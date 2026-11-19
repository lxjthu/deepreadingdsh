import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, existsSync, realpathSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ReadingService } from '../service.js';
import { panelProxy } from '../panel-proxy.js';
import { createServer, request as httpRequest } from 'node:http';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const root=dirname(dirname(fileURLToPath(import.meta.url)));
function fixture(t, extra={}) {
  const home=mkdtempSync(join(tmpdir(),'reading-'));
  t.after(()=>rmSync(home,{recursive:true,force:true}));
  return new ReadingService({root,home,settings:{python:process.env.DSH_TEST_PYTHON || 'python',shutdownTimeoutMs:1000,...extra},llm:{},messages:{},selection:()=>({provider:'test',model:'test'}),log:{warn(){}},...extra});
}
test('idle shutdown waits for process close and removes only its descriptor',async t=>{
  const service=fixture(t);await service.start();
  assert.equal(service.status,'ready');assert.ok(existsSync(join(service.home,'connection.json')));
  await service.stop();
  assert.equal(service.status,'stopped');assert.equal(service.base,undefined);
  assert.notEqual(service.child.exitCode,null);
  assert.equal(existsSync(join(service.home,'connection.json')),false);
  await service.stop();
});
test('dispose before readiness waits for exit; later instance remains live',async t=>{
  const first=fixture(t);const starting=first.start();const failed=assert.rejects(starting,/取消|退出/);
  await first.stop();await failed;
  const second=new ReadingService({root,home:first.home,settings:first.settings,llm:{},messages:{},selection:first.selection,log:first.log});
  t.after(()=>second.stop());
  await second.start();await new Promise(resolve=>setTimeout(resolve,1100));
  assert.equal(realpathSync((await second.call('/api/state')).home),realpathSync(second.home));
  await second.stop();
});
test('abnormal exit clears connection and supports a fresh instance',async t=>{
  const service=fixture(t);await service.start();service.child.kill();await service.closed;
  assert.equal(service.status,'failed');assert.equal(service.base,undefined);assert.equal(existsSync(join(service.home,'connection.json')),false);
  await service.stop();
  const retry=fixture(t);await retry.start();await retry.stop();
});
test('shutdown during model generation awaits the aborted stream',async t=>{
  const service=fixture(t);let entered,settled=false;
  const started=new Promise(resolve=>entered=resolve);
  service.messages={createUserMessage:m=>m};
  service.llm={async *stream(options){entered();await new Promise(resolve=>options.signal.addEventListener('abort',resolve,{once:true}));await new Promise(resolve=>setTimeout(resolve,50));settled=true;yield {type:'finish',reason:{kind:'aborted'}};}};
  await service.start();
  const fulfill=service.fulfill({id:'test',lease:'test',messages:[{role:'user',content:'test'}]});
  service.bridge=fulfill;
  await started;await service.stop();
  assert.equal(settled,true);assert.notEqual(service.child.exitCode,null);
});

test('chunked PDF open reaches the real Python reader and returns usable resources',async t=>{
  const service=fixture(t);await service.start();t.after(()=>service.stop());
  const path=join(service.home,'paper.pdf');
  await promisify(execFile)(service.settings.python,['-c',"import sys; import fitz; d=fitz.open(); p=d.new_page(); p.insert_text((40,60),'PDF reader regression'); d.save(sys.argv[1]); d.close()",path],{windowsHide:true});
  const topic=await service.call('/api/topics',{name:'PDF test'});
  const task=await service.call('/api/import',{topic_id:topic.id,path,engine:'pymupdf',auto_organize:false});
  const end=Date.now()+15000;let state;
  while(Date.now()<end){
    state=await service.call('/api/state');
    const current=state.tasks.find(row=>row.id===task.id);
    if(current.status==='completed')break;
    if(current.status==='failed')throw Error(current.error);
    await new Promise(resolve=>setTimeout(resolve,50));
  }
  assert.equal(state.tasks.find(row=>row.id===task.id).status,'completed');
  const entry=state.library[0].id;
  const proxy=createServer(panelProxy({connection:{admit:()=>({peer:{}})},backend:()=>({base:service.base,token:service.token})}));
  await new Promise(resolve=>proxy.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>proxy.close(resolve)));
  const result=await new Promise((resolve,reject)=>{
    const request=httpRequest(`http://127.0.0.1:${proxy.address().port}/deep-reading/api/pdf/session`,{method:'POST',headers:{'Content-Type':'application/json'}},async response=>{
      let text='';for await(const chunk of response)text+=chunk;
      resolve({status:response.statusCode,body:JSON.parse(text)});
    });
    request.on('error',reject);request.write(JSON.stringify({entry_id:entry}));request.end();
  });
  assert.equal(result.status,200,JSON.stringify(result.body));
  const url=new URL(result.body.url),params=new URLSearchParams(url.hash.slice(1));
  assert.notEqual(params.get('token'),service.token);
  for(const path of ['/pdf','/pdf.js','/pdf.css'])assert.equal((await fetch(url.origin+path)).status,200);
  const meta=await (await fetch(url.origin+'/api/pdf/meta?entry_id='+entry,{headers:{'X-Reading-Token':params.get('token')}})).json();
  assert.equal(meta.page_count,1);
  const page=await fetch(url.origin+'/api/pdf/page?'+new URLSearchParams({entry_id:entry,page:'1',token:params.get('token')}));
  assert.equal(page.headers.get('content-type'),'image/png');assert.equal(page.status,200);
});
