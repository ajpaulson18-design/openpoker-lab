"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = (v) => (v*100).toFixed(1)+'%';
const chips = (v) => Number(v).toFixed(2);
let opponents = [], game = null;
function status(message='', error=false) { $('#status').textContent=message; $('#status').classList.toggle('error',error); }
async function api(path,data) {
  const response=await fetch('/api/'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const result=await response.json(); if(!response.ok) throw new Error(result.error||'Request failed.'); return result;
}
function formData(form,numeric=[]) { const d=Object.fromEntries(new FormData(form)); for(const k of numeric)d[k]=Number(d[k]); return d; }
function bindForm(id,work,message='Calculating…') {
  $(id).addEventListener('submit',async e=>{e.preventDefault();const button=e.target.querySelector('button[type="submit"],button.primary');button.disabled=true;status(message);try{await work(e.target);status('Done. Results are ready.');}catch(err){status(err.message,true);}finally{button.disabled=false;}});
}
function warnings(items){return '<ul class="warnings">'+items.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>';}
function metric(value,label,small=false){return `<div class="metric"><strong${small?' class="smaller"':''}>${esc(value)}</strong><span>${esc(label)}</span></div>`;}
function equityStats(q){return `<div class="metrics">${metric(pct(q.equity),'POT EQUITY')}${metric(pct(q.win),'OUTRIGHT WIN')}${metric(pct(q.tie),'TIE')}</div><p class="hint">${q.exact?'Exact enumeration':q.trials.toLocaleString()+' trials · seed '+esc(q.seed)} · 95% sampling interval ${pct(q.interval95[0])}–${pct(q.interval95[1])}</p>`;}
function cardHtml(c){return `<span class="small-card ${/[dh]/.test(c[1])?'red':''}">${esc(c[0])}${{s:'♠',h:'♥',d:'♦',c:'♣'}[c[1]]||''}</span>`;}
document.querySelectorAll('.tab').forEach(button=>button.addEventListener('click',()=>{
  document.querySelectorAll('.panel').forEach(p=>p.hidden=p.id!==button.dataset.tab);
  document.querySelectorAll('.tab').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-current',b===button?'page':'false');});status();
}));
bindForm('#analysis-form',async form=>{
  const r=await api('analyze',formData(form,['pot','to_call','bet','trials','seed']));
  $('#analysis-result').innerHTML=`<p class="eyebrow">DECISION REPORT · SAVED LOCALLY</p>${equityStats(r.equity)}<div class="recommend"><span>HIGHEST ESTIMATED EV IN THIS MODEL</span><strong>${esc(r.recommended)}</strong></div><table><thead><tr><th>Action</th><th>Baseline EV</th><th>Modeled EV</th></tr></thead><tbody>${Object.entries(r.actions).map(([a,v])=>`<tr><td>${esc(a)}</td><td>${chips(r.baseline_actions[a])}</td><td>${chips(v)}</td></tr>`).join('')}</tbody></table><p>${esc(r.explanation)}</p>${warnings(r.warnings)}<p class="fine">${esc(r.method)} · Values in chips. Baseline is illustrative, not equilibrium.</p>`;
});
bindForm('#equity-form',async form=>{
  const data=formData(form,['trials','seed']);data.ranges=data.ranges.split('\n').map(s=>s.trim()).filter(Boolean);
  const r=await api('equity',data);
  $('#equity-result').innerHTML=`<p class="eyebrow">SHOWDOWN EQUITY</p>${equityStats(r)}<h3>Your final hand distribution</h3>${Object.entries(r.categories).map(([k,v])=>`<div class="bar-row"><span>${esc(k)}</span><progress value="${v}" max="1"></progress><span>${pct(v)}</span></div>`).join('')}<p class="fine">${esc(r.assumption)} Remaining combinations: ${r.range_combos.join(', ')}.</p>`;
});
async function loadOpponents(){
  ({opponents}=await api('opponents'));
  document.querySelectorAll('.opponent-select').forEach(select=>{const selected=select.value;const first=select.options[0].text;select.innerHTML=`<option value="">${esc(first)}</option>`+opponents.map(o=>`<option value="${esc(o.id)}">${esc(o.name)}</option>`).join('');select.value=selected;});
  $('#opponent-list').innerHTML=opponents.length?opponents.map(o=>`<article class="card"><h3>${esc(o.name)}</h3><p class="hint">${esc(o.profile.replaceAll('_',' '))} prior · all streets pooled below</p>${Object.entries(o.metrics).map(([k,m])=>`<div class="bar-row"><span>${esc(k.replaceAll('_',' '))}</span><progress value="${m.mean}" max="1"></progress><span>${pct(m.mean)}</span></div><p class="hint">${m.observations} observed opportunities · ${pct(m.interval95[0])}–${pct(m.interval95[1])} approximate interval · ${esc(m.confidence)} confidence</p>`).join('')}<p class="fine">Decision analysis uses observations for the entered street. Unspecified observations appear here but do not inform street-specific decisions.</p></article>`).join(''):'<div class="card result-card"><p class="eyebrow">NO OPPONENTS YET</p><h2>A read is a starting point.<br>Data gives it weight.</h2><p>Create a profile, then record observed opportunities. The probability estimate and its uncertainty update together.</p></div>';
}
bindForm('#opponent-form',async form=>{await api('opponents',formData(form));form.reset();await loadOpponents();},'Creating profile…');
bindForm('#observation-form',async form=>{const d=formData(form);d.success=d.success==='true';await api('observe',d);form.elements.note.value='';await loadOpponents();},'Saving observation…');
$('#export').addEventListener('click',async()=>{try{const data=await api('export');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='openpoker-research.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){status(e.message,true);}});
$('#solver-profile').addEventListener('change',e=>{const o=opponents.find(o=>o.id===e.target.value);if(o){$('#solver-form').elements.ip_bet.value=o.metrics.aggression.mean.toFixed(4);$('#solver-form').elements.ip_call.value=(1-o.metrics.fold_to_bet.mean).toFixed(4);}});
bindForm('#solver-form',async form=>{
  const d=formData(form,['pot','bet','iterations']);d.lock={};for(const k of ['ip_bet','ip_call']){if(d[k]!=='')d.lock[k]=Number(d[k]);delete d[k];}
  const r=await api('solve',d);const locked=Object.keys(r.lock).length>0;
  $('#solver-result').innerHTML=`<p class="eyebrow">${locked?'OPPONENT-LOCKED SCENARIO':'EQUILIBRIUM APPROXIMATION'}</p><div class="metrics">${metric(chips(r.value_oop),'OOP VALUE',true)}${metric(chips(r.nash_conv),'BEST-RESPONSE GAP',true)}${metric(r.deals,'LEGAL DEALS',true)}</div><p class="hint">${r.iterations.toLocaleString()} iterations. Values in chips, relative to half the existing pot. Smaller unlocked gap means less room for either player to improve.</p><h3>Out of position</h3><div class="scroll-table"><table><thead><tr><th>Hand</th><th>Bet</th><th>Call after checking</th></tr></thead><tbody>${r.oop.map(h=>`<tr><td>${esc(h.hand)}</td><td>${pct(h.bet)}</td><td>${pct(h.call_after_check)}</td></tr>`).join('')}</tbody></table></div><h3>In position</h3><div class="scroll-table"><table><thead><tr><th>Hand</th><th>Bet after check</th><th>Call</th></tr></thead><tbody>${r.ip.map(h=>`<tr><td>${esc(h.hand)}</td><td>${pct(h.bet_after_check)}</td><td>${pct(h.call)}</td></tr>`).join('')}</tbody></table></div>${locked?warnings([r.gap_note,'Locked frequencies apply equally across every hand. Interpret them as a scenario, not a discovered range-dependent policy.']):''}<p class="fine">${esc(r.scope)} Unreachable information sets may contain arbitrary strategies.</p>`;
},'Solving the river game… this can take a little while.');
function showGame(g){
  game=g;$('#game-controls').hidden=g.done;$('#acting-seat').textContent='Seat '+g.actor+' to act';
  if(!g.done){document.querySelectorAll('[data-action]').forEach(b=>b.disabled=!g.legal[b.dataset.action]);$('#raise-amount').min=g.legal.raise_min;$('#raise-amount').max=g.legal.raise_max;$('#raise-amount').value=g.legal.raise_min;document.querySelector('[data-action="call"]').textContent='Call '+g.legal.call;}
  $('#game-result').innerHTML=`<p class="eyebrow">${esc(g.street.toUpperCase())} · ${g.done?'HAND COMPLETE':'OPEN-CARD SANDBOX'}</p><h2>${g.pot} chips ${g.done?'settled':'in the pot'}</h2><div>${g.board.map(cardHtml).join('')||'<p class="hint">Community cards appear after preflop.</p>'}</div><div class="seats">${g.hands.map((h,i)=>`<div class="seat ${g.actor===i?'active-seat':''} ${g.folded[i]?'folded':''}"><h3>Seat ${i} ${g.button===i?'· Button':''}</h3><div>${h.map(cardHtml).join('')}</div><p>${g.stacks[i]} behind · ${g.committed[i]} committed</p><p>${g.folded[i]?'Folded':g.done?'Net: '+g.net[i]:g.stacks[i]===0?'All-in':'Street bet: '+g.street_bets[i]}</p></div>`).join('')}</div>${g.done?`<h3>Pot settlement</h3>${g.pots.map(p=>`<p class="hint">${p.amount} chips → seat ${p.winners.join(', ')}</p>`).join('')}`:''}<details><summary>Action history (${g.log.length})</summary>${g.log.map(a=>`<p class="hint">${esc(a.street)} · Seat ${a.seat}: ${esc(a.action)}${a.amount===null?'':' to '+a.amount}</p>`).join('')}</details>`;
}
bindForm('#game-form',async form=>{const d=formData(form,['button','seed']);d.stacks=d.stacks.split(',').map(Number);showGame(await api('game',d));},'Dealing…');
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;try{const g=await api('act',{id:game.id,action:b.dataset.action,amount:Number($('#raise-amount').value)});showGame(g);status();}catch(e){status(e.message,true);showGame(game);}}));
loadOpponents().catch(e=>status(e.message,true));
