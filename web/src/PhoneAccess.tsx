import React,{useState} from 'react';
import {Icon} from './ui';

export function PhoneAccess({api}:{api:(path:string)=>Promise<any>}){
  const [urls,setUrls]=useState<string[]>([]),[loaded,setLoaded]=useState(false),[error,setError]=useState('');
  async function load(){
    try{const result=await api('network');setUrls(result.urls||[]);setError('');}
    catch{setError('Не удалось получить адрес. Проверьте соединение с панелью.');}
    finally{setLoaded(true);}
  }
  async function copy(){
    if(!navigator.clipboard){setError('Выделите адрес и скопируйте его через меню браузера.');return;}
    try{await navigator.clipboard.writeText(urls[0]);}
    catch{setError('Выделите адрес и скопируйте его через меню браузера.');}
  }
  return <details className="phone-access" onToggle={e=>{if(e.currentTarget.open)load();}}>
    <summary aria-label="Открыть панель на телефоне"><Icon name="link" size={16}/><span>На телефоне</span></summary>
    <div className="phone-access-panel"><strong>Панель на телефоне</strong>
      <p>Подключите телефон к той же сети Wi-Fi, что и компьютер, и откройте этот адрес в браузере.</p>
      {!loaded&&<p role="status">Определяю адрес…</p>}
      {error&&<p role="alert">{error}</p>}
      {loaded&&!error&&!urls.length&&<p>Доступ по Wi-Fi пока не включён или компьютер не подключён к локальной сети.</p>}
      {urls.map(url=><a className="phone-link" key={url} href={url}>{url}</a>)}
      {!!urls.length&&<button onClick={copy}>Скопировать адрес</button>}
      <p>Компьютер должен оставаться включённым, а панель — запущенной.</p>
    </div>
  </details>;
}
