"use strict";
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = (v) => (v*100).toFixed(1)+'%';
const chips = (v) => Number(v).toFixed(2);
let opponents = [], game = null, practiceOpponent = '', pendingAction = null;
let activeHandId = null, handGeneration = 0, selectedDecisionId = null, selectionGeneration = 0;
let liveDecisions = [], studyDecisions = [], studyTitle = '', studyPayload = null;
let latestCoachResult = null, latestCoachDecision = null;
let afterActionError = '', afterActionLoading = false;
let selectedStudyCard = 'estimate', studyLoading = false, studyFailed = false;
let externalAiAvailable = false, coachQuestionLoading = false, coachQuestionError = '';
let coachConversation = null, coachConversations = new Map(), lastCoachQuestion = null;
let coachConversationFull = false, coachConversationExpired = false;
let coachDraft = {question:'',detail:'normal',audience:'standard',external:false};
let currentStudyView = null, currentStudyRequest = null, currentStudyLoading = false, currentStudyError = '';
let currentStudyGeneration = 0, currentStudyOpponent = '';
let currentCoachDraft={question:'',detail:'normal',audience:'standard',external:false};
let currentCoachResult=null,currentCoachError='',currentCoachLoading=false,currentCoachNeedsRefresh=false;
let currentCoachConversation=null,currentCoachFull=false,currentCoachStartNew=false,currentCoachRetry=null;
let currentCoachRequest=null,currentCoachGeneration=0;
document.querySelector('#table .coach-toolbar').append(
  document.querySelector('#coach-voice-template').content.cloneNode(true));
