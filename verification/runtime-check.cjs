const assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const hostRequire=createRequire('D:/Program Files/DeepSeekharness/resources/app.asar/dsh/package.json');
(async()=>{
  const llm=hostRequire('@deepseek-ai/dsh-llm');
  const {requestOptions}=await import('../bridge.js');
  const result=requestOptions({messages:['system','user','assistant','user'].map(role=>({role,content:'text'}))},llm,{provider:'test',model:'model',reasoningEffort:'high'});
  assert.deepEqual(result.messages.map(m=>m.role),['system','user','assistant','user']);
  for(const message of result.messages){assert.ok(message.id);assert.ok(message.source);assert.ok(Object.isFrozen(message));}
  assert.equal(result.messages[1].source.kind,'user');assert.equal(result.messages[2].source.kind,'model');
  assert.equal(result.reasoningEffort,'high');assert.equal('maxTokens' in result,false);
  console.log('Installed 0.2.2-rc.3 runtime message helpers: PASS (roles, id, source, immutable messages, effort, inherited token cap)');
})().catch(error=>{console.error(error);process.exitCode=1;});
