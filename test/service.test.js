import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, existsSync, realpathSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ReadingService } from '../service.js';

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
