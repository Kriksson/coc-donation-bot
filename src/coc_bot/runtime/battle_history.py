"""Bounded per-account battle evidence; reporting failures never interrupt input."""
from contextvars import ContextVar
from pathlib import Path
from functools import wraps
import json
import time
from uuid import uuid4

from loguru import logger

_CURRENT = ContextVar('battle_report', default=None)
LIMIT = 50


def _load(config):
    from coc_bot.accounts.store import read
    saved=read(config.data_dir/'battles/history.json',{})
    account=getattr(config,'account_tag',None)
    if not saved:return []
    if saved.get('account')!=account or saved.get('version')!=1 or not isinstance(saved.get('entries'),list):
        raise ValueError('Battle history identity or format is invalid')
    if any(not isinstance(e,dict) or not isinstance(e.get('deployments'),dict)
           or not isinstance(e.get('army'),list) for e in saved['entries']):
        raise ValueError('Battle history entries are invalid')
    json.dumps(saved,allow_nan=False)
    return saved['entries']


def history(config):
    try:return list(reversed(_load(config)))
    except (OSError,ValueError,TypeError,AttributeError):return []


class BattleReport:
    def __init__(self,config,village,*,recovery=False):
        self.config=config
        self.entry={'id':uuid4().hex,'village':village,'account':getattr(config,'account_tag',None),
                    'status':'running','recovery':recovery,'started_at':None,'ended_at':None,
                    'army':[],'deployments':{},'locations':[],'result_confirmed':False,
                    'loot':None,'stars':None,'damage_percent':None,'reason':None,'image':False}

    def save(self):
        if self.entry['started_at'] is None:return
        from coc_bot.accounts.store import write
        try:
            entries=[e for e in _load(self.config) if e.get('id')!=self.entry['id']]
            entries.append(self.entry)
            expired=entries[:-LIMIT]
            write(self.config.data_dir/'battles/history.json',{'version':1,'account':self.entry['account'],'entries':entries[-LIMIT:]})
            for entry in expired:
                ident=entry.get('id','')
                if isinstance(ident,str) and len(ident)==32 and all(c in '0123456789abcdef' for c in ident):
                    (self.config.data_dir/'battles'/f'{ident}.png').unlink(missing_ok=True)
        except (OSError,ValueError,TypeError,AttributeError) as exc:
            logger.warning('Отчёт о бое не сохранён: {}',exc)


def note_battle(**fields):
    report=_CURRENT.get()
    if report is None:return
    changed=False
    if fields.pop('entered_battle',False) and report.entry['started_at'] is None:
        report.entry['started_at']=time.time();changed=True
    for name in ('army','result_confirmed','reason','loot','stars','damage_percent'):
        if name in fields and report.entry[name]!=fields[name]:
            report.entry[name]=fields[name];changed=True
    if changed:report.save()


def note_deployment(unit,count=1,*,points=(),frame=None):
    report=_CURRENT.get()
    if report is None or type(count) is not int or not 0<count<=1000:return
    entry=report.entry
    entry['started_at']=entry['started_at'] or time.time()
    entry['deployments'][unit]=entry['deployments'].get(unit,0)+count
    targets=[(int(p[0]),int(p[1])) for p in points]
    entry['locations']=(entry['locations']+[{'unit':unit,'points':targets,'at':time.time()}])[-100:]
    try:
        import cv2
        import numpy as np
        if isinstance(frame,np.ndarray) and targets:
            image=frame.copy();h,w=image.shape[:2]
            for x,y in targets:
                if 0<=x<w and 0<=y<h:
                    cv2.circle(image,(x,y),max(9,round(w*.008)),(30,80,255),3)
            path=report.config.data_dir/'battles'/f'{entry["id"]}.png'
            path.parent.mkdir(parents=True,exist_ok=True)
            entry['image']=bool(cv2.imwrite(str(path),image))
    except (OSError,ValueError,TypeError,cv2.error) as exc:
        logger.warning('Снимок высадки не сохранён: {}',exc)
    report.save()


def record_results(first,second,village,stop=None):
    if _CURRENT.get() is None:return
    try:
        from coc_bot.vision.battle_rewards import agreeing_results
        note_battle(**agreeing_results(first,second,village,stop))
    except (OSError,ValueError,TypeError,AttributeError) as exc:
        logger.debug('Данные результата боя не прочитаны: {}',exc)


def tracked_battle(village):
    def decorate(function):
        @wraps(function)
        def run(owner,*args,**kwargs):
            if _CURRENT.get() is not None:return function(owner,*args,**kwargs)
            config=getattr(owner,'config',None)
            if not isinstance(getattr(config,'data_dir',None),Path):return function(owner,*args,**kwargs)
            report=BattleReport(config,village,recovery=village=='builder' and not kwargs.get('deploy',False))
            token=_CURRENT.set(report)
            try:
                result=function(owner,*args,**kwargs)
                success=result.get('status')=='returned' if isinstance(result,dict) else bool(getattr(result,'success',False))
                report.entry.update(status='returned' if success else 'incomplete',
                                    reason=str(result.get('status') if isinstance(result,dict) else getattr(result,'reason',''))[:500])
                return result
            except BaseException as exc:
                report.entry.update(status='interrupted',reason=str(exc)[:500])
                raise
            finally:
                report.entry['ended_at']=time.time()
                report.save()
                _CURRENT.reset(token)
        return run
    return decorate
