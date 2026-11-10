"""Read-only explanations of the current work and next safe scheduler turn."""
from datetime import datetime, timezone
import math
import time

LABELS={'farm':'Атака основной деревни','requests':'Запрос подкрепления','upgrades':'Улучшения основной деревни',
        'builder_base':'Деревня строителя','layouts':'Расстановка'}


def task_status(config, state, bot, farming, builder, activity):
    from coc_bot.runtime.visits import Visit, STEPS
    from coc_bot.accounts.store import read
    now=time.time()
    result={'reason':'Ожидаю следующую задачу','farm_due_at':None,'queue':[],
            'burst_limit':2,'builder_reason':None}
    try:
        visit=Visit(config).load();index=visit['step']
        order=list(STEPS[index:])
        if index==0 and not visit.get('maintenance_checked') and any(getattr(config,k,False) for k in
                ('upgrade_buildings_enabled','upgrade_research_enabled','upgrade_pets_enabled')):
            order=['upgrades']+[x for x in order if x!='upgrades']
        result['queue']=[{'task':name,'label':LABELS[name],
            'retry_at':visit['deferred'].get(name,{}).get('retry_at')} for name in order]
        if visit.get('finished_at'):result['next_check_at']=visit.get('next_check_at')
    except (OSError,ValueError,TypeError,AttributeError):
        result['queue_error']='Очередь не прочитана; требуется проверка журнала'
    if not state['active']:
        result['reason']='Бот остановлен: '+str(state['error']) if state.get('error') else 'Бот остановлен'
        return result
    phase=getattr(getattr(getattr(bot,'game_state',None),'state',None),'value',None)
    if phase=='boot' or state.get('state')=='starting':
        result['reason']='Проверяю аккаунт и восстанавливаю прерванные задачи'
    elif phase in ('in_battle','battle_results','returning_home'):
        result['reason']='Идёт бой или возврат в деревню. Следующая задача начнётся после подтверждения возврата'
    elif phase=='recovering':result['reason']='Восстанавливаю игру; новые атаки приостановлены'
    elif phase=='builder_base':
        result['reason']='Выполняю задачу деревни строителя. Затем продолжу очередь основной деревни'
        try:
            stage=read(config.data_dir/'builder_base/visit.json',{}).get('phase')
            result['reason']={'battle':'Идёт бой в деревне строителя; новые задачи начнутся после возврата',
                'matchmaking':'Ищу противника в деревне строителя',
                'collecting_resources':'Собираю ресурсы деревни строителя',
                'checking_upgrades':'Проверяю улучшения деревни строителя',
                'returning_to_home_village':'Возвращаюсь в основную деревню перед следующей задачей'}.get(stage,result['reason'])
        except (OSError,ValueError,TypeError):pass
    elif phase in ('upgrading','layouts'):result['reason']='Выполняю обслуживание деревни перед следующей атакой'
    elif not getattr(config,'farm_enabled',False):result['reason']='Автоматические атаки основной деревни отключены'
    elif not getattr(config,'farm_calibrated',False):result['reason']='Для атаки требуется завершить настройку распознавания'
    elif getattr(config,'farm_trigger_mode','resources')=='interval':
        try:
            last=read(config.data_dir/'runtime_state.json',{}).get('last_farm_at')
            moment=datetime.fromisoformat(last) if last else None
            if moment is not None and moment.tzinfo is None:raise ValueError('missing timezone')
            due=moment.timestamp()+config.farm_interval_seconds if moment else now
            if not math.isfinite(due):raise ValueError('invalid due')
            result['farm_due_at']=due
            seconds=max(0,math.ceil(due-now))
            result['reason']=(f'До следующей атаки {seconds//60:02d}:{seconds%60:02d}' if seconds
                              else 'Время атаки наступило; ожидаю свободной очереди и готовности армии')
        except (OSError,ValueError,TypeError,AttributeError,OverflowError):
            result['reason']='Не удалось проверить время последней атаки'
    elif farming.get('status')=='unverified':result['reason']='Атака ожидает подтверждённых показаний ресурсов основной деревни'
    elif farming.get('status')=='satisfied':result['reason']='Ресурсов достаточно; атака пока не нужна'
    else:result['reason']='Пополнение ресурсов запланировано; ожидаю готовности армии и свободной очереди'
    cooldown=getattr(bot,'_farm_fail_cooldown_until',0) if bot is not None else 0
    if type(cooldown) in (int,float) and math.isfinite(cooldown) and cooldown>time.monotonic() and phase not in ('in_battle','builder_base','recovering'):
        seconds=math.ceil(cooldown-time.monotonic())
        result['reason']=f'Повтор подготовки атаки через {seconds//60:02d}:{seconds%60:02d}'
    if builder.get('status')=='unverified':result['builder_reason']='Не подтверждены ресурсы строителя; атака ожидает повторного чтения'
    elif builder.get('status')=='refilling':result['builder_reason']='Нужно пополнить ресурсы строителя; не более двух заходов подряд'
    elif builder.get('status')=='satisfied':result['builder_reason']='Ресурсы строителя достигли установленного порога'
    return result
