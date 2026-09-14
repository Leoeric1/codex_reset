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
  if(!e){box.append(node('div','latest-date','暂无确认记录'));return;}
  const time=format(e.time).split(' '),heading=node('div','latest-date',time[0]);
  if(time[1])heading.append(node('small','',time[1]));box.append(heading,node('div','latest-caption',caption(e)));
  const meta=node('div','latest-meta');meta.append(node('span','badge '+tint(e),e.confirmation_basis==='receipt_review'?'AIHOT 回执核验':'来源帖子确认'));
  if(original(e))meta.append(link(original(e)));box.append(meta);
}
let filter='all',offset=0,busy=false,requestId=0;
function renderStatus(s){
  $('health-pill').className='pill '+s.color;
  $('health-pill').lastElementChild.textContent=s.source==='ok'?(s.status==='ok'?'AIHOT 正常':'本地同步延迟'):s.source==='stale'?'源站核验延迟':'数据源暂时不可用';
  $('checked').textContent=format(s.checked_at);$('synced').textContent=format(s.last_sync);$('next').textContent=format(s.next_check_at);
  latestCard('latest-reset',s.latest_reset);latestCard('latest-credit',s.latest_credit);
  const announcements=s.announcements, direct=announcements.find(e=>e.type==='direct_reset'),credit=announcements.find(e=>e.type==='reset_credit');
  const e=direct||credit;
  $('current-link').replaceChildren();
  if(!s.has_data){$('current-title').textContent='等待首次同步';$('current-detail').textContent='数据就绪后，这里将显示最新明确预告。';}
  else if(e){$('current-title').textContent=direct?'Tibo 已发布重置预告':'Tibo 已发布重置卡预告';$('current-detail').textContent=e.schedule?.label||'原帖尚未给出明确时间，请以原帖后续确认为准。';if(original(e))$('current-link').append(link(original(e)));}
  else{$('current-title').textContent='暂无有效的明确预告';$('current-detail').textContent='最近一次快照未发现有效预告。\n有新消息时，这里会自动更新。';}
  if(s.status!=='ok'&&s.has_data)$('current-detail').textContent+='\n当前显示最后成功数据，实时状态待核验。';
}
function renderEvent(e){
  const row=node('article','event'),time=node('div','event-time',format(e.time));time.append(node('small','',e.time_precision==='confirmed'?'确认帖时间':e.time_precision==='date'?'核验日期':'原帖时间'));
  const body=node('div','event-body'),top=node('div','event-top');top.append(node('h3','',e.title),node('span','badge '+tint(e),label(e)));body.append(top);
  if(e.posts[0])body.append(node('p','event-copy',e.posts[0].text));
  const notes=[];if(e.scope)notes.push('适用范围：'+e.scope);if(e.schedule)notes.push('原始预告：'+e.schedule.label);
  if(e.expired)notes.push('历史预告 · 时间已过或超过 24 小时仍无明确时间，未获确认');
  if(e.confirmation_basis==='receipt_review')notes.push('确认依据：AIHOT 回执核验');
  if(e.status==='confirmed'&&e.time_precision==='post')notes.push('实际发生日期未知，按原帖时间展示');
  if(notes.length)body.append(node('div','event-notes',notes.join(' · ')));
  if(original(e))body.append(link(original(e)));
  if(e.posts.length>1){const details=node('details'),summary=node('summary','',`查看全部 ${e.posts.length} 条原帖`);details.append(summary);e.posts.forEach(p=>{const item=node('div','post');item.append(node('span','',format(p.time)+' · '+p.stage),node('p','',p.text));if(p.url)item.append(link(p.url));details.append(item);});body.append(details);}
  row.append(time,node('div','event-dot '+tint(e)),body);return row;
}
async function get(url){const r=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(12000)});if(!r.ok)throw new Error('请求失败');const type=r.headers.get('content-type')||'';if(!type.includes('application/json'))throw new Error('登录状态可能已失效，请重新打开页面');return r.json();}
async function load(append=false){
  const id=++requestId;busy=true;$('refresh').disabled=true;$('more').disabled=true;
  try{
    const q=new URLSearchParams({limit:'30',offset:String(append?offset:0)});if(filter==='announced')q.set('status','announced');else if(filter!=='all')q.set('type',filter);
    const [s,data]=await Promise.all([get('/api/status'),get('/api/events?'+q)]);if(id!==requestId)return;
    renderStatus(s);if(!append)$('timeline').replaceChildren();
    data.items.forEach(e=>$('timeline').append(renderEvent(e)));if(!data.total)$('timeline').append(node('p','empty','暂无此类事件。'));
    offset=(append?offset:0)+data.items.length;$('count').textContent=data.total;$('more').hidden=offset>=data.total;$('client-error').hidden=true;
  }catch(e){if(id===requestId){$('client-error').textContent='页面暂时无法更新，已保留当前内容。'+(e.message||'请稍后重试。');$('client-error').hidden=false;}}
  finally{if(id===requestId){busy=false;$('refresh').disabled=false;$('more').disabled=false;}}
}
$('refresh').addEventListener('click',()=>load());$('more').addEventListener('click',()=>load(true));
document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));load();}));
load();setInterval(()=>{if(!busy&&!document.hidden&&!document.querySelector('details[open]')&&offset<=30)load();},60000);
