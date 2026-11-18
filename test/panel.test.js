import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { panelProxy } from '../panel-proxy.js';

test('native client contributes matching sidebar and main panel identities', () => {
  let module;
  vm.runInNewContext(readFileSync(new URL('../client.js', import.meta.url), 'utf8'), { window: { __ModuleLoader__: { load: spec => { module = spec.factory(() => ({})); } } } });
  const entries=[];
  module.apply({ effect:fn=>fn(),locale:{register:()=>()=>{},bind:()=>key=>({title:'文献研究'})[key]},slots: { inject: (_, fn) => fn(), register: (spec, component) => { entries.push({spec,component});return ()=>{}; } } });
  assert.equal(entries.find(e=>e.spec.name==='main').spec.key,'deep-reading');
  assert.equal(entries.find(e=>e.spec.name==='sidebar.panellist').spec.id,'deep-reading');
  assert.equal(entries.find(e=>e.spec.name==='sidebar.panellist').spec.label(),'文献研究');
});

test('panel proxy requires dsh admission, hides internal bridge, preserves backend credentials', async t => {
  const backend=createServer((req,res)=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify({url:req.url,token:req.headers['x-reading-token'],cookie:req.headers.cookie}));});
  await new Promise(resolve=>backend.listen(0,'127.0.0.1',resolve));
  t.after(()=>backend.close());
  const proxy=createServer(panelProxy({connection:{admit:req=>req.headers['x-test-auth']==='valid'?{peer:{}}:{rejection:401}},backend:()=>`http://127.0.0.1:${backend.address().port}`,token:'backend-only'}));
  await new Promise(resolve=>proxy.listen(0,'127.0.0.1',resolve));t.after(()=>proxy.close());
  const url=`http://127.0.0.1:${proxy.address().port}`;
  assert.equal((await fetch(url+'/deep-reading/api/state')).status,401);
  const headers={'X-Test-Auth':'valid',Cookie:'dsh-secret=hidden'};
  assert.equal((await fetch(url+'/deep-reading/bridge/next',{headers})).status,404);
  assert.equal((await fetch(url+'/deep-reading/wiki.js',{headers})).status,200);
  const r=await (await fetch(url+'/deep-reading/api/state?x=1',{headers})).json();
  assert.equal(r.url,'/api/state?x=1');assert.equal(r.token,'backend-only');assert.equal(r.cookie,undefined);
});
