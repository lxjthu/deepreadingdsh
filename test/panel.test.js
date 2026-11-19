import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer, request as httpRequest } from 'node:http';
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

test('chunked JSON is forwarded with its UTF-8 byte length', async t => {
  const backend=createServer(async (req,res)=>{
    let body='';for await(const chunk of req)body+=chunk;
    const size=Number(req.headers['content-length']||0);
    res.writeHead(size>0?200:400,{'Content-Type':'application/json'});
    res.end(JSON.stringify(size>0?{body,size,transfer:req.headers['transfer-encoding']}:{error:'请求大小需小于 100 MiB'}));
  });
  await new Promise(resolve=>backend.listen(0,'127.0.0.1',resolve));t.after(()=>backend.close());
  const proxy=createServer(panelProxy({connection:{admit:()=>({peer:{}})},backend:()=>`http://127.0.0.1:${backend.address().port}`,token:'backend-only'}));
  await new Promise(resolve=>proxy.listen(0,'127.0.0.1',resolve));t.after(()=>proxy.close());
  const text=JSON.stringify({entry_id:'中文 PDF 来源'});
  const result=await new Promise((resolve,reject)=>{
    const request=httpRequest(`http://127.0.0.1:${proxy.address().port}/deep-reading/api/pdf/session`,{method:'POST',headers:{'Content-Type':'application/json'}},async response=>{
      let body='';for await(const chunk of response)body+=chunk;
      resolve({status:response.statusCode,...JSON.parse(body)});
    });
    request.on('error',reject);request.write(text);request.end();
  });
  assert.equal(result.status,200,JSON.stringify(result));
  assert.equal(result.body,text);assert.equal(result.size,Buffer.byteLength(text));assert.equal(result.transfer,undefined);
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
  for (const path of ['/pdf', '/pdf.js', '/pdf.css', '/card', '/card.js', '/card.css','/katex/katex.min.js','/katex/fonts/KaTeX_Main-Regular.woff2']) {
    assert.equal((await fetch(url+'/deep-reading'+path,{headers})).status,200);
    assert.equal((await fetch(url+'/deep-reading'+path)).status,401);
  }
  assert.equal((await fetch(url+'/deep-reading/katex/LICENSE',{headers})).status,404);
  const r=await (await fetch(url+'/deep-reading/api/state?x=1',{headers})).json();
  assert.equal(r.url,'/api/state?x=1');assert.equal(r.token,'backend-only');assert.equal(r.cookie,undefined);
});
