import { test } from 'node:test';
import assert from 'node:assert/strict';
import { generate, requestOptions, admitVisionRequest } from '../bridge.js';
test('preserves message roles and keeps assistant history',()=>{
  const helpers={createSystemMessage:t=>({role:'system',text:t}),createAssistantMessage:m=>({role:'assistant',...m}),createUserMessage:m=>({role:'user',id:'test-id',...m})};
  const r=requestOptions({messages:[{role:'system',content:'rules'},{role:'user',content:'paper'},{role:'assistant',content:'previous'},{role:'user',content:'next'}]},helpers,{provider:'deepseek-account',model:'deepseek-flash'});
  assert.deepEqual(r.messages.map(m=>m.role),['system','user','assistant','user']);
  assert.equal(r.messages[2].content[0].text,'previous');
  assert.equal(r.messages[1].source.kind,'user');
  assert.equal(r.messages[1].id,'test-id');
  assert.equal('maxTokens' in r,false);
  const selected=requestOptions({messages:[]},helpers,{provider:'p',model:'m',reasoningEffort:'high',maxTokens:77});
  assert.equal(selected.reasoningEffort,'high');
  assert.equal(selected.maxTokens,77);
});

test('vision requires an image route and attaches admitted image references to the last user message',async()=>{
  const request={messages:[{role:'user',content:'old'},{role:'assistant',content:'answer'},{role:'user',content:'recognize'}],images:[{mediaType:'image/png',data:'AQ==',name:'crop.png'}]};
  let stored=0;
  const attachment={attachmentId:'image-id',mediaType:'image/png',bytes:1,width:1,height:1};
  const attachments={async saveImages(images){stored++;assert.equal(images[0].data[0],1);return [attachment];}};
  const signal=new AbortController().signal,config={provider:'p',model:'v'};
  await assert.rejects(admitVisionRequest(request,{resolveModelInfo:async()=>({inputModalities:['text']})},attachments,config,signal),/不支持图片/);
  assert.equal(stored,0);
  const admitted=await admitVisionRequest(request,{resolveModelInfo:async()=>({inputModalities:['text','image']})},attachments,config,signal);
  const helpers={createUserMessage:m=>({role:'user',...m}),createAssistantMessage:m=>({role:'assistant',...m})};
  const result=requestOptions(admitted,helpers,config,signal);
  assert.equal(result.messages[0].content.length,1);
  assert.deepEqual(result.messages[2].content[1],{type:'image',attachment});
});
test('only a complete visible answer succeeds',async()=>{
  const llm={async *stream(){yield {type:'text-delta',text:'answer'};yield {type:'usage',usage:{inputTokens:2,outputTokens:1}};yield {type:'finish',reason:{kind:'stop'}};}};
  assert.equal((await generate(llm,{})).content,'answer');
  for(const kind of ['max-tokens','error','aborted','tool-calls']){
    await assert.rejects(generate({async *stream(){yield {type:'text-delta',text:'partial'};yield {type:'finish',reason:{kind}};}},{}));
  }
  await assert.rejects(generate({async *stream(){yield {type:'finish',reason:{kind:'stop'}};}},{}));
});
