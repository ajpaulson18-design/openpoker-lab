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
let coachConversation = null, coachConversations = new Map(), lastCoachQuestion = null;
let coachConversationFull = false, coachConversationExpired = false;
let coachDraft = {question:'',detail:'normal',audience:'standard',external:false};
let currentStudyView = null, currentStudyRequest = null, currentStudyLoading = false, currentStudyError = '';
let currentStudyGeneration = 0, currentStudyOpponent = '';
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
  $('#opponent-list').innerHTML=opponents.length?opponents.map(o=>`<article class="card"><h3>${esc(o.name)}</h3><p class="hint">${esc(o.profile.replaceAll('_',' '))} prior · all streets pooled below</p>${Object.entries(o.metrics).map(([k,m])=>`<div class="bar-row"><span>${esc(k.replaceAll('_',' '))}</span><progress value="${m.mean}" max="1"></progress><span>${pct(m.mean)}</span></div><p class="hint">${m.observations} observed opportunities · ${pct(m.interval95[0])}–${pct(m.interval95[1])} approximate interval · ${esc(m.confidence)} confidence</p>`).join('')}<p class="fine">Decision analysis uses observations for the entered street. Unspecified observations appear here but do not inform street-specific decisions.</p></article>`).join(''):'<div class="card result-card"><p class="eyebrow">NO OPPONENTS YET</p><h2>A read is a startinu�}w����k�w��pponent=d.opponent_id;delete d.opponent_id;pendingAction=null;
    const dealt=await api('game',d);
    if(handGeneration!==dealGeneration)return;
    activeHandId=dealt.id;selectionGeneration++;selectedDecisionId=null;liveDecisions=[];studyDecisions=[];studyPayload=null;studyLoading=false;studyFailed=false;coachQuestionLoading=false;coachQuestionError='';coachConversation=null;coachConversationFull=false;coachConversations.clear();lastCoachQuestion=null;coachDraft={question:'',detail:'normal',audience:'standard',external:false};latestCoachResult=null;latestCoachDecision=null;$('#session-review').hidden=true;$('#decision-study').hidden=true;$('#coach-panel').innerHTML='<p class="hint">Make a decision to receive post-action coaching.</p>';showGame(dealt);status('Done. Results are ready.');
  }catch(err){
    if(handGeneration===dealGeneration){status(err.message,true);if(game)showGame(game);}
  }finally{
    if(handGeneration===dealGeneration)button.disabled=false;
  }
});
$('#coach-toggle').addEventListener('change',e=>{if(!e.target.checked){clearCurrentStudy();showCoach(null);if(!game?.done)invalidateDecisionStudy();}else {renderCurrentStudy();if(game&&!game.done&&liveDecisions.length){showCoach(latestCoachResult,latestCoachDecision);showDecisionStudy(liveDecisions,'Current hand · choose a decision',liveDecisions[liveDecisions.length-1].decision_id);}}});
$('#game-form').elements.opponent_id.addEventListener('change',e=>{practiceOpponent=e.target.value;if(game&&!game.done)clearCurrentStudy();});
$('#current-study').addEventListener('click',e=>{if(e.target.closest('[data-study-current],[data-study-current-retry]'))void requestCurrentStudy();});
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
