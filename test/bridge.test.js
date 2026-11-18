import { test } from 'node:test';
import assert from 'node:assert/strict';
import { generate, requestOptions } from '../bridge.js';
test('preserves message roles and keeps assistant history',()=>{
  const helpers={createSystemMessage:t=>({role:'system',text:t}),createAssistantMessage:m=>({role:'assistant',...m})};
  const r=requestOptions({messages:[{role:'system',content:'rules'},{role:'user',content:'paper'},{role:'assistant',content:'previous'},{role:'user',content:'next'}]},helpers,{provider:'deepseek-account',model:'deepseek-flash'});
  assert.deepEqual(r.messages.map(m=>m.role),['system','user','assistant','user']);
  assert.equal(r.messages[2].content[0].text,'previous');
});
test('only a complete visible answer succeeds',async()=>{
  const llm={async *stream(){yield {type:'text-delta',text:'answer'};yield {type:'usage',usage:{inputTokens:2,outputTokens:1}};yield {type:'finish',reason:{kind:'stop'}};}};
  assert.equal((await generate(llm,{})).content,'answer');
  for(const kind of ['max-tokens','error','aborted','tool-calls']){
    await assert.rejects(generate({async *stream(){yield {type:'text-delta',text:'partial'};yield {type:'finish',reason:{kind}};}},{}));
  }
  await assert.rejects(generate({async *stream(){yield {type:'finish',reason:{kind:'stop'}};}},{}));
});
