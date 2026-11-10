import React,{useState} from 'react';
import {EmptyState,Icon,MessageText} from './ui';

type Field={key:string;label:string;description:string;kind:string;choices:string[];section:string;advanced:boolean};
const categories=[['Общие','settings'],['Пожертвования','heart'],['Атаки','swords'],['Улучшения','hammer'],
  ['Строительная база','castle'],['Внешний вид','palette'],['Снимки экрана','image'],['Устройство','link']];
function category(f:Field){
  if(f.key.startsWith('builder_base_'))return 'Строительная база';
  if(/^(upgrade_|progression_|layouts_)/.test(f.key))return 'Улучшения';
  if(f.key.startsWith('farm_'))return 'Атаки';
  if(f.key.startsWith('collection_'))return 'Снимки экрана';
  if(['gui_theme','gui_show_debug_activity','gui_dev_options'].includes(f.key))return 'Внешний вид';
  if(f.section==='Donation')return 'Пожертвования';
  if(/Device|Clan/.test(f.section))return 'Устройство';
  return 'Общие';
}
const choiceLabels:Record<string,string>={resources:'По ресурсам',interval:'По интервалу',sequence:'Последовательность',planner:'Планировщик',automatic:'Автоматически',left:'Слева',right:'Справа',Safe:'Безопасный',Balanced:'Сбалансированный',Fast:'Быстрый',Custom:'Вручную'};

function SettingRow({field:f,value,edit}:{field:Field;value:any;edit:(v:any)=>void}){
  const [help,setHelp]=useState(false);
  return <div className={'setting '+(help?'help-open':'')}>
    <div className="setting-name"><label htmlFor={f.key}>{f.label}</label>{f.description&&<button type="button" className="icon-button field-help"
      aria-label={'Подсказка: '+f.label} aria-expanded={help} aria-controls={f.key+'-help'} title={f.description} onClick={()=>setHelp(!help)}><Icon name="info" size={15}/></button>}</div>
    {f.kind==='bool'?<input id={f.key} className="switch" type="checkbox" checked={!!value} onChange={e=>edit(e.target.checked)}/>:
      f.kind==='choice'?<select id={f.key} value={value??''} onChange={e=>edit(e.target.value)}>{f.choices.map(c=><option key={c} value={c}>{choiceLabels[c]||c}</option>)}</select>:
      <input id={f.key} value={value??''} type={['int','float'].includes(f.kind)?'number':'text'} min={0} step={f.kind==='float'?'any':1} onChange={e=>edit(e.target.value)}/>}
    {help&&<p id={f.key+'-help'} className="setting-description">{f.description}</p>}
  </div>;
}

export function SettingsPanel({fields,values,search,setSearch,advanced,setAdvanced,dirty,saving,restarting,saveDisabled,resetDisabled,save,reset,edit,updateMessage}: {
  fields:Field[];values:Record<string,any>;search:string;setSearch:(s:string)=>void;advanced:boolean;setAdvanced:(v:boolean)=>void;
  dirty:boolean;saving:boolean;restarting:boolean;saveDisabled:boolean;resetDisabled:boolean;save:()=>void;reset:()=>void;
  edit:(key:string,value:any)=>void;updateMessage?:string|null;
}){
  const [selected,setSelected]=useState('General');
  const available=categories.filter(([name])=>fields.some(f=>category(f)===name));
  const active=available.some(([name])=>name===selected)?selected:available[0]?.[0];
  const shown=fields.filter(f=>search.trim()||category(f)===active);
  return <div className="settings-workspace">
    <div className="page-actions settings-actions"><label className="search-field"><Icon name="search" size={18}/><input aria-label="Поиск настроек" placeholder="Найти настройку…" value={search} onChange={e=>setSearch(e.target.value)}/>
      {search&&<button className="icon-button" aria-label="Очистить поиск" onClick={()=>setSearch('')}><Icon name="close" size={15}/></button>}</label>
      <label className="toggle"><input type="checkbox" checked={advanced} onChange={e=>setAdvanced(e.target.checked)}/>Дополнительно</label>
      <div className="action-spacer"/>{(dirty||saving)&&<><button disabled={resetDisabled||!dirty} onClick={reset}>Отменить изменения</button>
      <button disabled={saveDisabled} className="primary" onClick={save}><Icon name={saving?'refresh':'check'} size={17}/>{saving?'Применение…':restarting?'Сохранить и перезапустить':'Сохранить изменения'}</button>
      </>}
    </div>
    <div className="settings-layout"><nav className="settings-nav" aria-label="Категории настроек">{available.map(([name,icon])=><button key={name} aria-current={!search&&active===name?'page':undefined}
      className={!search&&active===name?'selected':''} onClick={()=>{setSelected(name);setSearch('');}}><Icon name={icon} size={18}/>{name}</button>)}</nav>
      <div className="settings-content">
      {updateMessage&&<div className="notice" role="status"><MessageText value={updateMessage}/></div>}
      <section className="settings panel">{shown.map(f=><SettingRow key={f.key} field={f} value={values[f.key]} edit={v=>edit(f.key,v)}/>)}
      {!shown.length&&<EmptyState icon="search">Настройки не найдены</EmptyState>}</section></div>
    </div>
  </div>;
}
