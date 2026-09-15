'use strict';
const $ = (id) => document.getElementById(id);
const format = (value, dateOnly = false) => {
  if (!value) return '未知';
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value.replaceAll('-', '.');
  const d = new Date(value);
  if (Number.isNaN(d.valueOf())) return '未知';
  return new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',...(dateOnly?{}:{hour:'2-digit',minute:'2-digit',hour12:false})}).format(d).replaceAll('-', '.');
};
function node(tag, cls, text) { const e=document.createElement(tag); if(cls)e.className=cls; if(text!==undefined)e.textContent=text; return e; }
function link(url, text='查看原帖 ↗') {
  const a=node('a','event-link',text);
  try { const u=new URL(url); if(u.protocol!=='https:'||!['x.com','twitter.com','aihot.news'].includes(u.hostname))return node('span','','原帖链接不可用'); }
  catch { return node('span','','原帖链接不可用'); }
  a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;
}
function label(e) { return e.type==='reset_credit'?(e.status==='confirmed'?'重置卡已发放':'重置卡预告'):(e.status==='confirmed'?'全员重置确认':'全员重置预告'); }
function tint(e) { return e.status==='announced'?'yellow':e.type==='reset_credit'?'purple':''; }
function caption(e) {return e.time_precision==='confirmed'?'确认帖发布时间 · 实际执行时刻未知':e.time_precision==='date'?'已核验发生日期 · 具体时刻未知':'原帖发布时间 · 实际发生日期未知';}
function original(e) { return e.posts.find(p=>p.url)?.url; }
function latestCard(id,e) {
  const box=$(id);box.replaceChildren();
  if(!e){box.append(node('div','empty','暂无确认记录'));return;}
  const parts=format(e.time).split(' '),date=parts[0].slice(5);
  const heading=node('div','latest-date',date);
  if(parts[1])heading.append(node('strong','latest-time',parts[1]));
  box.append(heading,node('div','latest-caption',caption(e)));
  const meta=node('div','latest-meta');meta.append(node('span','badge '+tint(e),label(e)),node('span','source','AIHOT'));
  if(original(e))meta.append(link(original(e)));box.append(meta);
}
let filter='all',offset=0,busy=false,requestId=0;
function renderStatus(s){
  const healthy=s.status==='ok';
  const text=healthy?'数据正常':s.source==='unavailable'?'数据源不可用':'数据更新延迟';
  $('source-status').textContent=text;
  $('health-pill').className='pill '+s.color;
  $('health-pill').lastElementChild.textContent=text+(s.checked_at?' · 最近核验 '+format(s.checked_at).split(' ')[1]:'');
  if(!healthy)$('health-details').open=true;
  $('checked').textContent=format(s.checked_at);$('synced').textContent=format(s.last_sync);$('next').textContent=format(s.next_check_at);
  $('failures').textContent=s.consecutive_failures||0;$('last-error').textContent=s.last_error||'无';
  latestCard('latest-reset',s.latest_reset);latestCard('latest-credit',s.latest_credit);
  const e=s.announcements.find(e=>e.type==='direct_reset')||s.announcements[0];
  $('announcement').classList.toggle('has-announcement',!!e);
  $('current-link').replaceChildren();$('current-detail').hidden=!e;
  $('current-title').textContent=e?'新的重置预告':s.has_data?'暂无新的重置预告':'等待首次同步';
  if(e){
    const schedule=e.schedule||{};
    const window= schedule.label || (schedule.from ? format(schedule.from)+(schedule.through?' — '+format(schedule.through):''):'时间区间待确认');
    $('current-detail').textContent=label(e)+' · '+window+'\n发布于 '+format(e.announced_at)+' · AIHOT';
    if(original(e))$('current-link').append(link(original(e)));
  }
}
function renderEvent(e){
  const row=node('article','event'),time=node('div','event-time',format(e.time));
  const body=node('div','event-body'),top=node('div','event-top');
  top.append(node('span','badge '+tint(e),e.type==='reset_credit'?'重置卡':'全员重置'),node('span','event-stage',e.status==='announced'?'预告帖发布':e.time_precision==='confirmed'?'确认帖发布':e.time_precision==='date'?'核验日期':'原帖发布'));
  if(original(e))top.append(link(original(e)));
  body.append(top);
  const details=node('details','event-details'),summary=node('summary','','展开详情');details.append(summary);
  if(e.expired)details.append(node('p','event-notes','历史预告 · 已过有效时间，未获确认'));
  details.append(node('p','event-notes',caption(e)));
  if(e.schedule)details.append(node('p','event-notes','schedule：'+(e.schedule.label||'未提供说明')+' '+(e.schedule.from?format(e.schedule.from):'')+(e.schedule.through?' — '+format(e.schedule.through):'')));
  if(e.confirmation_basis)details.append(node('p','event-notes','confirmationBasis：'+e.confirmation_basis));
  e.posts.forEach(p=>{const item=node('div','post');item.append(node('span','',format(p.time)+' · '+p.stage),node('p','',p.text));if(p.url)item.append(link(p.url));details.append(item);});
  body.append(details);row.append(time,body);return row;
}
async function get(url){const r=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(12000)});if(!r.ok)throw new Error('请求失败');const type=r.headers.get('content-type')||'';if(!type.includes('application/json'))throw new Error('登录状态可能已失效，请重新打开页面');return r.json();}
async function load(append=false){
  const id=++requestId;busy=true;$('refresh').disabled=true;$('more').disabled=true;
  try{
    const q=new URLSearchParams({limit:'10',offset:String(append?offset:0)});if(filter==='announced')q.set('status','announced');else if(filter!=='all')q.set('type',filter);
    const [s,data]=await Promise.all([get('/api/status'),get('/api/events?'+q)]);if(id!==requestId)return;
    renderStatus(s);if(!append)$('timeline').replaceChildren();
    data.items.forEach(e=>$('timeline').append(renderEvent(e)));if(!data.total)$('timeline').append(node('p','empty','暂无此类事件。'));
    offset=(append?offset:0)+data.items.length;$('count').textContent=data.total;$('more').hidden=offset>=data.total;$('client-error').hidden=true;
  }catch(e){if(id===requestId){$('client-error').textContent='页面暂时无法更新，已保留当前内容。'+(e.message||'请稍后重试。');$('client-error').hidden=false;}}
  finally{if(id===requestId){busy=false;$('refresh').disabled=false;$('more').disabled=false;}}
}
$('refresh').addEventListener('click',()=>load());$('more').addEventListener('click',()=>load(true));
document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));load();}));
load();setInterval(()=>{if(!busy&&!document.hidden&&!document.querySelector('.event-details[open]')&&offset<=10)load();},60000);

function setTheme(){const light=document.documentElement.dataset.theme==='light';$('theme').textContent=light?'深色':'浅色';$('theme').setAttribute('aria-pressed',String(light));}
$('theme').addEventListener('click',()=>{const value=document.documentElement.dataset.theme==='light'?'dark':'light';document.documentElement.dataset.theme=value;try{localStorage.setItem('leohub-theme',value);}catch{}setTheme();});
setTheme();
function tick(){ $('clock').textContent=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date()); }
tick();setInterval(tick,30000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!busy)load();});