function status(message='', error=false) { $('#status').textContent=message; $('#status').classList.toggle('error',error); }
async function api(path,data,extraHeaders={}) {
  const response=await fetch('/api/'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json',...extraHeaders},body:JSON.stringify(data)});
  const result=await response.json(); if(!response.ok){const error=new Error(result.error||'Request failed.');error.code=result.code;error.status=response.status;throw error;} return result;
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
  if((currentStudyView&&(currentStudyView.binding.hand_id!==g.id||currentStudyView.binding.state_revision!==g.revision))
      ||(currentStudyRequest&&(currentStudyRequest.hand_id!==g.id||currentStudyRequest.revision!==g.revision)))clearCurrentStudy();
  game=g;$('#game-controls').hidden=g.done;$('#acting-seat').textContent=g.done?'':g.actor_name+' to act · Seat '+g.actor;
  if(!g.done){document.querySelectorAll('[data-action]').forEach(b=>b.disabled=!g.legal[b.dataset.action]);$('#raise-amount').min=g.legal.raise_min;$('#raise-amount').max=g.legal.raise_max;$('#raise-amount').value=g.legal.raise_min;document.querySelector('[data-action="call"]').textContent='Call '+g.legal.call;}
  $('#game-result').innerHTML=`<p class="eyebrow">${esc(g.street.toUpperCase())} · ${g.done?'HAND COMPLETE':'PRACTICE TABLE'}</p><h2>${g.pot} chips ${g.done?'settled':'in the pot'}</h2><div>${g.board.map(cardHtml).join('')||'<p class="hint">Community cards appear after preflop.</p>'}</div><div class="seats">${g.hands.map((h,i)=>`<div class="seat ${g.actor===i?'active-seat':''} ${g.folded[i]?'folded':''}"><h3>${esc(g.names[i])} <span class="seat-number">· Seat ${i}${g.button===i?' · Button':''}</span></h3><div>${h?h.map(cardHtml).join(''):'<span class="unknown-cards">PRIVATE CARDS HIDDEN</span>'}</div><p>${g.stacks[i]} behind · ${g.committed[i]} committed</p><p>${g.folded[i]?'Folded':g.done?'Net: '+g.net[i]:g.stacks[i]===0?'All-in':'Street bet: '+g.street_bets[i]}</p></div>`).join('')}</div>${g.done?`<h3>Pot settlement</h3>${g.pots.map(p=>`<p class="hint">${p.amount} chips → ${p.winner_names.map(esc).join(', ')}</p>`).join('')}`:''}<details><summary>Action history (${g.log.length})</summary>${g.log.map(a=>`<p class="hint">${esc(a.street)} · ${esc(a.name)} (Seat ${a.seat}): ${esc(a.action)}${a.amount===null?'':' to '+a.amount}</p>`).join('')}</details>`;
  renderCurrentStudy();
}
function clearCurrentCoach(){currentCoachGeneration++;currentCoachResult=null;currentCoachError='';currentCoachLoading=false;currentCoachNeedsRefresh=false;currentCoachRequest=null;currentCoachConversation=null;currentCoachFull=false;currentCoachStartNew=false;currentCoachRetry=null;currentCoachDraft={question:'',detail:'normal',audience:'standard',external:false};}
function clearCurrentStudy(){currentStudyGeneration++;currentStudyView=null;currentStudyRequest=null;currentStudyLoading=false;currentStudyError='';clearCurrentCoach();renderCurrentStudy();}
function renderCurrentStudy(){
  const panel=$('#current-study');if(!panel)return;
  const visible=Boolean(game&&!game.done&&game.actor===0&&activeHandId===game.id&&$('#coach-toggle').checked);
  panel.hidden=!visible;if(!visible){panel.innerHTML='';return;}
  if(currentStudyLoading){panel.innerHTML='<p class="hint" role="status">Calculating a local practice estimate…</p>';return;}
  if(currentStudyError){panel.innerHTML=`<p class="current-study-error" role="alert">${esc(currentStudyError)}</p><button class="secondary" data-study-current-retry>Retry study preview</button>`;return;}
  if(!currentStudyView){panel.innerHTML='<button class="secondary" data-study-current>Study current decision</button><p class="hint">Optional local estimate. Nothing is calculated until you ask.</p>';return;}
  const v=currentStudyView,ctx=v.context;
  const actions=v.modeled_actions.map(a=>`<li><strong>${esc(a.name)}${a.amount===null?'':` ${a.amount_semantics==='street_total'?'to':'+'}${esc(a.amount)}`}</strong> · ${a.estimated_ev_chips===null?'EV unavailable':`${chips(a.estimated_ev_chips)} estimated chips`}${a.action_id===v.recommended_action_id?' · recommended':''}${a.size_note?`<br><span class="hint">${esc(a.size_note)}${a.maximum_legal_total===null?'':` Legal raise totals: ${esc(a.minimum_legal_total)}–${esc(a.maximum_legal_total)}.`}</span>`:''}</li>`).join('');
  const turns=currentCoachConversation?.turns||[];
  const turnList=turns.length?`<section class="current-coach-turns" aria-label="Questions about this preview"><h4>Questions about this preview</h4>${turns.map((turn,index)=>`<article class="current-coach-turn"><p class="eyebrow">Turn ${index+1} · ${turn.response?.source==='openai'?'External AI':'Local response'}</p><p class="current-coach-question"><strong>Question:</strong> ${esc(turn.question)}</p>${coachReplyHtml(turn.response,true)}</article>`).join('')}${turns.length<4?'<div class="current-coach-followups"><button type="button" class="secondary" data-current-coach-followup="simpler">Simpler</button><button type="button" class="secondary" data-current-coach-followup="deeper">Go deeper</button></div>':''}${currentCoachFull?'<p class="hint">This conversation has four turns.</p><button type="button" class="secondary" data-current-coach-new>Start new conversation</button>':''}</section>`:'';
  const coachError=currentCoachError?`<p class="current-study-error" role="alert">${esc(currentCoachError)}</p>${currentCoachNeedsRefresh?'<button type="button" class="secondary" data-study-current-retry>Refresh preview</button>':currentCoachStartNew?'<button type="button" class="secondary" data-current-coach-new>Start new conversation</button>':'<button type="button" class="secondary" data-current-coach-retry>Retry question</button>'}`:'';
  const fullNotice=currentCoachFull&&!turns.length?'<p class="hint">This conversation has four turns.</p><button type="button" class="secondary" data-current-coach-new>Start new conversation</button>':'';
  panel.innerHTML=`<div class="current-study-view"><p class="eyebrow">${esc(v.source_label)}</p><h4>${esc(v.heading)}</h4><p>${esc(ctx.street)} · Your cards ${ctx.hero_cards.map(cardHtml).join(' ')} · Pot ${esc(ctx.pot_chips)} chips</p>${ctx.board.length?`<p>Board ${ctx.board.map(cardHtml).join(' ')}</p>`:''}<ul class="current-study-actions">${actions}</ul><h4>Assumptions</h4>${warnings(v.assumptions)}<h4>Limits</h4>${warnings(v.limitations)}<p class="fine">Preview only · revision ${esc(v.binding.state_revision)}</p></div><button class="secondary" data-study-current-retry>Refresh preview</button>${turnList}<form id="current-coach-form" class="current-coach-form"><h4>${turns.length?'Ask a follow-up about this decision':'Ask one question about this decision'}</h4><label>Question<textarea name="question" maxlength="500" required rows="3" placeholder="Ask about this current unplayed decision">${esc(currentCoachDraft.question)}</textarea></label><div class="two"><label>Detail<select name="detail"><option value="short"${currentCoachDraft.detail==='short'?' selected':''}>Short</option><option value="normal"${currentCoachDraft.detail==='normal'?' selected':''}>Normal</option><option value="technical"${currentCoachDraft.detail==='technical'?' selected':''}>Technical</option></select></label><label>Audience<select name="audience"><option value="beginner"${currentCoachDraft.audience==='beginner'?' selected':''}>Beginner</option><option value="standard"${currentCoachDraft.audience==='standard'?' selected':''}>Standard</option></select></label></div><label class="toggle coach-external-opt-in"><input name="external" type="checkbox"${currentCoachDraft.external?' checked':''}${externalAiAvailable?'':' disabled'}> Use external AI for this question</label><p class="hint">External AI is off by default for every turn. When selected, this question, the current preview's allowlisted facts, and up to two recent questions for this same preview may be sent. Opponent cards are never sent.</p>${!externalAiAvailable?'<p class="hint">External AI is disabled in local settings. You can still request a local response.</p>':''}<button class="primary" type="submit"${currentCoachLoading||currentCoachNeedsRefresh||currentCoachFull||currentCoachStartNew?' disabled':''}>${currentCoachLoading?'Preparing answer…':'Ask question'}</button>${currentCoachLoading?'<p class="hint" role="status">Preparing an answer tied to this preview…</p>':''}${coachError}${fullNotice}</form>`;
}
async function requestCurrentStudy(){
  if(!game||game.done||game.actor!==0||!activeHandId||pendingAction||!$('#coach-toggle').checked)return;
  const handId=activeHandId,revision=game.revision,generation=++currentStudyGeneration,opponentId=practiceOpponent||null;
  clearCurrentCoach();
  currentStudyOpponent=practiceOpponent;currentStudyRequest={hand_id:handId,revision};currentStudyView=null;currentStudyError='';currentStudyLoading=true;renderCurrentStudy();
  try{
    const view=await api(`v1/hands/${encodeURIComponent(handId)}/current-study`,{expected_revision:revision,opponent_id:opponentId});
    const binding=view?.binding;
    if(view?.status!=='ready'||view?.schema_version!==1||!binding||binding.hand_id!==handId||binding.state_revision!==revision
        ||typeof binding.decision_id!=='string'||!binding.decision_id.trim()
        ||typeof binding.evidence_id!=='string'||!binding.evidence_id.trim())throw new Error('Study preview did not match this hand. Try again.');
    if(currentStudyGeneration!==generation||activeHandId!==handId||game?.id!==handId||game?.revision!==revision||practiceOpponent!==currentStudyOpponent||!$('#coach-toggle').checked)return;
    currentStudyView=view;
  }catch(error){
    if(currentStudyGeneration!==generation||activeHandId!==handId||game?.revision!==revision||practiceOpponent!==currentStudyOpponent||!$('#coach-toggle').checked)return;
    currentStudyError=error.message;
  }finally{
    if(currentStudyGeneration===generation){currentStudyRequest=null;currentStudyLoading=false;renderCurrentStudy();}
  }
}
async function askCurrentCoach(){
  if(!game||game.done||game.actor!==0||pendingAction||!activeHandId
      ||!currentStudyView||!$('#coach-toggle').checked||currentCoachLoading||currentCoachNeedsRefresh)return;
  const target={...currentStudyView.binding};
  const handId=activeHandId,revision=game.revision,generation=++currentCoachGeneration;
  let retry=currentCoachRetry;
  if(retry&&(retry.payload.question!==currentCoachDraft.question.trim()
      ||retry.payload.detail!==currentCoachDraft.detail
      ||retry.payload.audience!==currentCoachDraft.audience
      ||retry.external!==currentCoachDraft.external)){
    currentCoachRetry=null;retry=null;
  }
  if(!retry){
    const question=currentCoachDraft.question.trim();
    if(!question)return;
    const payload={client_turn_id:crypto.randomUUID(),target,question,
      detail:currentCoachDraft.detail,audience:currentCoachDraft.audience};
    if(currentCoachConversation?.conversation_id)payload.conversation_id=currentCoachConversation.conversation_id;
    retry={payload,external:currentCoachDraft.external};
    currentCoachRetry=retry;
  }
  const {payload,external}=retry;
  currentCoachRequest={...target};currentCoachResult=null;currentCoachError='';currentCoachLoading=true;renderCurrentStudy();
  try{
    const result=await api(`v1/hands/${encodeURIComponent(handId)}/current-coach/turns`,
      payload,external?{'X-OpenPoker-External-AI':'1'}:{});
    const reply=result?.reply,forbidden=(reply?.blocks||[]).flatMap(block=>block.facts||[])
      .some(fact=>fact.kind==='choice'||fact.kind==='choice_loss');
    const previousTurns=currentCoachConversation?.turns||[];
    const priorTurn=previousTurns.find(turn=>turn.clientTurnId===payload.client_turn_id);
    const expectedTurnIndex=priorTurn?.turnIndex??previousTurns.length+1;
    if(!['ready','fallback'].includes(result?.status)
        ||typeof result.conversation_id!=='string'||!result.conversation_id
        ||(payload.conversation_id&&result.conversation_id!==payload.conversation_id)
        ||result.client_turn_id!==payload.client_turn_id
        ||!Number.isInteger(result.turn_index)||result.turn_index!==expectedTurnIndex
        ||(currentCoachConversation&&currentCoachConversation.conversation_id!==result.conversation_id)
        ||!sameCoachBinding(result.binding,target)||!sameCoachBinding(reply?.binding,target)
        ||reply?.schema_version!==1||!['recommendation','limits','unavailable'].includes(reply?.intent)
        ||!Array.isArray(reply?.unavailable_fields)||!reply.unavailable_fields.includes('choice')
        ||!reply.unavailable_fields.includes('choice_loss')||forbidden)
      throw new Error('The answer did not match this unplayed preview. Refresh the preview and ask again.');
    if(currentCoachGeneration!==generation||currentCoachRetry?.payload.client_turn_id!==payload.client_turn_id
        ||activeHandId!==handId||game?.id!==handId
        ||game?.revision!==revision||!currentStudyView
        ||!sameCoachBinding(currentStudyView.binding,target)||!$('#coach-toggle').checked)return;
    currentCoachResult=result;
    currentCoachConversation??={conversation_id:result.conversation_id,turns:[]};
    if(!currentCoachConversation.turns.some(turn=>turn.clientTurnId===result.client_turn_id))
      currentCoachConversation.turns.push({clientTurnId:result.client_turn_id,
        turnIndex:result.turn_index,question:payload.question,response:result});
    currentCoachFull=currentCoachConversation.turns.length>=4;
    currentCoachRetry=null;currentCoachStartNew=false;currentCoachDraft.external=false;
  }catch(error){
    if(currentCoachGeneration!==generation||activeHandId!==handId||game?.revision!==revision
        ||!currentStudyView||!sameCoachBinding(currentStudyView.binding,target)
        ||!$('#coach-toggle').checked)return;
    currentCoachError=error.message;
    currentCoachNeedsRefresh=error.code==='preview_expired'||error.code==='stale_context';
    currentCoachFull=error.code==='conversation_full';
    currentCoachStartNew=error.code==='conversation_expired'||error.code==='conversation_full';
  }finally{
    if(currentCoachGeneration===generation){currentCoachRequest=null;currentCoachLoading=false;renderCurrentStudy();}
  }
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
  const afterAction=decision?.decision_id?`<button type="button" class="secondary" data-explain-latest-action${afterActionLoading?' disabled':''}>${afterActionLoading?'Loading saved explanation…':afterActionError?'Retry explanation':'Explain my action (local)'}</button><p class="hint">Uses this decision\'s saved evidence. External AI stays off unless you select it for a separate question.</p>${afterActionError?`<p class="hint error" role="alert">${esc(afterActionError)}</p>`:''}`:'';
  $('#coach-panel').innerHTML=`<p class="eyebrow">LIVE COACH · AFTER THE DECISION</p><div class="recommend"><span>${choiceLabel}</span><strong>${esc(result.recommended)}</strong></div><p>Baseline: <strong>${esc(result.baseline_recommended)}</strong> · Exploit: <strong>${esc(result.recommended)}</strong> · Confidence: ${esc(result.confidence)}</p>${voice}<details><summary>Explain</summary>${coachExplanation(result.explanation_payload)}</details>${afterAction}`;
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
  coachQuestionLoading=false;coachQuestionError='';coachConversation=null;coachConversationFull=false;coachConversationExpired=false;lastCoachQuestion=null;
  coachDraft={question:'',detail:'normal',audience:'standard',external:false};
  studyDecisions=[];$('#decision-study').hidden=true;$('#decision-study').innerHTML='';
}
function studyActionLabel(action){
  return action.name==='raise'&&action.amount!==null?`raise to ${action.amount}`:action.name;
}
function studyActionEv(action){
  const key=Object.hasOwn(action,'estimated_ev_chips')?'estimated_ev_chips':'estimated_ev';
  const value=action[key];return value===null||value===undefined?'Unavailable':`${chips(value)} ${key==='estimated_ev_chips'?'chips':coachEvBasisLabel(studyPayload?.ev_basis)}`;
}
function coachEvBasisLabel(basis){
  return basis==='incremental_decision_chips'?'estimated chips from this decision'
    :basis==='half_initial_pot_utility'?'solver chip utility relative to half the starting pot'
    :String(basis||'').replaceAll('_',' ');
}
function coachFactUnit(unit,result){
  if(unit==='incremental_decision_chips'||unit==='half_initial_pot_utility')return coachEvBasisLabel(unit);
  if(unit==='basis'||unit==='source'||unit==='street'||unit==='action'||unit==='action_id'||unit==='policy'
      ||unit==='choice'||unit==='assumption'||unit==='semantics'||unit==='label'||!unit)return '';
  if(unit==='ev')return (result?.source_label||result?.reply?.source_label||'').startsWith('Restricted')
    ?coachEvBasisLabel('half_initial_pot_utility'):'EV units';
  if(unit==='standard_error')return '';
  if(unit==='interval')return 'probability interval';
  return String(unit).replaceAll('_',' ');
}
function coachFixed(value){return typeof value==='number'&&Number.isFinite(value)?value.toFixed(2):String(value);}
function coachPercent(value){return typeof value==='number'&&Number.isFinite(value)?pct(value):String(value);}
function coachSolverDiagnostic(value){
  if(typeof value==='number'&&Number.isFinite(value)&&value!==0&&Math.abs(value)<0.005)
    return value>0?'less than 0.01':'greater than -0.01';
  return coachFixed(value);
}
function coachFactLabel(kind,currentPreview=false){
  if(currentPreview&&kind==='recommendation')return 'Current modeled recommendation';
  return ({street:'Street',hero_cards:'Your cards',board:'Board',current_pot:'Current pot',
    pot_basis:'Pot basis',source_kind:'Analysis source',ev_basis:'Value basis',
    modeled_action:'Modeled action',action_ev:'Modeled action EV',
    baseline_action_ev:'Baseline action EV',recommendation:'Saved recommendation',
    baseline_recommendation:'Baseline recommendation',baseline_label:'Baseline policy',
    choice:'Recorded choice',choice_loss:'Recorded choice loss',
    opponent_assumption:'Saved opponent assumption',opponent_uncertainty:'Opponent uncertainty',
    confidence_label:'Saved confidence',equity_standard_error:'Equity estimate uncertainty',
    equity_exact:'Exact equity',solver_nash_conv:'NashConv',
    solver_exploitability:'Exploitability',solver_iterations:'Solver iterations',
    solver_gap_semantics:'Solver gap semantics'})[kind]||kind.replaceAll('_',' ');
}
function coachFactValue(fact,actionLabels=new Map()){
  const value=fact.value;
  if(value===null||value===undefined)return 'Unavailable';
  if(fact.kind==='modeled_action'&&Array.isArray(value))return coachActionLabel(value);
  if(fact.kind==='source_kind')return ({practice_estimate:'Practice estimate',restricted_equilibrium:'Restricted equilibrium result',restricted_exploit:'Restricted exploit estimate'})[value]||String(value).replaceAll('_',' ');
  if(fact.kind==='ev_basis')return coachEvBasisLabel(value);
  if(['recommendation','baseline_recommendation'].includes(fact.kind))return actionLabels.get(value)||'Modeled action';
  if(['action_ev','baseline_action_ev'].includes(fact.kind)&&Array.isArray(value))return `${actionLabels.get(value[0])||'Modeled action'}: ${value[1]===null?'Unavailable':coachFixed(value[1])}`;
  if(fact.kind==='choice'&&Array.isArray(value))return `${value[0]}${value[0]==='raise'?` to ${value[1]}`:''} · ${value[3]==='unassessed_size'?'size not evaluated':'assessed'}`;
  if(fact.kind==='choice_loss')return coachFixed(value);
  if(fact.kind==='opponent_assumption'&&Array.isArray(value))return `${value[0].replaceAll('_',' ')} · ${coachPercent(value[4])} · ${value[5]} observations`;
  if(fact.kind==='opponent_uncertainty'&&Array.isArray(value))return `${coachPercent(value[0])}–${coachPercent(value[1])} · ${value[4]}`;
  if(fact.kind==='equity_standard_error')return coachPercent(value);
  if(['solver_nash_conv','solver_exploitability'].includes(fact.kind))return coachSolverDiagnostic(value);
  if(fact.kind==='current_pot')return coachFixed(value);
  if(Array.isArray(value))return value.join(' · ');
  if(typeof value==='boolean')return value?'Yes':'No';
  if(typeof value==='number')return coachFixed(value);
  return String(value);
}
function coachActionLabel(value){
  if(!Array.isArray(value)||typeof value[1]!=='string')return 'Modeled action';
  if(value[1]!=='raise'||value[2]===null)return value[1];
  return `${value[3]==='street_total'?'raise to':'raise by'} ${value[2]}`;
}
function sameCoachBinding(a,b){
  return !!a&&!!b&&a.hand_id===b.hand_id&&a.decision_id===b.decision_id
    &&a.evidence_id===b.evidence_id&&a.state_revision===b.state_revision;
}
function coachTeachingNoteMarkup(result,currentPreview){
  const note=result.teaching_note,reply=result.reply||{};
  if(!note||note.schema_version!==1||typeof note.text!=='string'||note.text.length>600
    ||!Array.isArray(note.supporting_fact_ids)||!note.supporting_fact_ids.length
    ||!sameCoachBinding(note.binding,result.binding)
    ||!sameCoachBinding(note.binding,reply.binding))return '';
  return `<aside class="coach-teaching-note" aria-label="Local teaching note"><h5>LOCAL TEACHING NOTE · ${esc(note.source_label||(currentPreview?'Current practice preview':'Saved analysis'))}</h5><p>${esc(note.text)}</p><small>Supported by ${currentPreview?'preview':'saved'} facts</small></aside>`;
}
function coachTeachingNoteHtml(result){return coachTeachingNoteMarkup(result,false);}
function currentCoachTeachingNoteHtml(result){return coachTeachingNoteMarkup(result,true);}
function coachReplyHtml(result,currentPreview=false){
  const reply=result.reply||{},blocks=(reply.blocks||[]).map(block=>{
    const blockFacts=block.facts||[];
    const actionLabels=new Map(blockFacts.filter(fact=>fact.kind==='modeled_action'&&Array.isArray(fact.value))
      .map(fact=>[fact.value[0],coachActionLabel(fact.value)]));
    const facts=blockFacts.map(fact=>`<li><strong>${esc(coachFactLabel(fact.kind,currentPreview))}:</strong> ${esc(coachFactValue(fact,actionLabels))}${coachFactUnit(fact.unit,result)?` <span class="coach-unit">${esc(coachFactUnit(fact.unit,result))}</span>`:''}</li>`).join('');
    const caveats=(block.caveats||[]).map(item=>`<li>${esc(item)}</li>`).join('');
    return `<section class="ai-answer-block"><h5>${esc(block.label)}</h5>${facts?`<ul>${facts}</ul>`:''}${caveats?`<ul class="study-limits">${caveats}</ul>`:''}</section>`;
  }).join('');
  const caveats=(reply.caveats||[]).map(item=>`<li>${esc(item)}</li>`).join('');
  const origin=result.source==='openai'?'AI-selected plan · OpenAI':'Local explanation · OpenPoker renders validated facts';
  const reason=result.fallback_reason;
  const fallbackMessages={external_ai_not_configured:'External AI was requested but is disabled or not configured locally.',refusal:'External AI was requested, but the provider declined this question.',incomplete:'External AI was requested, but the provider did not finish the response.',invalid_response:'External AI was requested, but the provider returned an incomplete response.',invalid_plan:'External AI was requested, but its plan did not pass validation.',http_error:'External AI was requested, but the provider request failed.',timeout:'External AI was requested, but the provider request timed out.',network_error:'External AI was requested, but the provider could not be reached.',provider_error:'External AI was requested, but the provider request failed safely.'};
  const fallback=fallbackMessages[reason]?`<p class="hint">${esc(fallbackMessages[reason])} OpenPoker prepared this local explanation from the validated facts.</p>`:'';
  const planScope=result.source==='openai'
    ?'<p class="hint">OpenAI selected a plan from the allowed facts; OpenPoker renders the answer from the validated evidence.</p>'
    :'<p class="hint">OpenPoker selected and rendered this explanation from the validated evidence.</p>';
  const evidenceFacts=new Map((reply.blocks||[]).flatMap(block=>(block.facts||[]).map(fact=>[fact.fact_id,fact])));
  const note=result.teaching_note;
  if(note&&Array.isArray(note.supporting_fact_ids))for(const id of note.supporting_fact_ids)
    if(!evidenceFacts.has(id))evidenceFacts.set(id,{fact_id:id,kind:'supporting evidence'});
  const evidence=[...evidenceFacts.values()].map(fact=>`<li><strong>${esc(coachFactLabel(fact.kind,currentPreview))}:</strong> ${esc(fact.fact_id)}</li>`).join('');
  const evidenceDetails=evidence?`<details class="coach-evidence-details"><summary>Evidence details</summary><p>References point to facts from this ${currentPreview?'current preview':'saved decision'}, bound to its evidence version.</p><ul>${evidence}</ul></details>`:'';
  const localScope=currentPreview&&typeof result.local_scope==='string'?`<p class="hint">${esc(result.local_scope)}</p>`:'';
  const answer=currentPreview
    ?`<article class="ai-coach-reply"><p class="eyebrow">${esc(origin)} · ${esc(result.source_label||reply.source_label||'Current practice preview')}</p>${fallback}${planScope}${localScope}${currentCoachTeachingNoteHtml(result)}${blocks}${evidenceDetails}${caveats?`<h5>Limitations and caveats</h5><ul class="study-limits">${caveats}</ul>`:''}</article>`
    :`<article class="ai-coach-reply"><p class="eyebrow">${esc(origin)} · ${esc(result.source_label||reply.source_label||'Saved analysis')}</p>${fallback}${planScope}${coachTeachingNoteHtml(result)}${blocks}${evidenceDetails}${caveats?`<h5>Limitations and caveats</h5><ul class="study-limits">${caveats}</ul>`:''}</article>`;
  return answer;
}
function coachTurnListHtml(){
  const turns=coachConversation?.turns||[];
  if(!turns.length)return '';
  const rows=turns.map((turn,index)=>`<article class="coach-turn"><p class="coach-turn-question"><strong>${index+1}. You asked:</strong> ${esc(turn.question)}</p>${coachReplyHtml(turn.result)}</article>`).join('');
  const latest=turns[turns.length-1];
  const controls=coachConversationFull||coachConversationExpired?'':`<div class="coach-followups"><button type="button" class="secondary" data-coach-followup="simpler"${coachQuestionLoading?' disabled':''}>Simpler</button><button type="button" class="secondary" data-coach-followup="deeper"${coachQuestionLoading?' disabled':''}>Go deeper</button></div>`;
  return `<section class="coach-turn-list" aria-label="Follow-up questions"><h4>Questions about this decision</h4>${rows}${latest?controls:''}${coachConversationFull?'<button type="button" class="secondary" data-new-coach-conversation>Start a new conversation</button>':''}</section>`;
}
function coachQuestionHtml(){
  const error=coachQuestionError?`<p class="hint error" role="alert">${esc(coachQuestionError)}</p>${coachConversationExpired?'<button type="button" class="secondary" data-reset-expired-coach>Start a new conversation</button>':coachConversationFull?'':'<button type="button" class="secondary" data-coach-retry>Retry question</button>'}`:'';
  return `<form id="study-coach-form" class="study-coach-form"><h4>Ask about this decision</h4><label>Question<textarea name="question" maxlength="500" required rows="3" placeholder="Ask one question about the saved decision">${esc(coachDraft.question)}</textarea></label><div class="two"><label>Detail<select name="detail"><option value="short"${coachDraft.detail==='short'?' selected':''}>Short</option><option value="normal"${coachDraft.detail==='normal'?' selected':''}>Normal</option><option value="technical"${coachDraft.detail==='technical'?' selected':''}>Technical</option></select></label><label>Audience<select name="audience"><option value="beginner"${coachDraft.audience==='beginner'?' selected':''}>Beginner</option><option value="standard"${coachDraft.audience==='standard'?' selected':''}>Standard</option></select></label></div><label class="toggle coach-external-opt-in"><input name="external" type="checkbox"${coachDraft.external?' checked':''}${externalAiAvailable?'':' disabled'}> Use external AI for this question</label><p class="hint">When selected, your question, up to two recent questions about this same decision, hero cards, board, and other allowlisted facts are sent to OpenAI. Opponent hole cards, deck, names, and notes are excluded. External AI is off by default.</p>${!externalAiAvailable?'<p class="hint">External AI is disabled in local settings. You can still request a local fallback.</p>':''}<button class="primary" type="submit"${coachQuestionLoading||coachConversationFull||coachConversationExpired?' disabled':''}>${coachQuestionLoading?'Asking…':'Ask question'}</button>${coachQuestionLoading?'<p class="hint" role="status">Preparing a grounded answer…</p>':''}${error}</form>${coachTurnListHtml()}`;
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
    const baseline=studyPayload.baseline?`<p class="hint">${esc(studyPayload.baseline.label)} recommends ${esc(studyPayload.baseline.recommended_action||'an unavailable action')}${baselineValue===null||baselineValue===undefined?'':` · ${chips(baselineValue)} ${baselineValueKey==='estimated_ev_chips'?'chips':coachEvBasisLabel(studyPayload.baseline.ev_basis)}`}</p>`:'';
    const situation=studyPayload.situation,decision=studyPayload.decision;
    const teaching=(situation&&decision)?`<div class="study-teaching-pair"><section class="study-teaching-card" aria-label="Your situation"><p class="eyebrow">Your situation</p><p>${esc(situation.text)}</p><p class="hint">${esc(situation.note)}</p></section><section class="study-teaching-card" aria-label="Your decision"><p class="eyebrow">Your decision</p><p>${esc(decision.text)}</p><p class="hint">${esc(decision.note)}</p></section></div>`:'';
    const limitations=(studyPayload.limitations||[]).map(item=>`<li>${esc(item)}</li>`).join('');
    content=`<p class="eyebrow">${esc(studyPayload.heading)} · ${esc(studyPayload.source_label)}</p>${teaching}<div class="study-prompts" role="group" aria-label="Decision study prompts">${prompts}</div>${active?`<article class="study-answer" aria-live="polite"><h4>${esc(active.question)}</h4><p>${esc(active.answer)}</p></article>`:''}<h4>Modeled actions</h4><div class="study-alternatives"><table><thead><tr><th>Action</th><th>Estimated value</th></tr></thead><tbody>${rows}</tbody></table></div>${baseline}${limitations?`<h4>Limitations and caveats</h4><ul class="study-limits">${limitations}</ul>`:''}${coachQuestionHtml()}`;
  }
  panel.innerHTML=`<p class="eyebrow">DECISION STUDY</p><h3>${esc(studyTitle)}</h3><div class="decision-list" role="group" aria-label="Saved decisions">${decisionButtons}</div><div class="study-content">${content}</div>`;
}
async function selectDecisionStudy(decisionId){
  if(!decisionId||!studyDecisions.some(item=>item.decision_id===decisionId))return;
  selectedDecisionId=decisionId;selectedStudyCard='estimate';studyPayload=null;studyFailed=false;studyLoading=true;
  coachQuestionLoading=false;coachQuestionError='';coachConversation=null;coachConversationFull=false;coachConversationExpired=false;lastCoachQuestion=null;
  coachDraft={question:'',detail:'normal',audience:'standard',external:false};
  const handId=activeHandId,generation=++selectionGeneration;
  renderStudyPanel();
  try{
    const payload=await api(`v1/decisions/${encodeURIComponent(decisionId)}/study`);
    if(activeHandId!==handId||selectedDecisionId!==decisionId||generation!==selectionGeneration)return;
    studyPayload=payload;studyLoading=false;
    if(payload.status==='ready'&&payload.cards?.length)selectedStudyCard=payload.cards[0].id;
    if(payload.status==='ready'&&payload.binding){
      const target={hand_id:handId,decision_id:decisionId,evidence_id:payload.binding.evidence_id,
        state_revision:payload.binding.state_revision};
      const key=JSON.stringify(target);
      coachConversation=coachConversations.get(key)||{key,target,conversationId:null,turns:[]};
      coachConversations.set(key,coachConversation);
      coachConversationFull=coachConversation.turns.length>=4;
      coachConversationExpired=false;
    }
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
  if(coachQuestionLoading||coachConversationExpired||!studyPayload||studyPayload.status!=='ready'||!selectedDecisionId)return;
  const binding=studyPayload.binding;
  const request=retry&&lastCoachQuestion?lastCoachQuestion:{
    question:coachDraft.question.trim(),detail:coachDraft.detail,audience:coachDraft.audience,
    external:coachDraft.external,clientTurnId:crypto.randomUUID(),
    conversationId:coachConversation?.conversationId||null,
  };
  if(!request.question||request.question.length>500){coachQuestionError='Enter a question from 1 to 500 characters.';renderStudyPanel();return;}
  const captured={handId:activeHandId,decisionId:selectedDecisionId,evidenceId:binding?.evidence_id,
    revision:binding?.state_revision,generation:selectionGeneration,handGeneration,
    conversation:coachConversation};
  if(!captured.handId||!captured.evidenceId){coachQuestionError='This study is missing its saved evidence binding.';renderStudyPanel();return;}
  if(!captured.conversation){coachQuestionError='This study is missing its conversation binding.';renderStudyPanel();return;}
  lastCoachQuestion={...request};coachQuestionLoading=true;coachQuestionError='';renderStudyPanel();
  try{
    const payload={client_turn_id:request.clientTurnId,
      target:{hand_id:captured.handId,decision_id:captured.decisionId,
        evidence_id:captured.evidenceId,state_revision:captured.revision},
      question:request.question,detail:request.detail,audience:request.audience};
    if(request.conversationId)payload.conversation_id=request.conversationId;
    const result=await api('v1/coach/turns',payload,request.external?{'X-OpenPoker-External-AI':'1'}:{});
    if(!coachRequestSelectionMatches(captured))return;
    if(result.status==='failed'||result.status==='unavailable'){
      coachQuestionError=result.reason||result.error||'This decision cannot be used for a coach request.';
    }else if(!coachRequestMatches(captured,result)
      ||(request.conversationId&&result.conversation_id!==request.conversationId)
      ||result.client_turn_id!==request.clientTurnId){
      coachQuestionError='The answer did not match the selected decision. Refresh the study and try again.';
    }else{
      captured.conversation.conversationId=result.conversation_id;
      if(!captured.conversation.turns.some(turn=>turn.clientTurnId===request.clientTurnId)){
        captured.conversation.turns.push({clientTurnId:request.clientTurnId,
          question:request.question,result});
      }
      lastCoachQuestion={...request,conversationId:result.conversation_id};
      coachConversationFull=captured.conversation.turns.length>=4;
    }
    coachQuestionLoading=false;
  }catch(error){
    if(!coachRequestSelectionMatches(captured))return;
    coachQuestionError=error.message||'Could not complete this request.';
    coachConversationFull=error.code==='conversation_full';
    coachConversationExpired=error.code==='conversation_expired';coachQuestionLoading=false;
  }
  renderStudyPanel();
}
function startNewCoachConversation(){
  if(!coachConversation)return;
  coachConversation={key:coachConversation.key,target:coachConversation.target,
    conversationId:null,turns:[]};
  coachConversations.set(coachConversation.key,coachConversation);
  coachConversationFull=false;coachConversationExpired=false;coachQuestionError='';lastCoachQuestion=null;
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
async function explainLatestAction(){
  const decisionId=latestCoachDecision?.decision_id,handId=activeHandId,generation=handGeneration;
  if(afterActionLoading||!decisionId||!handId||!$('#coach-toggle').checked||coachQuestionLoading
    ||!liveDecisions.some(item=>item.decision_id===decisionId))return;
  afterActionError='';afterActionLoading=true;showCoach(latestCoachResult,latestCoachDecision);
  await selectDecisionStudy(decisionId);
  if(activeHandId!==handId||handGeneration!==generation
    ||latestCoachDecision?.decision_id!==decisionId||!$('#coach-toggle').checked)return;
  const binding=studyPayload?.binding;
  if(studyPayload?.status!=='ready'||binding?.hand_id!==handId
    ||binding?.decision_id!==decisionId
    ||binding?.evidence_id!==latestCoachDecision.evidence_id
    ||binding?.state_revision!==latestCoachDecision.state_revision){
    afterActionError=studyFailed
      ?'Could not load this decision’s saved study. Retry to try again.'
      :studyPayload?.status==='unavailable'
        ?'This decision’s saved explanation is unavailable. Retry to check again.'
        :'The saved study no longer matches this action. Retry to refresh its evidence.';
    afterActionLoading=false;showCoach(latestCoachResult,latestCoachDecision);return;
  }
  if(selectedDecisionId!==decisionId){
    afterActionError='The saved study selection changed. Retry to reload this action’s evidence.';
    afterActionLoading=false;showCoach(latestCoachResult,latestCoachDecision);return;
  }
  if(coachConversationFull||coachConversationExpired)startNewCoachConversation();
  coachDraft={question:'Explain my recorded choice and its saved loss.',
    detail:'normal',audience:'standard',external:false};
  afterActionLoading=false;showCoach(latestCoachResult,latestCoachDecision);
  await askStudyCoach();
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
  clearCurrentStudy();
  invalidateDecisionStudy();
  try{
    const d=formData(form,['button','seed']);d.names=d.names.split(',').map(s=>s.trim());d.stacks=d.stacks.split(',').map(Number);practiceOpponent=d.opponent_id;delete d.opponent_id;pendingAction=null;
    const dealt=await api('game',d);
    if(handGeneration!==dealGeneration)return;
    activeHandId=dealt.id;selectionGeneration++;selectedDecisionId=null;liveDecisions=[];studyDecisions=[];studyPayload=null;studyLoading=false;studyFailed=false;coachQuestionLoading=false;coachQuestionError='';coachConversation=null;coachConversationFull=false;coachConversations.clear();lastCoachQuestion=null;coachDraft={question:'',detail:'normal',audience:'standard',external:false};latestCoachResult=null;latestCoachDecision=null;afterActionError='';afterActionLoading=false;$('#session-review').hidden=true;$('#decision-study').hidden=true;$('#coach-panel').innerHTML='<p class="hint">Make a decision to receive post-action coaching.</p>';showGame(dealt);status('Done. Results are ready.');
  }catch(err){
    if(handGeneration===dealGeneration){status(err.message,true);if(game)showGame(game);}
  }finally{
    if(handGeneration===dealGeneration)button.disabled=false;
  }
});
$('#coach-toggle').addEventListener('change',e=>{if(!e.target.checked){clearCurrentStudy();showCoach(null);if(!game?.done)invalidateDecisionStudy();}else {renderCurrentStudy();if(game&&!game.done&&liveDecisions.length){showCoach(latestCoachResult,latestCoachDecision);showDecisionStudy(liveDecisions,'Current hand · choose a decision',liveDecisions[liveDecisions.length-1].decision_id);}}});
$('#coach-panel').addEventListener('click',e=>{
  if(e.target.closest('[data-explain-latest-action]'))void explainLatestAction();
});
$('#game-form').elements.opponent_id.addEventListener('change',e=>{practiceOpponent=e.target.value;if(game&&!game.done)clearCurrentStudy();});
$('#current-study').addEventListener('click',e=>{
  if(e.target.closest('[data-study-current],[data-study-current-retry]')){void requestCurrentStudy();return;}
  if(e.target.closest('[data-current-coach-retry]')){void askCurrentCoach();return;}
  if(e.target.closest('[data-current-coach-new]')){
    currentCoachGeneration++;currentCoachConversation=null;currentCoachRetry=null;
    currentCoachFull=false;currentCoachStartNew=false;currentCoachError='';
    currentCoachNeedsRefresh=false;currentCoachResult=null;currentCoachDraft.external=false;
    renderCurrentStudy();return;
  }
  const followup=e.target.closest('[data-current-coach-followup]');
  if(followup){
    const simpler=followup.dataset.currentCoachFollowup==='simpler';
    currentCoachDraft.question=simpler
      ?'Explain the current modeled recommendation more simply.'
      :'Go deeper on the current modeled recommendation.';
    currentCoachDraft.detail=simpler?'short':'technical';
    currentCoachDraft.audience=simpler?'beginner':'standard';
    currentCoachDraft.external=false;currentCoachError='';currentCoachRetry=null;
    renderCurrentStudy();
  }
});
$('#current-study').addEventListener('input',e=>{if(e.target.name==='question')currentCoachDraft.question=e.target.value;});
$('#current-study').addEventListener('change',e=>{
  const edited=e.target.name==='question'||e.target.name==='detail'||e.target.name==='audience'||e.target.name==='external';
  if(edited&&currentCoachRetry){
    const payload=currentCoachRetry.payload;
    const changed=(e.target.name==='question'&&e.target.value!==payload.question)
      ||(e.target.name==='detail'&&e.target.value!==payload.detail)
      ||(e.target.name==='audience'&&e.target.value!==payload.audience)
      ||(e.target.name==='external'&&e.target.checked!==currentCoachRetry.external);
    if(changed){currentCoachRetry=null;if(!currentCoachNeedsRefresh&&!currentCoachStartNew)currentCoachError='';}
  }
  if(e.target.name==='detail')currentCoachDraft.detail=e.target.value;
  if(e.target.name==='audience')currentCoachDraft.audience=e.target.value;
  if(e.target.name==='external')currentCoachDraft.external=e.target.checked;
});
$('#current-study').addEventListener('submit',e=>{
  if(e.target.id!=='current-coach-form')return;
  e.preventDefault();
  currentCoachDraft.question=e.target.elements.question.value;
  currentCoachDraft.detail=e.target.elements.detail.value;
  currentCoachDraft.audience=e.target.elements.audience.value;
  currentCoachDraft.external=e.target.elements.external.checked;
  void askCurrentCoach();
});
$('#decision-study').addEventListener('click',e=>{
  const followup=e.target.closest('[data-coach-followup]');
  if(followup){
    if(coachQuestionLoading||coachConversationExpired)return;
    coachDraft.question=followup.dataset.coachFollowup==='simpler'
      ?'Explain this same decision more simply.'
      :'Go deeper on this same decision.';
    coachDraft.detail=followup.dataset.coachFollowup==='simpler'?'short':'technical';
    coachDraft.audience=followup.dataset.coachFollowup==='simpler'?'beginner':'standard';
    coachDraft.external=$('#study-coach-form')?.elements.external.checked||false;
    void askStudyCoach(false);return;
  }
  if(e.target.closest('[data-new-coach-conversation]')){startNewCoachConversation();return;}
  const decisionButton=e.target.closest('[data-decision-id]');
  if(decisionButton){void selectDecisionStudy(decisionButton.dataset.decisionId);return;}
  const cardButton=e.target.closest('[data-study-card]');
  if(cardButton&&studyPayload?.status==='ready'){selectedStudyCard=cardButton.dataset.studyCard;renderStudyPanel();return;}
  if(e.target.closest('[data-retry-study]'))void selectDecisionStudy(selectedDecisionId);
  if(e.target.closest('[data-coach-retry]'))void askStudyCoach(true);
  if(e.target.closest('[data-reset-expired-coach]'))startNewCoachConversation();
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
  clearCurrentStudy();
  b.disabled=true;
  const action=b.dataset.action,amount=Number($('#raise-amount').value),actingStreet=actingGame.street;
  const requestKey=JSON.stringify([actingGame.id,action,action==='raise'?amount:null,practiceOpponent,$('#coach-toggle').checked,$('#coach-personality').value,actingGame.revision]);
  if(!pendingAction||pendingAction.key!==requestKey)pendingAction={key:requestKey,id:crypto.randomUUID()};
  const actionRequest=pendingAction;
  try{
    const g=await api('act',{id:actingHandId,action,amount,opponent_id:practiceOpponent,coach_visible:$('#coach-toggle').checked,personality:$('#coach-personality').value,expected_revision:actingGame.revision,client_action_id:actionRequest.id});
    if(activeHandId!==actingHandId||handGeneration!==actingHandGeneration)return;
    if(pendingAction===actionRequest)pendingAction=null;
    afterActionError='';afterActionLoading=false;
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
