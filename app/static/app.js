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
  try { const u=new URL(url); if(u.protocol!=='https:'||u.username||u.password||!['x.com','twitter.com','aihot.news'].includes(u.hostname))return node('span','muted','原帖链接不可用'); }
  catch { return node('span','muted','原帖链接不可用'); }
  a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;
}
function label(e) { return e.type==='reset_credit'?(e.status==='confirmed'?'重置卡已发放':'重置卡预告'):(e.status==='confirmed'?'全员重置确认':'全员重置预告'); }
function tint(e) { return e.status==='announced'?'yellow':e.type==='reset_credit'?'purple':'blue'; }
function caption(e) {return e.time_precision==='confirmed'?'确认帖发布时间 · 实际执行时刻未知':e.time_precision==='date'?'已核验发生日期 · 具体时刻未知':'原帖发布时间 · 实际发生日期未知';}
function scheduleText(e) {
  const s=e.schedule;
  if(!s)return '预计时间未明确';
  return s.label || (s.from ? format(s.from)+(s.through?' — '+format(s.through):''):'预计时间未明确');
}
function postCard(p, compact=false) {
  const card=node('article','post-card'+(compact?' compact':''));
  const head=node('div','post-heading');
  head.append(node('span','post-stage',p.stage||'原帖'),node('time','post-time',format(p.time)+' 发布'));
  card.append(head,node('p','post-text',p.text||'暂无中文内容'));
  const foot=node('div','post-footer');foot.append(node('span','muted','中文内容 · AIHOT 整理'));
  if(p.url)foot.append(link(p.url));card.append(foot);return card;
}
function latestCard(id,e,hero=false) {
  const box=$(id);box.replaceChildren();
  if(!e){box.append(node('p','empty','暂无确认记录'));return;}
  const info=node('div','latest-info');
  info.append(node('span','badge '+tint(e),label(e)));
  const parts=format(e.time).split(' ');
  const date=node('div','latest-date',parts[0].slice(5));
  if(parts[1])date.append(node('strong','latest-time',parts[1]));
  info.append(date,node('p','latest-year',parts[0].slice(0,4)+' 年'),node('p','latest-caption',caption(e)));
  box.append(info);
  if(hero && e.posts.length)box.append(postCard(e.posts[0],true));
  else if(!hero){
    box.append(node('p','credit-excerpt',e.posts[0]?.text||e.title));
    if(e.posts[0]?.url)box.append(link(e.posts[0].url));
  }
}
function renderStatus(s){
  const healthy=s.status==='ok';
  const text=healthy?'数据正常':s.source==='unavailable'?'数据源不可用':'数据更新延迟';
  $('source-status').textContent=text;
  $('health-pill').className='pill '+s.color;
  $('health-pill').lastElementChild.textContent=text+(s.checked_at?' · 最近核验 '+format(s.checked_at).split(' ')[1]:'');
  if(!healthy)$('health-details').open=true;
  $('checked').textContent=format(s.checked_at);$('synced').textContent=format(s.last_sync);$('next').textContent=format(s.next_check_at);
  $('failures').textContent=s.consecutive_failures||0;$('last-error').textContent=s.last_error||'无';
  latestCard('latest-reset',s.latest_reset,true);latestCard('latest-credit',s.latest_credit);
  $('announcement').replaceChildren();$('announcement').hidden=!s.announcements.length;
  s.announcements.forEach(e=>{
    const row=node('div','announcement-row');row.append(node('span','badge yellow',label(e)),node('span','announcement-text',scheduleText(e)),node('span','muted','发布于 '+format(e.announced_at)));
    if(e.posts[0]?.url)row.append(link(e.posts[0].url));$('announcement').append(row);
  });
}
function eventCard(e){
  const card=node('article','day-event');card.dataset.eventId=e.id;
  const top=node('div','event-heading');top.append(node('span','badge '+tint(e),label(e)),node('span','event-clock',format(e.time).split(' ')[1]||'时刻未知'));
  card.append(top,node('h4','',e.title),node('p','event-caption',caption(e)));
  if(e.scope)card.append(node('p','event-scope','范围：'+e.scope));
  if(e.schedule)card.append(node('p','event-schedule',(e.status==='confirmed'?'原预告：':'预告：')+scheduleText(e)));
  if(e.expired)card.append(node('p','event-schedule','历史预告 · 已过有效时间，尚未确认'));
  e.posts.forEach(p=>card.append(postCard(p)));
  if(!e.posts.length)card.append(node('p','empty','暂无原帖内容'));
  return card;
}
let current=null, desiredMonth=null, requestId=0, busy=false, loaded=0;
function dayLabel(day){
  const parts=[day.date];
  if(day.direct_reset)parts.push(day.direct_reset+' 条全员重置确认');
  if(day.reset_credit)parts.push(day.reset_credit+' 条重置卡确认');
  if(day.announced)parts.push(day.announced+' 条预告');
  if(!day.total)parts.push('无记录');
  return parts.join('，');
}
function renderCalendar(data,append){
  const focusDate=document.activeElement?.dataset.date;
  const oldScroll=$('day-scroll').scrollTop;
  const sameDay=current?.selected_date===data.selected_date;
  renderStatus(data.status);
  $('month-title').textContent=data.month.replace('-', ' 年 ')+' 月';
  $('month-count').textContent=`本月：${data.totals.direct_reset} 条全员重置 · ${data.totals.reset_credit} 条重置卡 · ${data.totals.announced} 条预告`;
  const days=document.createDocumentFragment();
  data.days.forEach(day=>{
    const button=node('button','day'+(day.date.startsWith(data.month)?'':' outside'));
    button.type='button';button.dataset.date=day.date;button.setAttribute('aria-label',dayLabel(day));
    button.setAttribute('aria-pressed',String(day.date===data.selected_date));
    if(day.date===data.today)button.setAttribute('aria-current','date');
    button.append(node('span','day-number',String(Number(day.date.slice(8)))));
    const marks=node('span','day-marks');
    for(const [field,text,cls] of [['direct_reset','全员重置','reset-mark'],['reset_credit','重置卡','credit-mark'],['announced','预告','announcement-mark']]){
      if(day[field])marks.append(node('span',cls,text+(day[field]>1?' ×'+day[field]:'')));
    }
    button.append(marks);days.append(button);
  });
  $('calendar-days').replaceChildren(days);
  $('day-title').textContent=data.selected_date.replace('-', ' 年 ').replace('-', ' 月 ')+' 日';
  $('day-count').textContent=data.total+' 条记录';
  if(!append)$('day-events').replaceChildren();
  const existing=new Set([...$('day-events').children].map(e=>e.dataset.eventId));
  data.items.forEach(e=>{if(!existing.has(e.id))$('day-events').append(eventCard(e));});
  if(!data.total)$('day-events').append(node('p','empty','当天暂无记录，试试日历中带标记的日期。'));
  loaded=data.offset+data.items.length;$('more').hidden=loaded>=data.total;
  current=data;desiredMonth=data.month;
  $('day-scroll').scrollTop=sameDay?oldScroll:0;
  if(focusDate){const button=[...$('calendar-days').children].find(e=>e.dataset.date===focusDate);button?.focus({preventScroll:true});}
}
async function get(url){
  const r=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(12000)});
  if(!r.ok)throw new Error('请求失败，请稍后重试');
  if(!(r.headers.get('content-type')||'').includes('application/json'))throw new Error('登录状态可能已失效，请重新打开页面');
  const data=await r.json();
  const counts=v=>v&&['direct_reset','reset_credit','announced','total'].every(k=>Number.isSafeInteger(v[k])&&v[k]>=0);
  const event=v=>v&&typeof v.id==='string'&&typeof v.title==='string'&&typeof v.time==='string'
    &&['direct_reset','reset_credit'].includes(v.type)&&['announced','confirmed'].includes(v.status)
    &&['confirmed','date','post'].includes(v.time_precision)
    &&(!v.schedule||typeof v.schedule==='object')
    &&Array.isArray(v.posts)&&v.posts.every(p=>p&&typeof p.text==='string'&&typeof p.time==='string');
  if(!data||!Array.isArray(data.days)||data.days.length!==42
    ||!data.days.every(d=>counts(d)&&/^\d{4}-\d{2}-\d{2}$/.test(d.date))
    ||!Array.isArray(data.items)||!data.items.every(event)||!counts(data.totals)
    ||!/^\d{4}-\d{2}$/.test(data.month)||!/^\d{4}-\d{2}-\d{2}$/.test(data.selected_date)
    ||!Number.isSafeInteger(data.total)||data.total<0||!Number.isSafeInteger(data.offset)||data.offset<0
    ||!data.status||!Array.isArray(data.status.announcements)||!data.status.announcements.every(event)
    ||(data.status.latest_reset&&!event(data.status.latest_reset))
    ||(data.status.latest_credit&&!event(data.status.latest_credit)))throw new Error('数据格式异常');
  return data;
}
async function load({month=current?.month,day=current?.selected_date,append=false}={}){
  const id=++requestId;busy=true;$('refresh').disabled=true;$('more').disabled=true;$('calendar-panel').setAttribute('aria-busy','true');
  const q=new URLSearchParams({limit:'20',offset:String(append?loaded:0)});
  if(month)q.set('month',month);if(day)q.set('day',day);
  try{
    const data=await get('/api/calendar?'+q);if(id!==requestId)return;
    // A changed snapshot invalidates offset pagination; reload the selected day.
    if(append && data.status.last_snapshot_at!==current?.status.last_snapshot_at){load({month,day});return;}
    renderCalendar(data,append);$('client-error').hidden=true;
  }catch(e){if(id===requestId){desiredMonth=current?.month||null;$('client-error').textContent='页面暂时无法更新，已保留当前内容。'+(e.message||'');$('client-error').hidden=false;}}
  finally{if(id===requestId){busy=false;$('refresh').disabled=false;$('more').disabled=false;$('calendar-panel').setAttribute('aria-busy','false');}}
}
function moveMonth(delta){
  if(!desiredMonth)return;
  const [y,m]=desiredMonth.split('-').map(Number),d=new Date(Date.UTC(y,m-1+delta,1));
  if(d.getUTCFullYear()<1900||d.getUTCFullYear()>9998)return;
  desiredMonth=d.toISOString().slice(0,7);load({month:desiredMonth,day:null});
}
$('previous-month').addEventListener('click',()=>moveMonth(-1));$('next-month').addEventListener('click',()=>moveMonth(1));
$('latest').addEventListener('click',()=>load({month:null,day:null}));
$('calendar-days').addEventListener('click',event=>{const day=event.target.closest('[data-date]')?.dataset.date;if(day)load({month:day.slice(0,7),day});});
$('refresh').addEventListener('click',()=>load());$('more').addEventListener('click',()=>load({append:true}));
function setTheme(){const light=document.documentElement.dataset.theme==='light';$('theme').textContent=light?'深色':'浅色';$('theme').setAttribute('aria-pressed',String(light));}
$('theme').addEventListener('click',()=>{const value=document.documentElement.dataset.theme==='light'?'dark':'light';document.documentElement.dataset.theme=value;try{localStorage.setItem('leohub-theme',value);}catch{}setTheme();});
setTheme();
function tick(){ $('clock').textContent=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date()); }
tick();setInterval(tick,30000);
load();setInterval(()=>{if(!busy&&!document.hidden&&loaded<=20&&!window.getSelection()?.toString())load();},60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!busy)load();});
