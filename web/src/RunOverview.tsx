import React,{useEffect,useState} from 'react';
import {MessageText} from './ui';
export type TaskStatus={reason:string;builder_reason?:string|null;burst_limit:number;queue:{task:string;label:string;retry_at?:number}[];queue_error?:string};
export function RunOverview({data}:{data?:TaskStatus}){
  if(!data)return null;
  return <section className="panel task-overview"><div className="panel-label">План работы</div>
    <p className="task-reason" role="status">{data.reason}</p>
    {data.builder_reason&&<p className="task-secondary">{data.builder_reason}</p>}
    {!!data.queue.length&&<ol className="task-queue" aria-label="Очередь задач">{data.queue.map((task,index)=><li key={task.task}>
      <span className="queue-number">{index+1}</span><span>{task.label}{!!task.retry_at&&task.retry_at*1000>Date.now()&&<small>После {new Date(task.retry_at*1000).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'})}</small>}</span>
    </li>)}</ol>}
    {data.queue_error&&<p>{data.queue_error}</p>}
    <small className="task-secondary">До {data.burst_limit} повторных заходов подряд в одну деревню, затем — следующая задача.</small>
  </section>;
}
type Battle={id:string;village:string;started_at:number;ended_at?:number;status:string;reason?:string;reason_label?:string;recovery:boolean;
  result_confirmed:boolean;stars?:number;damage_percent?:number;army:{unit:string;count:number}[];deployments:Record<string,number>;loot:Record<string,number>|null;image:boolean};
const outcomes:Record<string,string>={running:'Бой не завершён',returned:'Возврат подтверждён',incomplete:'Требуется проверка',interrupted:'Прерван'};
export function BattleHistory({base}:{base:string}){
  const [entries,setEntries]=useState<Battle[]>([]),[labels,setLabels]=useState<Record<string,string>>({}),[error,setError]=useState(false);
  useEffect(()=>{let stopped=false;const update=async()=>{
    try{const response=await fetch(base+'/api/battles');if(!response.ok)throw new Error();const data=await response.json();
      if(!stopped){setEntries(data.entries);setLabels(data.unit_labels||{});setError(false);}}
    catch{if(!stopped)setError(true);}
  };void update();const timer=setInterval(update,15000);return()=>{stopped=true;clearInterval(timer);};},[base]);
  return <section className="panel battle-history"><div className="panel-label">История боёв</div>
    {error&&<p role="status">Не удалось обновить историю боёв</p>}
    {!entries.length&&<p className="task-secondary">Здесь появятся отчёты новых боёв.</p>}
    {entries.slice(0,10).map(battle=><details key={battle.id} className="battle-entry"><summary>
      <time>{new Date(battle.started_at*1000).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</time>
      <span>{battle.village==='builder'?'Деревня строителя':'Основная деревня'}</span><strong>{outcomes[battle.status]||'Исход не подтверждён'}</strong>
    </summary><div className="battle-detail">
      {battle.recovery&&<p>Восстановление прерванного боя</p>}
      <p>{battle.result_confirmed?'Экран результатов подтверждён':'Результат боя не прочитан'}{battle.ended_at&&` · ${Math.max(0,Math.round(battle.ended_at-battle.started_at))} с`}</p>
      {!!battle.army.length&&<p>{battle.village==='builder'?'Лагеря':'Армия'}: {battle.army.map(a=>`${labels[a.unit]||'Отряд'} ×${a.count}`).join(', ')}</p>}
      <p>Подтверждённые высадки: {Object.entries(battle.deployments).map(([unit,count])=>`${labels[unit]||'Отряд'} ×${count}`).join(', ')||'нет'}</p>
      {(battle.stars!=null||battle.damage_percent!=null)&&<p>{[battle.stars!=null?`Звёзды: ${battle.stars}`:null,battle.damage_percent!=null?`Разрушение: ${battle.damage_percent}%`:null].filter(Boolean).join(' · ')}</p>}
      <p>{battle.village==='builder'?'Награда':'Добыча'}: {battle.loot?Object.entries(battle.loot).map(([key,value])=>`${({gold:'золото',elixir:'эликсир',dark_elixir:'тёмный эликсир'} as Record<string,string>)[key]||'ресурс'} ${value.toLocaleString('ru-RU')}`).join(', '):'не считана'}</p>
      {battle.reason&&<p><MessageText value={battle.reason_label||battle.reason}/></p>}
      {battle.image&&<a href={base+`/api/battles/${battle.id}/image`} target="_blank" rel="noreferrer">Снимок последней подтверждённой высадки</a>}
    </div></details>)}
  </section>;
}
