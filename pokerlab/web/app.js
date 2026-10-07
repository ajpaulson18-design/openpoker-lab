"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = (v) => (v*100).toFixed(1)+'%';
const chips = (v) => Number(v).toFixed(2);
const exact = (v) => String(v);
let opponents = [], game = null, practiceOpponent = '';
$('#solver').append($('#river-explanation-template').content.cloneNode(true));
document.querySelector('#table .coach-toolbar').append(
  document.querySelector('#coach-voice-template').content.cloneNode(true));
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
function renderRiverExplanation(analysis,payload){
  const best=analysis.best_response;
  const baseline=Object.fromEntries(analysis.baseline_strategy.map(item=>[item.action,item.frequency]));
  const exploit=Object.fromEntries(analysis.exploitative_strategy.map(item=>[item.action,item.frequency]));
  const differences=Object.fromEntries(analysis.ev_differences.map(item=>[item.action,item.value]));
  const actionRows=analysis.action_evs.map(item=>`<tr><td>${esc(item.action)}</td><td class="num">${exact(item.value)}</td><td class="num">${exact(differences[item.action])}</td></tr>`).join('');
  const strategyRows=analysis.legal_actions.map(action=>`<tr><td>${esc(action)}</td><td class="num">${exact(baseline[action])}</td><td class="num">${exact(exploit[action])}</td></tr>`).join('');
  const assumptions=(analysis.opponent_assumptions||[]).map(item=>`<li><strong>${esc(item.tendency_id.replaceAll('_',' '))}</strong> at ${esc(item.node||'unspecified node')}: ${pct(item.value)} modeled from ${item.evidence_count} observed opportunities; reference ${item.baseline_frequency===null?'not supplied':pct(item.baseline_frequency)}, posterior ${item.posterior_mean===null?'not supplied':pct(item.posterior_mean)}, evidence weight ${item.confidence_weight===null?'not supplied':pct(item.confidence_weight)}. ${esc(item.reason||'')}</li>`).join('');
  const uncertainty=payload.uncertainty?`<p data-testid="explanation-uncertainty">${esc(payload.uncertainty.confidence)} uncertainty · ${pct(payload.uncertainty.level)} interval ${pct(payload.uncertainty.lower)}–${pct(payload.uncertainty.upper)} · ${esc(payload.uncertainty.method)}</p>`:'<p data-testid="explanation-uncertainty">No uncertainty interval was supplied for this analysis.</p>';
  return `<div data-testid="river-explanation-report" data-analysis-id="${esc(analysis.analysis_id)}" data-level="${esc(payload.level)}"><p class="eyebrow">REPLAYED RESTRICTED-RIVER ANALYSIS</p><div class="recommend" data-testid="explanation-recommendation"><span>BEST RESPONSE IN THIS MODELED SCENARIO</span><strong>${esc(best.action)}</strong></div><p data-testid="explanation-summary">${esc(payload.summary)}</p><p class="hint">${esc(payload.mathematical_reason)}</p><p class="hint" data-testid="explanation-confidence" data-confidence="${esc(analysis.confidence)}">Solver/model confidence: ${esc(analysis.confidence)}. This label is not a claim of predictive accuracy.</p><p class="fine">Stable analysis ID: <code data-testid="analysis-id">${esc(analysis.analysis_id)}</code> · Explanation level: <strong data-testid="explanation-level">${esc(payload.level)}</strong></p><h3>Action EVs</h3><p class="hint">Values are copied from the backend contract without recalculation or rounding. EV change is opponent-model EV minus reference EV.</p><table data-testid="action-evs"><thead><tr><th>Action</th><th>Opponent-model EV (chips)</th><th>EV change (chips)</th></tr></thead><tbody>${actionRows}</tbody></table><h3>Reference and opponent-adjusted strategies</h3><table data-testid="strategy-comparison"><thead><tr><th>Action</th><th>Reference frequency</th><th>Opponent-adjusted frequency</th></tr></thead><tbody>${strategyRows}</tbody></table><h3>Opponent-model inputs</h3><ul data-testid="model-assumptions">${assumptions||'<li>No supported opponent tendency matched this decision; the opponent-adjusted strategy equals the reference.</li>'}</ul><div class="river-uncertainty"><h3>Uncertainty</h3>${uncertainty}</div><h3>Scenario limitations and caveats</h3>${warnings(payload.caveats||[])||'<p class="hint">No additional caveats were supplied.</p>'}<details><summary>Inspect explanation provenance</summary><ul>${(payload.provenance||[]).map(item=>`<li>${esc(item.field)} · ${esc(item.source)} · ${esc(item.reference)}</li>`).join('')}</ul></details></div>`;
}
function setRiverExplanationState(state,content,busy=false){
  const result=$('#river-explanation-result');
  result.dataset.state=state;result.setAttribute('aria-busy',String(busy));result.innerHTML=content;
}
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
$('#river-explanation-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const explanationForm=event.currentTarget,solverForm=$('#solver-form');
  if(!explanationForm.reportValidity()||!solverForm.reportValidity())return;
  const button=explanationForm.querySelector('button[type="submit"]');
  button.disabled=true;status('Replaying the restricted river decision…');
  setRiverExplanationState('loading','<p class="eyebrow">REPLAY IN PROGRESS</p><h2>Calculating and explaining…</h2><p class="hint">The backend is replaying the supplied river scenario before generating its deterministic explanation.</p>',true);
  try{
    const source=formData(solverForm,['pot','bet','iterations']);
    const analysis=await api('exploit',{
      board:source.board,oop_range:source.oop_range,ip_range:source.ip_range,
      hero_hand:explanationForm.elements.hero_hand.value.trim(),
      opponent_id:$('#river-explanation-opponent').value,
      pot:source.pot,bet:source.bet,iterations:source.iterations,
      decision:explanationForm.elements.decision.value
    });
    if(!analysis.analysis_id||!analysis.best_response||!analysis.best_response.action)throw new Error('The replay did not return the required analysis facts.');
    const payload=await api('explain',{
      analysis,recommended_action:analysis.best_response.action,
      level:explanationForm.elements.level.value
    });
    if(payload.analysis_id!==analysis.analysis_id)throw new Error('The explanation analysis ID does not match the replay.');
    setRiverExplanationState('ready',renderRiverExplanation(analysis,payload));
    status('River explanation ready.');
  }catch(error){
    setRiverExplanationState('error',`<p class="eyebrow">EXPLANATION UNAVAILABLE</p><h2>Could not replay this decision.</h2><p role="alert">${esc(error.message||'Request failed.')}</p><p class="hint">Check the exact hero hand, compatible ranges, river board, and saved opponent model, then try again.</p>`);
    status(error.message||'Explanation request failed.',true);
  }finally{
    button.disabled=false;$('#river-explanation-result').setAttribute('aria-busy','false');
  }
});
function showGame(g){
  game=g;$('#game-controls').hidden=g.done;$('#acting-seat').textContent=g.done?'':g.actor_name+' to act · Seat '+g.actor;
  if(!g.done){document.querySelectorAll('[data-action]').forEach(b=>b.disabled=!g.legal[b.dataset.action]);$('#raise-amount').min=g.legal.raise_min;$('#raise-amount').max=g.legal.raise_max;$('#raise-amount').value=g.legal.raise_min;document.querySelector('[data-action="call"]').textContent='Call '+g.legal.call;}
  $('#game-result').innerHTML=`<p class="eyebrow">${esc(g.street.toUpperCase())} · ${g.done?'HAND COMPLETE':'PRACTICE TABLE'}</p><h2>${g.pot} chips ${g.done?'settled':'in the pot'}</h2><div>${g.board.map(cardHtml).join('')||'<p class="hint">Community cards appear after preflop.</p>'}</div><div class="seats">${g.hands.map((h,i)=>`<div class="seat ${g.actor===i?'active-seat':''} ${g.folded[i]?'folded':''}"><h3>${esc(g.names[i])} <span class="seat-number">· Seat ${i}${g.button===i?' · Button':''}</span></h3><div>${h?h.map(cardHtml).join(''):'<span class="unknown-cards">PRIVATE CARDS HIDDEN</span>'}</div><p>${g.stacks[i]} behind · ${g.committed[i]} committed</p><p>${g.folded[i]?'Folded':g.done?'Net: '+g.net[i]:g.stacks[i]===0?'All-in':'Street bet: '+g.street_bets[i]}</p></div>`).join('')}</div>${g.done?`<h3>Pot settlement</h3>${g.pots.map(p=>`<p class="hint">${p.amount} chips → ${p.winner_names.map(esc).join(', ')}</p>`).join('')}`:''}<details><summary>Action history (${g.log.length})</summary>${g.log.map(a=>`<p class="hint">${esc(a.street)} · ${esc(a.name)} (Seat ${a.seat}): ${esc(a.action)}${a.amount===null?'':' to '+a.amount}</p>`).join('')}</details>`;
}
function coachExplanation(payload){
  if(!payload)return '<p class="hint">Structured explanation unavailable for this historical result.</p>';
  const evidence=(payload.evidence||[]).map(item=>`<li>${esc(item.tendency_id.replaceAll('_',' '))}: ${pct(item.value)} from ${item.evidence_count} observed opportunities</li>`).join('');
  const alternatives=(payload.alternative_actions||[]).map(item=>`<tr><td>${esc(item.action)}</td><td>${chips(item.ev)}</td><td>${chips(item.ev_difference)}</td></tr>`).join('');
  return `<p>${esc(payload.summary)}</p><p class="hint">${esc(payload.mathematical_reason)}</p>${evidence?`<h4>Opponent evidence</h4><ul>${evidence}</ul>`:''}${alternatives?`<h4>Alternatives</h4><table><thead><tr><th>Action</th><th>EV</th><th>Difference</th></tr></thead><tbody>${alternatives}</tbody></table>`:''}${warnings(payload.caveats||[])}`;
}
function showCoach(result,chosen){
  if(!result){$('#coach-panel').innerHTML='<p class="hint">Blind Play is on. Analysis is still saved for review.</p>';return;}
  const loss=Math.max(0,result.actions[result.recommended]-result.actions[chosen]);
  const voice=result.personality?`<p>${esc(result.personality.text)}</p><p class="fine">${esc(result.personality.personality.replaceAll('_',' '))} · local deterministic renderer · analysis ${esc(result.personality.analysis_id)}</p>`:'';
  $('#coach-panel').innerHTML=`<p class="eyebrow">LIVE COACH · AFTER THE DECISION</p><div class="recommend"><span>YOU CHOSE ${esc(chosen.toUpperCase())} · ESTIMATED LOSS ${chips(loss)}</span><strong>${esc(result.recommended)}</strong></div><p>Baseline: <strong>${esc(result.baseline_recommended)}</strong> · Exploit: <strong>${esc(result.recommended)}</strong> · Confidence: ${esc(result.confidence)}</p>${voice}<details><summary>Explain</summary>${coachExplanation(result.explanation_payload)}</details>`;
}
async function loadReview(){
  const data=await api('session/'+game.id),r=data.review;
  const errors=r.biggest_errors.map(d=>`<li>${esc(d.street)}: ${esc(d.chosen_action)} lost ${chips(d.ev_loss)} chips versus ${esc(d.analysis_at_time.recommended)}</li>`).join('');
  const exploits=r.biggest_successful_exploits.map(d=>`<li>${esc(d.street)}: ${esc(d.chosen_action)} gained ${chips(d.exploit_gain||0)} chips versus the baseline action</li>`).join('');
  $('#session-review').hidden=false;
  $('#session-review').innerHTML=`<p class="eyebrow">SESSION REVIEW · ORIGINAL ANALYSIS PRESERVED</p><h3>${r.analyzed_decisions} analyzed decisions</h3><div class="metrics">${metric(r.matched_recommendation,'MATCHED')}${metric(r.meaningful_ev_losses,'EV MISTAKES')}${metric(chips(r.total_ev_loss),'TOTAL EV LOSS')}</div><p class="hint">Missed exploit opportunities: ${r.missed_exploitative_opportunities} · Successful exploits: ${r.successful_exploits}. Historical records keep their original analysis and opponent-model snapshot.</p>${errors?`<h3>Biggest errors</h3><ol>${errors}</ol>`:''}${exploits?`<h3>Biggest successful exploits</h3><ol>${exploits}</ol>`:''}`;
}
function updateButtonPlayers(){
  const names=$('#game-form').elements.names.value.split(',').map(s=>s.trim()).filter(Boolean);
  const select=$('#button-player'),current=select.value;
  select.innerHTML=names.map((name,i)=>`<option value="${i}">${esc(name||'Player '+(i+1))}</option>`).join('');
  if([...select.options].some(o=>o.value===current))select.value=current;
}
$('#game-form').elements.names.addEventListener('input',updateButtonPlayers);
bindForm('#game-form',async form=>{const d=formData(form,['button','seed']);d.names=d.names.split(',').map(s=>s.trim());d.stacks=d.stacks.split(',').map(Number);practiceOpponent=d.opponent_id;delete d.opponent_id;$('#session-review').hidden=true;$('#coach-panel').innerHTML='<p class="hint">Make a decision to receive post-action coaching.</p>';showGame(await api('game',d));},'Dealing…');
$('#coach-toggle').addEventListener('change',e=>{if(!e.target.checked)showCoach(null);});
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;const action=b.dataset.action;try{const g=await api('act',{id:game.id,action,amount:Number($('#raise-amount').value),opponent_id:practiceOpponent,coach_visible:$('#coach-toggle').checked,personality:$('#coach-personality').value});showGame(g);showCoach(g.coach,action);if(g.done)await loadReview();status();}catch(e){status(e.message,true);showGame(game);}}));
loadOpponents().catch(e=>status(e.message,true));
