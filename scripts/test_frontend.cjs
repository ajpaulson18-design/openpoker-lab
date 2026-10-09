'use strict';
// Exercise the actual browser adapter block without a DOM or duplicated implementation.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../pokerlab/web/app.js'),'utf8');
const block=source.split('// BEGIN PRESENTATION ADAPTERS')[1].split('// END PRESENTATION ADAPTERS')[0];
const context=vm.createContext({});
vm.runInContext('// BEGIN PRESENTATION ADAPTERS'+block+'\nthis.adapter={loungeHandClass,loungeMatrixModel,loungeBlend,loungeSeatSlots};',context);
const {loungeHandClass:handClass,loungeMatrixModel:matrix,loungeBlend:blend,loungeSeatSlots:slots}=context.adapter;
let checks=0;
function check(name,work){work();checks++;console.log('PASS '+name);}
check('Physical hands map correctly to pairs, suited and offsuit classes',()=>{
  assert.equal(handClass('QsJs'),'QJs');assert.equal(handClass('JsQs'),'QJs');
  assert.equal(handClass('AsKh'),'AKo');assert.equal(handClass('AsAh'),'AA');
  assert.equal(handClass('AsAs'),null);assert.equal(handClass('bad'),null);
});
const response={strategy_schema:'river-strategy-v1',backend:'optimized-binary-tree',
  oop:[{hand:'AsAh',bet:.2,call_after_check:.9},{hand:'AcAd',bet:.8,call_after_check:.6},{hand:'QsJs',bet:0,call_after_check:1}],
  ip:[{hand:'KsKh',bet_after_check:.25,call:.75}]};
const original=JSON.stringify(response);
check('Existing browser contracts retain unique IDs and required controls',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../pokerlab/web/index.html'),'utf8');
  const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);
  assert.equal(new Set(ids).size,ids.length);
  for(const id of ['analysis-form','equity-form','solver-form','game-form','game-controls','raise-amount','coach-toggle','coach-voice-template','current-study','coach-panel','session-review','decision-study','lounge-analysis','lounge-strategy'])assert.ok(ids.includes(id),`missing ${id}`);
  assert.ok(html.includes('form="game-form"'));
  assert.ok(html.indexOf('href="/coach.css"')<html.indexOf('href="/style.css"'));
});
check('Class inspection preserves exact per-combination probabilities',()=>{
  const aa=matrix(response,'oop_open').cells.find(c=>c.label==='AA');
  assert.equal(aa.probability,.5);assert.equal(aa.combinations[0].probability,.2);
  assert.equal(aa.combinations[1].probability,.8);assert.equal(JSON.stringify(response),original);
});
check('Missing combinations stay unavailable rather than becoming folds',()=>{
  const model=matrix(response,'oop_open');assert.equal(model.cells.length,169);
  assert.equal(model.cells.find(c=>c.label==='22').probability,null);
  assert.equal(model.cells.find(c=>c.label==='QJs').probability,0);
});
check('Distinct decision nodes never become a fabricated three-action strategy',()=>{
  assert.equal(matrix(response,'oop_response').cells.find(c=>c.label==='QJs').probability,1);
  assert.equal(matrix(response,'ip_open').cells.find(c=>c.label==='KK').probability,.25);
  assert.equal(matrix(response,'ip_response').cells.find(c=>c.label==='KK').probability,.75);
  assert.equal(matrix(response,'unknown'),null);
});
check('Unsupported schemas and invalid values fail closed',()=>{
  for(const data of [{...response,backend:'configured-tree'},{...response,strategy_schema:'postflop-strategy-v1'},
    {oop:[{hand:'AsAh',bet:NaN},{hand:'KsKh',bet:1.1},{hand:'QsQh',bet:'0.5'}]}])
    assert.equal(matrix(data,'oop_open').cells.filter(c=>c.probability!==null).length,0);
});
check('Pure strategy colors retain endpoints and unavailable states',()=>{
  assert.equal(blend(null,['#c99b52','#7cb9d4']),'');
  assert.ok(blend(1,['#c99b52','#7cb9d4']).includes('rgb(201,155,82)'));
  assert.ok(blend(0,['#c99b52','#7cb9d4']).includes('rgb(124,185,212)'));
});
check('Seat positioning covers every supported player count without hidden-data inference',()=>{
  for(let count=2;count<=6;count++){const positions=slots(count);assert.equal(positions.length,count);assert.equal(new Set(positions).size,count);assert.equal(positions[0],0);}
});
console.log(`${checks} frontend contract checks passed.`);
