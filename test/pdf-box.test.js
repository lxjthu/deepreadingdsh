import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../web/pdf.js',import.meta.url),'utf8');

function fixture(){
  const listeners={},pageListeners={},windowListeners={},controls={};
  function node(className=''){
    return {className,style:{},dataset:{},children:[],classList:{toggle(){}},
      append(child){child.parent=this;this.children.push(child);},
      remove(){if(this.parent)this.parent.children=this.parent.children.filter(child=>child!==this);},
      setAttribute(){},querySelectorAll(selector){return this.children.filter(child=>selector==='.box-draft'&&child.className.includes('box-draft'));},
      addEventListener(name,callback){this[name]=callback;}};
  }
  const layer=node();
  Object.defineProperty(layer,'textContent',{set(){this.children=[];}});
  const section={dataset:{page:'1'},getBoundingClientRect:()=>({left:0,top:0,width:100,height:100}),querySelector:()=>layer,setPointerCapture(){}};
  const tools=['select','box','highlight'].map(tool=>({...node(),dataset:{tool}}));
  controls['#pages']={addEventListener:(name,callback)=>{pageListeners[name]=callback;}};
  const state={tool:'box',marks:[],pages:new Map([[1,{section,marks:layer}]])};
  const calls=[],removed=[];
  const context=vm.createContext({
    state,clamp:(value,a,b)=>Math.min(b,Math.max(a,value)),round:value=>Math.round(value*100000)/100000,
    $:selector=>controls[selector]??(controls[selector]=node()),$$:()=>tools,
    element:(_tag,className)=>node(className),button:(_label,onclick,className)=>({...node(className),onclick}),
    guarded:fn=>fn,setStatus(){},updateCount(){},captureCardSelection:()=>null,openEditor(){},
    createMark:async(...args)=>{calls.push(args);return {id:'saved'};},removeMark:async id=>{removed.push(id);},
    KIND_NAMES:{box:'框选'},
    document:{body:{dataset:{}},addEventListener:(name,callback)=>{listeners[name]=callback;}},
    window:{getSelection:()=>({isCollapsed:true,rangeCount:0,removeAllRanges(){}}),addEventListener:(name,callback)=>{windowListeners[name]=callback;}},
  });
  vm.runInContext(source.slice(source.indexOf('/* ---------- pointer tools ---------- */'),source.indexOf('/* ---------- editor ---------- */')),context);
  const start=source.indexOf("for (const tool of $$('[data-tool]'))");
  vm.runInContext(source.slice(start,source.indexOf("const colors = $('#colors');",start)),context);
  const event=(x=10,y=20)=>({button:0,pointerId:1,clientX:x,clientY:y,target:{closest:selector=>selector==='.page'?section:null},preventDefault(){}});
  async function box(){pageListeners.pointerdown(event());listeners.pointermove(event(70,80));await listeners.pointerup(event(70,80));}
  return {context,state,layer,controls,listeners,pageListeners,windowListeners,tools,calls,removed,event,box,
    pending:()=>vm.runInContext('draftBox',context)};
}

test('release keeps a draft; cancel and later pointerup never save it',async()=>{
  const f=fixture();await f.box();assert.equal(f.calls.length,0);assert.ok(f.pending());
  f.controls['#box-cancel'].onclick();await f.listeners.pointerup(f.event());
  assert.equal(f.pending(),null);assert.equal(f.state.tool,'select');assert.equal(f.calls.length,0);
  assert.equal(f.layer.children.length,0);
});

test('Escape cancels dragging and finished drafts',async()=>{
  for(const finished of [false,true]){
    const f=fixture();
    if(finished)await f.box();else{f.pageListeners.pointerdown(f.event());f.listeners.pointermove(f.event(70,80));}
    f.listeners.keydown({key:'Escape',preventDefault(){}});await f.listeners.pointerup(f.event(70,80));
    assert.equal(f.state.tool,'select');assert.equal(f.pending(),null);assert.equal(f.calls.length,0);assert.equal(f.layer.children.length,0);
  }
});

test('save writes one rectangle and failed save keeps a retryable draft',async()=>{
  const f=fixture();await f.box();
  f.context.createMark=async()=>{throw Error('offline');};
  await assert.rejects(f.controls['#box-save'].onclick(),/offline/);
  assert.ok(f.pending());assert.equal(f.pending().saving,false);assert.equal(f.controls['#box-save'].disabled,false);
  f.context.createMark=async(...args)=>{f.calls.push(args);};
  await f.controls['#box-save'].onclick();await f.controls['#box-save'].onclick();
  assert.equal(f.calls.length,1);assert.equal(f.calls[0][0],'box');
  assert.equal(JSON.stringify(f.calls[0][2]),'[[0.1,0.2,0.7,0.8]]');
  assert.equal(f.pending(),null);assert.equal(f.state.tool,'select');
});

test('tool change, pointer cancellation, capture loss and blur discard active drags',async()=>{
  for(const reason of ['tool','pointercancel','lostpointercapture','blur']){
    const f=fixture();f.pageListeners.pointerdown(f.event());f.listeners.pointermove(f.event(70,80));
    if(reason==='tool')f.tools[0].click();else if(reason==='blur')f.windowListeners.blur();else f.listeners[reason](f.event());
    await f.listeners.pointerup(f.event(70,80));assert.equal(f.calls.length,0);assert.equal(f.layer.children.length,0);
  }
});

test('saved boxes expose a direct delete control',async()=>{
  const f=fixture();f.state.marks=[{id:'box-old',kind:'box',page:1,color:'yellow',rects:[[.1,.2,.7,.8]]}];
  vm.runInContext(source.slice(source.indexOf('function renderMarks()'),source.indexOf('function sortedMarks()')),f.context);
  vm.runInContext('renderMarks()',f.context);
  const remove=f.layer.children[0].children[0];assert.equal(remove.className,'box-remove');
  await remove.onclick({stopPropagation(){}});assert.deepEqual(f.removed,['box-old']);
});
