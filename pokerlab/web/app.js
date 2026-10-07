"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = (v) => (v*100).toFixed(1)+'%';
const chips = (v) => Number(v).toFixed(2);
let opponents = [], game = null, practiceOpponent = '', pendingAction = null;
let activeHandId = null, selectedDecisionId = null, selectionGeneration = 0;
let liveDecisions = [], studyDecisions = [], studyTitle = '', studyPayload = null;
let selectedStudyCard = 'estimate', studyLoading = false, studyFailed = false;
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
function showCoach(result,decision){
  if(!result){$('#coach-panel').innerHTML='<p class="hint">Blind Play is on. Analysis is still saved for review.</p>';return;}
  const chosen=decision?.chosen_action_detail?.name||result.recommended;
  const assessed=decision?.assessment_status!=='unassessed_size'&&decision?.ev_loss!==null;
  const loss=assessed?chips(decision?.ev_loss??0):'raise size not evaluated';
  const voice=result.personality?`<p>${esc(result.personality.text)}</p><p class="fine">${esc(result.personality.personality.replaceAll('_',' '))} · local deterministic renderer · analysis ${esc(result.personality.analysis_id)}</p>`:'';
  const amount=decision?.chosen_action_detail?.amount;
  const choiceLabel=`YOU CHOSE ${esc(chosen.toUpperCase())}${chosen==='raise'?` TO ${esc(amount)}`:''} · ${assessed?`ESTIMATED LOSS ${loss}`:'RAISE SIZE NOT EVALUATED'}`;
  $('#coach-panel').innerHTML=`<p class="eyebrow">LIVE COACH · AFTER THE DECISION</p><div class="recommend"><span>${choiceLabel}</span><strong>${esc(result.recommended)}</strong></div><p>Baseline: <strong>${esc(result.baseline_recommended)}</strong> · Exploit: <strong>${esc(result.recommended)}</strong> · Confidence: ${esc(result.confidence)}</p>${voice}<details><summary>Explain</summary>${coachExplanation(result.explanation_payload)}</details>`;
}
function decisionLabel(decision){
  const detail=decision.chosen_action_detail||{};
  const action=detail.name||decision.chosen_action||'Decision';
  const amount=detail.amount;
  const exactRaise=action==='raise'&&Number.isFinite(amount);
  return `${decision.street||'Decision'} · ${action}${exactRaise?` to ${amount}`:''}`;
}
function invalidateDecisionStudy(){
  selectionGeneration++;selectedDecisionId=null;studyPayload=null;studyLoading=false;studyFailed=false;
  studyDecisions=[];$('#decision-study').hidden=true;$('#decision-study').innerHTML='';
}
function studyActionLabel(action){
  return action.name==='raise'&&action.amount!==null?`raise to ${action.amount}`:action.name;
}
function studyActionEv(action){
  const key=Object.hasOwn(action,'estimated_ev_chips')?'estimated_ev_chips':'estimated_ev';
  const value=action[key];return value===null||value===undefined?'Unavailable':`${chips(value)}${key==='estimated_ev_chips'?' chips':''}`;
}
function renderStudyPanel(){
  const panel=$('#decision-study');
  if(!studyDecisions.length){panel.hidden=true;panel.innerHTML='';return;}
  panel.hidden=false;
  const decisionButtons=studyDecisions.map(item=>{
    const id=String(item.decision_id||'');
    return `<button class="secondary" type="button" data-decision-id="${esc(id)}" aria-pressed="${id===selectedDecisionId}">${esc(decisionLabel(item))}</button>`;
  }).join('');
  let content='<p class="hint">Select a saved decision to open its study cards.</p>';
  if(studyLoading)content='<p class="hint" role="status">Loading saved decision study…</p>';
  else if(studyFailed)content=`<p class="hint">Could not load this study.</p><button class="secondary study-retry" type="button" data-retry-study>Retry</button>`;
  else if(studyPayload?.status==='unavailable')content=`<p class="hint">${esc(studyPayload.reason||'Study evidence is unavailable for this older decision.')}</p>`;
  else if(studyPayload?.status==='ready'){
    const cards=studyPayload.cards||[];
    const active=cards.find(card=>card.id===selectedStudyCard)||cards[0];
    const prompts=cards.map(card=>`<button type="button" class="secondary" data-study-card="${esc(card.id)}" aria-pressed="${card.id===active?.id}">${esc(card.question)}</button>`).join('');
    const rows=(studyPayload.modeled_actions||[]).map(action=>`<tr><td>${esc(studyActionLabel(action))}</td><td>${esc(studyActionEv(action))}</td></tr>`).join('');
    const baselineValueKey=studyPayload.baseline&&Object.hasOwn(studyPayload.baseline,'estimated_ev_chips')?'estimated_ev_chips':'estimated_ev';
    const baselineValue=studyPayload.baseline?.[baselineValueKey];
    const baseline=studyPayload.baseline?`<p class="hint">${esc(studyPayload.baseline.label)} recommends ${esc(studyPayload.baseline.recommended_action||'an unavailable action')}${baselineValue===null||baselineValue===undefined?'':` · ${chips(baselineValue)}${baselineValueKey==='estimated_ev_chips'?' chips':` in ${esc(studyPayload.baseline.ev_basis)}`}`}</p>`:'';
    const limitations=(studyPayload.limitations||[]).map(item=>`<li>${esc(item)}</li>`).join('');
    content=`<p class="eyebrow">${esc(studyPayload.heading)} · ${esc(studyPayload.source_label)}</p><div class="study-prompts" role="group" aria-label="Decision study prompts">${prompts}</div>${active?`<article class="study-answer" aria-live="polite"><h4>${esc(active.question)}</h4><p>${esc(active.answer)}</p></article>`:''}<h4>Modeled actions</h4><div class="study-alternatives"><table><thead><tr><th>Action</th><th>Estimated value</th></tr></thead><tbody>${rows}</tbody></table></div>${baseline}${limitations?`<h4>Limitations and caveats</h4><ul class="study-limits">${limitations}</ul>`:''}`;
  }
  panel.innerHTML=`<p class="eyebrow">DECISION STUDY</p><h3>${esc(studyTitle)}</h3><div class="decision-list" role="group" aria-label="Saved decisions">${decisionButtons}</div><div class="study-content">${content}</div>`;
}
async function selectDecisionStudy(decisionId){
  if(!decisionId||!studyDecisions.some(item=>item.decision_id===decisionId))return;
  selectedDecisionId=decisionId;selectedStudyCard='estimate';studyPayload=null;studyFailed=false;studyLoading=true;
  const handId=activeHandId,generation=++selectionGeneration;
  renderStudyPanel();
  try{
    const payload=await api(`v1/decisions/${encodeURIComponent(decisionId)}/study`);
    if(activeHandId!==handId||selectedDecisionId!==decisionId||generation!==selectionGeneration)return;
    studyPayload=payload;studyLoading=false;
    if(payload.status==='ready'&&payload.cards?.length)selectedStudyCard=payload.cards[0].id;
  }catch(e){
    if(activeHandId!==handId||selectedDecisionId!==decisionId||generation!==selectionGeneration)return;
    studyLoading=false;studyFailed=true;
  }
  renderStudyPanel();
}
function showDecisionStudy(decisions,title,selectId=null){
  studyDecisions=decisions.filter(item=>typeof item.decision_id==='string'&&item.decision_id);
  studyTitle=title;
  const requested=selectId||selectedDecisionId;
  const next=studyDecisions.some(item=>item.decision_id===requested)?requested:studyDecisions[studyDecisions.length-1]?.decision_id;
  if(next&&next!==selectedDecisionId){void selectDecisionStudy(next);return;}
  if(!next){invalidateDecisionStudy();return;}
  renderStudyPanel();
}
async function loadReview(handId=activeHandId){
  const data=await api('session/'+handId);
  if(activeHandId!==handId)return;
  const r=data.review;
  const errors=r.biggest_errors.map(d=>`<li>${esc(d.street)}: ${esc(d.chosen_action)} lost ${chips(d.ev_loss)} chips versus ${esc(d.analysis_at_time.recommended)}</li>`).join('');
  const exploits=r.biggest_successful_exploits.map(d=>`<li>${esc(d.street)}: ${esc(d.chosen_action)} gained ${chips(d.exploit_gain||0)} chips versus the baseline action</li>`).join('');
  $('#session-review').hidden=false;
  $('#session-review').innerHTML=`<p class="eyebrow">SESSION REVIEW · ORIGINAL ANALYSIS PRESERVED</p><h3>${r.analyzed_decisions} analyzed decisions</h3><p class="hint">${r.assessed_decisions} assessed · ${r.unassessed_decisions} unassessed. Raise sizes above the one modeled by practice are not scored.</p><div class="metrics">${metric(r.matched_recommendation,'MATCHED')}${metric(r.meaningful_ev_losses,'EV MISTAKES')}${metric(chips(r.total_ev_loss),'TOTAL EV LOSS')}</div><p class="hint">Missed exploit opportunities: ${r.missed_exploitative_opportunities} · Successful exploits: ${r.successful_exploits}. Historical records keep their original analysis and opponent-model snapshot.</p>${errors?`<h3>Biggest errors</h3><ol>${errors}</ol>`:''}${exploits?`<h3>Biggest successful exploits</h3><ol>${exploits}</ol>`:''}`;
  showDecisionStudy(data.decisions,'Completed hand · choose a decision',data.decisions[data.decisions.length-1]?.decision_id||null);
}
function updateButtonPlayers(){
  const names=$('#game-form').elements.names.value.split(',').map(s=>s.trim()).filter(Boolean);
  const select=$('#button-player'),current=select.value;
  select.innerHTML=names.map((name,i)=>`<option value="${i}">${esc(name||'Player '+(i+1))}</option>`).join('');
  if([...select.options].some(o=>o.value===current))select.value=current;
}
$('#game-form').elements.names.addEventListener('input',updateButtonPlayers);
bindForm('#game-form',async form=>{const d=formData(form,['button','seed']);d.names=d.names.split(',').map(s=>s.trim());d.stacks=d.stacks.split(',').map(Number);practiceOpponent=d.opponent_id;delete d.opponent_id;pendingAction=null;const dealt=await api('game',d);activeHandId=dealt.id;selectionGeneration++;selectedDecisionId=null;liveDecisions=[];studyDecisions=[];studyPayload=null;studyLoading=false;studyFailed=false;$('#session-review').hidden=true;$('#decision-study').hidden=true;$('#coach-panel').innerHTML='<p class="hint">Make a decision to receive post-action coaching.</p>';showGame(dealt);},'Dealing…');
$('#coach-toggle').addEventListener('change',e=>{if(!e.target.checked){showCoach(null);if(!game?.done)invalidateDecisionStudy();}else if(game&&!game.done&&liveDecisions.length)showDecisionStudy(liveDecisions,'Current hand · choose a decision',liveDecisions[liveDecisions.length-1].decision_id);});
$('#decision-study').addEventListener('click',e=>{
  const decisionButton=e.target.closest('[data-decision-id]');
  if(decisionButton){void selectDecisionStudy(decisionButton.dataset.decisionId);return;}
  const cardButton=e.target.closest('[data-study-card]');
  if(cardButton&&studyPayload?.status==='ready'){selectedStudyCard=cardButton.dataset.studyCard;renderStudyPanel();return;}
  if(e.target.closest('[data-retry-study]'))void selectDecisionStudy(selectedDecisionId);
});
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;const action=b.dataset.action;const amount=Number($('#raise-amount').value);const actingStreet=game.street;const requestKey=JSON.stringify([game.id,action,action==='raise'?amount:null,practiceOpponent,$('#coach-toggle').checked,$('#coach-personality').value,game.revision]);if(!pendingAction||pendingAction.key!==requestKey)pendingAction={key:requestKey,id:crypto.randomUUID()};try{const g=await api('act',{id:game.id,action,amount,opponent_id:practiceOpponent,coach_visible:$('#coach-toggle').checked,personality:$('#coach-personality').value,expected_revision:game.revision,client_action_id:pendingAction.id});pendingAction=null;if(g.decision)liveDecisions.push({decision_id:g.decision.decision_id,street:actingStreet,chosen_action:g.decision.chosen_action_detail?.name,chosen_action_detail:g.decision.chosen_action_detail,assessment_status:g.decision.assessment_status});showGame(g);showCoach(g.coach,g.decision);if(g.done)await loadReview(activeHandId);else if($('#coach-toggle').checked&&liveDecisions.length)showDecisionStudy(liveDecisions,'Current hand · choose a decision',g.decision?.decision_id);status();}catch(e){status(e.message,true);showGame(game);if(action==='raise')$('#raise-amount').value=amount;}finally{b.disabled=false;}}));
loadOpponents().catch(e=>status(e.message,true));
