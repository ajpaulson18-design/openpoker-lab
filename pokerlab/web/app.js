"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = (v) => (v*100).toFixed(1)+'%';
const chips = (v) => Number(v).toFixed(2);
let opponents = [], game = null, practiceOpponent = '', pendingAction = null;
let activeHandId = null, handGeneration = 0, selectedDecisionId = null, selectionGeneration = 0;
let liveDecisions = [], studyDecisions = [], studyTitle = '', studyPayload = null;
let latestCoachResult = null, latestCoachDecision = null;
let selectedStudyCard = 'estimate', studyLoading = false, studyFailed = false;
let externalAiAvailable = false, coachQuestionLoading = false, coachQuestionError = '';
let coachQuestionReply = null, lastCoachQuestion = null;
let coachDraft = {question:'',detail:'normal',audience:'standard',external:false};
document.querySelector('#table .coach-toolbar').append(
  document.querySelector('#coach-voice-template').content.cloneNode(true));
function status(message='', error=false) { $('#status').textContent=message; $('#status').classList.toggle('error',error); }
async function api(path,data,extraHeaders={}) {
  const response=await fetch('/api/'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json',...extraHeaders},body:JSON.stringify(data)});
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
  if(!result){
    $('#coach-panel').innerHTML=$('#coach-toggle').checked
      ?'<p class="hint">Live coaching was not requested for this decision. Its saved facts are available in the study cards.</p>'
      :'<p class="hint">Blind Play is on. Analysis is still saved for review.</p>';
    return;
  }
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
  coachQuestionLoading=false;coachQuestionError='';coachQuestionReply=null;lastCoachQuestion=null;
  coachDraft={question:'',detail:'normal',audience:'standard',external:false};
  studyDecisions=[];$('#decision-study').hidden=true;$('#decision-study').innerHTML='';
}
function studyActionLabel(action){
  return action.name==='raise'&&action.amount!==null?`raise to ${action.amount}`:action.name;
}
function studyActionEv(action){
  const key=Object.hasOwn(action,'estimated_ev_chips')?'estimated_ev_chips':'estimated_ev';
  const value=action[key];return value===null||value===undefined?'Unavailable':`${chips(value)}${key==='estimated_ev_chips'?' chips':''}`;
}
function coachFactLabel(kind){
  return ({street:'Street',hero_cards:'Your cards',board:'Board',current_pot:'Current pot',
    pot_basis:'Pot basis',source_kind:'Analysis source',ev_basis:'EV basis',
    modeled_action:'Modeled action',action_ev:'Modeled action EV',
    baseline_action_ev:'Baseline action EV',recommendation:'Saved recommendation',
    baseline_recommendation:'Baseline recommendation',baseline_label:'Baseline policy',
    choice:'Recorded choice',choice_loss:'Recorded choice loss',
    opponent_assumption:'Saved opponent assumption',opponent_uncertainty:'Opponent uncertainty',
    confidence_label:'Saved confidence',equity_standard_error:'Equity standard error',
    equity_exact:'Exact equity',solver_nash_conv:'NashConv',
    solver_exploitability:'Exploitability',solver_iterations:'Solver iterations',
    solver_gap_semantics:'Solver gap semantics'})[kind]||kind.replaceAll('_',' ');
}
function coachFactValue(fact){
  const value=fact.value;
  if(value===null||value===undefined)return 'Unavailable';
  if(fact.kind==='modeled_action'&&Array.isArray(value))return `${value[1]}${value[2]===null?'':` ${value[2]}`} (${value[3]})`;
  if(['action_ev','baseline_action_ev'].includes(fact.kind)&&Array.isArray(value))return `${value[0]}: ${value[1]===null?'Unavailable':value[1]}`;
  if(fact.kind==='choice'&&Array.isArray(value))return `${value[0]}${value[0]==='raise'?` to ${value[1]}`:''} · ${value[3].replaceAll('_',' ')}`;
  if(fact.kind==='opponent_assumption'&&Array.isArray(value))return `${value[0].replaceAll('_',' ')} · ${value[4]} · ${value[5]} observations`;
  if(Array.isArray(value))return value.join(' · ');
  if(typeof value==='boolean')return value?'Yes':'No';
  return String(value);
}
function sameCoachBinding(a,b){
  return !!a&&!!b&&a.hand_id===b.hand_id&&a.decision_id===b.decision_id
    &&a.evidence_id===b.evidence_id&&a.state_revision===b.state_revision;
}
function coachTeachingNoteHtml(result){
  const note=result.teaching_note,reply=result.reply||{};
  if(!note||note.schema_version!==1||typeof note.text!=='string'||note.text.length>600
    ||!Array.isArray(note.supporting_fact_ids)||!note.supporting_fact_ids.length
    ||!sameCoachBinding(note.binding,result.binding)
    ||!sameCoachBinding(note.binding,reply.binding))return '';
  const citations=note.supporting_fact_ids.map(id=>`<li>${esc(id)}</li>`).join('');
  return `<aside class="coach-teaching-note" aria-label="Local teaching note"><h5>LOCAL TEACHING NOTE · ${esc(note.source_label||'Saved analysis')}</h5><p>${esc(note.text)}</p><small>Supported by saved facts</small><ul>${citations}</ul></aside>`;
}
function coachReplyHtml(result){
  const reply=result.reply||{},blocks=(reply.blocks||[]).map(block=>{
    const facts=(block.facts||[]).map(fact=>`<li><strong>${esc(coachFactLabel(fact.kind))}:</strong> ${esc(coachFactValue(fact))}${fact.unit?` <span class="coach-unit">${esc(fact.unit)}</span>`:''}<small>Fact ${esc(fact.fact_id)}</small></li>`).join('');
    const caveats=(block.caveats||[]).map(item=>`<li>${esc(item)}</li>`).join('');
    return `<section class="ai-answer-block"><h5>${esc(block.label)}</h5>${facts?`<ul>${facts}</ul>`:''}${caveats?`<ul class="study-limits">${caveats}</ul>`:''}</section>`;
  }).join('');
  const caveats=(reply.caveats||[]).map(item=>`<li>${esc(item)}</li>`).join('');
  const origin=result.source==='openai'?'AI-selected plan · OpenAI':'Local fallback · no external AI answer';
  const fallback=result.fallback_reason?`<p class="hint">${esc(({external_ai_not_selected:'External AI was not selected.',external_ai_not_configured:'External AI is disabled or not configured locally.',refusal:'The provider declined this request.',incomplete:'The provider did not finish the response.',invalid_response:'The provider returned an incomplete response.',invalid_plan:'The selected plan did not pass validation.',http_error:'The provider request failed.',timeout:'The provider request timed out.',network_error:'The provider could not be reached.',provider_error:'The provider request failed safely.'})[result.fallback_reason]||'A local fallback was used.')}</p>`:'';
  return `<article class="ai-coach-reply" aria-live="polite"><p class="eyebrow">${esc(origin)} · ${esc(result.source_label||reply.source_label||'Saved analysis')}</p>${fallback}${coachTeachingNoteHtml(result)}${blocks}${caveats?`<h5>Limitations and caveats</h5><ul class="study-limits">${caveats}</ul>`:''}${result.retryable?'<button type="button" class="secondary" data-coach-retry>Retry question</button>':''}</article>`;
}
function coachQuestionHtml(){
  const error=coachQuestionError?`<p class="hint error" role="alert">${esc(coachQuestionError)}</p><button type="button" class="secondary" data-coach-retry>Retry question</button>`:'';
  const result=coachQuestionReply?coachReplyHtml(coachQuestionReply):'';
  return `<form id="study-coach-form" class="study-coach-form"><h4>Ask about this decision</h4><label>Question<textarea name="question" maxlength="500" required rows="3" placeholder="Ask one question about the saved decision">${esc(coachDraft.question)}</textarea></label><div class="two"><label>Detail<select name="detail"><option value="short"${coachDraft.detail==='short'?' selected':''}>Short</option><option value="normal"${coachDraft.detail==='normal'?' selected':''}>Normal</option><option value="technical"${coachDraft.detail==='technical'?' selected':''}>Technical</option></select></label><label>Audience<select name="audience"><option value="beginner"${coachDraft.audience==='beginner'?' selected':''}>Beginner</option><option value="standard"${coachDraft.audience==='standard'?' selected':''}>Standard</option></select></label></div><label class="toggle coach-external-opt-in"><input name="external" type="checkbox"${coachDraft.external?' checked':''}${externalAiAvailable?'':' disabled'}> Use external AI for this question</label><p class="hint">When selected, your question, hero cards, board, and other allowlisted facts for this decision are sent to OpenAI. Opponent hole cards, deck, names, and notes are excluded. External AI is off by default.</p>${!externalAiAvailable?'<p class="hint">External AI is disabled in local settings. You can still request a local fallback.</p>':''}<button class="primary" type="submit"${coachQuestionLoading?' disabled':''}>${coachQuestionLoading?'Asking…':'Ask question'}</button>${coachQuestionLoading?'<p class="hint" role="status">Preparing a grounded answer…</p>':''}${error}</form>${result}`;
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
    content=`<p class="eyebrow">${esc(studyPayload.heading)} · ${esc(studyPayload.source_label)}</p><div class="study-prompts" role="group" aria-label="Decision study prompts">${prompts}</div>${active?`<article class="study-answer" aria-live="polite"><h4>${esc(active.question)}</h4><p>${esc(active.answer)}</p></article>`:''}<h4>Modeled actions</h4><div class="study-alternatives"><table><thead><tr><th>Action</th><th>Estimated value</th></tr></thead><tbody>${rows}</tbody></table></div>${baseline}${limitations?`<h4>Limitations and caveats</h4><ul class="study-limits">${limitations}</ul>`:''}${coachQuestionHtml()}`;
  }
  panel.innerHTML=`<p class="eyebrow">DECISION STUDY</p><h3>${esc(studyTitle)}</h3><div class="decision-list" role="group" aria-label="Saved decisions">${decisionButtons}</div><div class="study-content">${content}</div>`;
}
async function selectDecisionStudy(decisionId){
  if(!decisionId||!studyDecisions.some(item=>item.decision_id===decisionId))return;
  selectedDecisionId=decisionId;selectedStudyCard='estimate';studyPayload=null;studyFailed=false;studyLoading=true;
  coachQuestionLoading=false;coachQuestionError='';coachQuestionReply=null;lastCoachQuestion=null;
  coachDraft={question:'',detail:'normal',audience:'standard',external:false};
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
function coachRequestSelectionMatches(captured){
  return activeHandId===captured.handId&&selectedDecisionId===captured.decisionId
    &&handGeneration===captured.handGeneration&&selectionGeneration===captured.generation;
}
function coachRequestMatches(captured,result){
  const binding=result?.binding;
  return coachRequestSelectionMatches(captured)&&binding
    &&binding.hand_id===captured.handId&&binding.decision_id===captured.decisionId
    &&binding.evidence_id===captured.evidenceId&&binding.state_revision===captured.revision;
}
async function askStudyCoach(retry=false){
  if(!studyPayload||studyPayload.status!=='ready'||!selectedDecisionId)return;
  const binding=studyPayload.binding;
  const request=retry&&lastCoachQuestion?lastCoachQuestion:{
    question:coachDraft.question.trim(),detail:coachDraft.detail,audience:coachDraft.audience,
    external:coachDraft.external,
  };
  if(!request.question||request.question.length>500){coachQuestionError='Enter a question from 1 to 500 characters.';renderStudyPanel();return;}
  const captured={handId:activeHandId,decisionId:selectedDecisionId,evidenceId:binding?.evidence_id,
    revision:binding?.state_revision,generation:selectionGeneration,handGeneration};
  if(!captured.handId||!captured.evidenceId){coachQuestionError='This study is missing its saved evidence binding.';renderStudyPanel();return;}
  lastCoachQuestion={...request};coachQuestionLoading=true;coachQuestionError='';coachQuestionReply=null;renderStudyPanel();
  try{
    const result=await api(`v1/decisions/${encodeURIComponent(captured.decisionId)}/coach`,{
      evidence_id:captured.evidenceId,question:request.question,detail:request.detail,audience:request.audience,
    },request.external?{'X-OpenPoker-External-AI':'1'}:{});
    if(!coachRequestSelectionMatches(captured))return;
    if(result.status==='failed'||result.status==='unavailable'){
      coachQuestionError=result.reason||result.error||'This decision cannot be used for a coach request.';
    }else{
      if(!coachRequestMatches(captured,result)){
        coachQuestionError='The answer did not match the selected decision. Refresh the study and try again.';
      }else coachQuestionReply=result;
    }
    coachQuestionLoading=false;
  }catch(error){
    if(activeHandId!==captured.handId||selectedDecisionId!==captured.decisionId
      ||handGeneration!==captured.handGeneration||selectionGeneration!==captured.generation)return;
    coachQuestionError=error.message||'Could not complete this request.';coachQuestionLoading=false;
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
$('#game-form').addEventListener('submit',async e=>{
  e.preventDefault();
  const form=e.target,button=form.querySelector('button[type="submit"],button.primary');
  button.disabled=true;status('Dealing…');
  const dealGeneration=++handGeneration;
  invalidateDecisionStudy();
  try{
    const d=formData(form,['button','seed']);d.names=d.names.split(',').map(s=>s.trim());d.stacks=d.stacks.split(',').map(Number);practiceOpponent=d.opponent_id;delete d.opponent_id;pendingAction=null;
    const dealt=await api('game',d);
    if(handGeneration!==dealGeneration)return;
    activeHandId=dealt.id;selectionGeneration++;selectedDecisionId=null;liveDecisions=[];studyDecisions=[];studyPayload=null;studyLoading=false;studyFailed=false;coachQuestionLoading=false;coachQuestionError='';coachQuestionReply=null;lastCoachQuestion=null;coachDraft={question:'',detail:'normal',audience:'standard',external:false};latestCoachResult=null;latestCoachDecision=null;$('#session-review').hidden=true;$('#decision-study').hidden=true;$('#coach-panel').innerHTML='<p class="hint">Make a decision to receive post-action coaching.</p>';showGame(dealt);status('Done. Results are ready.');
  }catch(err){
    if(handGeneration===dealGeneration){status(err.message,true);if(game)showGame(game);}
  }finally{
    if(handGeneration===dealGeneration)button.disabled=false;
  }
});
$('#coach-toggle').addEventListener('change',e=>{if(!e.target.checked){showCoach(null);if(!game?.done)invalidateDecisionStudy();}else if(game&&!game.done&&liveDecisions.length){showCoach(latestCoachResult,latestCoachDecision);showDecisionStudy(liveDecisions,'Current hand · choose a decision',liveDecisions[liveDecisions.length-1].decision_id);}});
$('#decision-study').addEventListener('click',e=>{
  const decisionButton=e.target.closest('[data-decision-id]');
  if(decisionButton){void selectDecisionStudy(decisionButton.dataset.decisionId);return;}
  const cardButton=e.target.closest('[data-study-card]');
  if(cardButton&&studyPayload?.status==='ready'){selectedStudyCard=cardButton.dataset.studyCard;renderStudyPanel();return;}
  if(e.target.closest('[data-retry-study]'))void selectDecisionStudy(selectedDecisionId);
  if(e.target.closest('[data-coach-retry]'))void askStudyCoach(true);
});
$('#decision-study').addEventListener('input',e=>{
  if(e.target.matches('[name="question"]'))coachDraft.question=e.target.value;
});
$('#decision-study').addEventListener('change',e=>{
  if(e.target.name==='detail')coachDraft.detail=e.target.value;
  if(e.target.name==='audience')coachDraft.audience=e.target.value;
  if(e.target.name==='external')coachDraft.external=e.target.checked;
});
$('#decision-study').addEventListener('submit',e=>{
  if(e.target.id!=='study-coach-form')return;
  e.preventDefault();
  coachDraft.question=e.target.elements.question.value;
  coachDraft.detail=e.target.elements.detail.value;
  coachDraft.audience=e.target.elements.audience.value;
  coachDraft.external=e.target.elements.external.checked;
  void askStudyCoach(false);
});
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',async()=>{
  const actingHandId=activeHandId,actingHandGeneration=handGeneration,actingGame=game;
  if(!actingHandId||!actingGame)return;
  b.disabled=true;
  const action=b.dataset.action,amount=Number($('#raise-amount').value),actingStreet=actingGame.street;
  const requestKey=JSON.stringify([actingGame.id,action,action==='raise'?amount:null,practiceOpponent,$('#coach-toggle').checked,$('#coach-personality').value,actingGame.revision]);
  if(!pendingAction||pendingAction.key!==requestKey)pendingAction={key:requestKey,id:crypto.randomUUID()};
  const actionRequest=pendingAction;
  try{
    const g=await api('act',{id:actingHandId,action,amount,opponent_id:practiceOpponent,coach_visible:$('#coach-toggle').checked,personality:$('#coach-personality').value,expected_revision:actingGame.revision,client_action_id:actionRequest.id});
    if(activeHandId!==actingHandId||handGeneration!==actingHandGeneration)return;
    if(pendingAction===actionRequest)pendingAction=null;
    latestCoachResult=g.coach||null;latestCoachDecision=g.decision||null;
    if(g.decision)liveDecisions.push({decision_id:g.decision.decision_id,street:actingStreet,chosen_action:g.decision.chosen_action_detail?.name,chosen_action_detail:g.decision.chosen_action_detail,assessment_status:g.decision.assessment_status});
    showGame(g);showCoach($('#coach-toggle').checked?g.coach:null,g.decision);
    if(g.done)await loadReview(actingHandId);
    else if($('#coach-toggle').checked&&liveDecisions.length)showDecisionStudy(liveDecisions,'Current hand · choose a decision',g.decision?.decision_id);
    status();
  }catch(e){
    if(activeHandId!==actingHandId||handGeneration!==actingHandGeneration)return;
    status(e.message,true);showGame(game);if(action==='raise')$('#raise-amount').value=amount;
  }finally{
    if(activeHandId===actingHandId&&handGeneration===actingHandGeneration)b.disabled=!game||game.done||!game.legal?.[action];
  }
}));
loadOpponents().catch(e=>status(e.message,true));
api('health').then(info=>{externalAiAvailable=info.external_ai_coach_available===true;if(selectedDecisionId)renderStudyPanel();}).catch(()=>{});
