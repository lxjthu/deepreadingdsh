const assert=require('node:assert/strict');
const {createRequire,registerHooks}=require('node:module');
const {pathToFileURL}=require('node:url');
const {mkdtempSync,rmSync,mkdirSync,writeFileSync,readFileSync,realpathSync,unlinkSync}=require('node:fs');
const {tmpdir}=require('node:os');
const {join}=require('node:path');
const {createServer}=require('node:http');
const {execFileSync}=require('node:child_process');
const hostRequire=createRequire('D:/Program Files/DeepSeekharness/resources/app.asar/dsh/package.json');
registerHooks({resolve(specifier,context,next){
  try{return next(specifier,context);}
  catch(error){if(!specifier.startsWith('@deepseek-ai/'))throw error;return next(pathToFileURL(hostRequire.resolve(specifier)).href,context);}
}});
(async()=>{
  const {Context}=hostRequire('@deepseek-ai/cordis');
  const plugin=await import('../index.js');
  const tmp=mkdtempSync(join(tmpdir(),'reading-controller-'));
  const settingsFile=join(tmp,'machine.json'), first=join(tmp,'原库'), second=join(tmp,'中文 空库');
  const ctx=new Context();let server,picked=second,opened=0;
  ctx.provide('skills',{register:()=>()=>{}});
  ctx.provide('llm',{async *stream(options){
    if(!options.signal.aborted)await new Promise(resolve=>options.signal.addEventListener('abort',resolve,{once:true}));
    yield {type:'finish',reason:{kind:'aborted'}};
  }});
  ctx.provide('agentDefaultModel',{currentSelection:()=>({provider:'dynamic',model:'selected',reasoningEffort:'high'})});
  ctx.provide('directoryPicker',{capability:()=>({kind:'native',pick:async signal=>{opened++;if(picked==='WAIT')return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>setTimeout(()=>reject(Error('picker aborted')),50),{once:true}));return picked;}})});
  ctx.provide('connection',{admit:req=>req.headers['x-test-auth']==='yes'?{peer:{}}:{rejection:401}});
  ctx.provide('webServer',{register:({handler})=>{server=createServer(handler);server.listen(0,'127.0.0.1');return ()=>new Promise(resolve=>server.close(resolve));}});
  const fiber=ctx.plugin(plugin,{dataDir:first,settingsFile,python:'D:/code/dsh-deep-reading-runtime/.venv/Scripts/python.exe',shutdownTimeoutMs:1000});
  await fiber;
  while(!server?.listening)await new Promise(resolve=>setTimeout(resolve,10));
  let url=`http://127.0.0.1:${server.address().port}/deep-reading`;
  async function api(path,body,ok=true){
    const response=await fetch(url+path,{method:body===undefined?'GET':'POST',headers:{'X-Test-Auth':'yes','Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
    const result=await response.json();if(ok)assert.equal(response.status,200,JSON.stringify(result));else assert.equal(response.status,400);
    return result;
  }
  async function ready(){const end=Date.now()+10000;let state;while(Date.now()<end){state=await api('/control/status');if(state.status==='ready')return state;if(state.status==='failed')throw Error(state.error);await new Promise(resolve=>setTimeout(resolve,30));}throw Error('Not ready: '+JSON.stringify(state));}
  try{
    await ready();
    assert.equal((await fetch(url+'/control/status')).status,401);
    assert.equal((await api('/control/pick',{})).path,second);assert.equal(opened,1);
    picked=null;assert.equal((await api('/control/pick',{})).path,null);assert.equal((await api('/control/status')).home,first);
    const topic=await api('/api/topics',{name:'kept'});
    const paper=join(tmp,'paper.md');writeFileSync(paper,'# Test paper\n\nAuthors: Tester\nYear: 2026\n\nEvidence about research methods.');
    const busy=await api('/api/import',{topic_id:topic.id,path:paper,engine:'pymupdf',auto_organize:true});
    while((await api('/api/state')).tasks[0].status!=='running')await new Promise(resolve=>setTimeout(resolve,20));
    await api('/control/save',{path:second},false);
    assert.equal((await api('/control/status')).home,first);
    await api('/api/cancel',{id:busy.id});
    while((await api('/api/state')).tasks.some(t=>t.status==='running'||t.status==='queued'))await new Promise(resolve=>setTimeout(resolve,50));
    await new Promise(resolve=>setTimeout(resolve,350));
    const unknown=join(tmp,'unknown');mkdirSync(unknown);writeFileSync(join(unknown,'keep.txt'),'keep');
    await api('/control/save',{path:unknown},false);assert.equal((await api('/control/status')).home,first);
    assert.equal((await api('/api/state')).topics[0].name,'kept');
    await api('/control/save',{path:second});
    assert.equal((await api('/api/state')).topics.length,0);assert.equal(realpathSync(JSON.parse(readFileSync(settingsFile)).dataDir),realpathSync(second));
    await api('/control/save',{path:first});assert.equal((await api('/api/state')).topics[0].name,'kept');
    const saved=readFileSync(settingsFile);unlinkSync(settingsFile);mkdirSync(settingsFile);
    await api('/control/save',{path:second},false);
    assert.equal(realpathSync((await api('/control/status')).home),realpathSync(first));
    assert.equal((await api('/control/status')).status,'ready');
    assert.equal((await api('/api/state')).topics[0].name,'kept');
    execFileSync('D:/code/dsh-deep-reading-runtime/.venv/Scripts/python.exe',['-c',"import sqlite3,sys;d=sqlite3.connect(sys.argv[1]);d.execute('PRAGMA user_version=99');d.close()",join(first,'topics.sqlite3')],{windowsHide:true});
    await api('/control/save',{path:second},false);
    const failed=await api('/control/status');assert.equal(failed.status,'failed');assert.equal(failed.activeHome,null);assert.ok(failed.error.includes('恢复失败'));
    execFileSync('D:/code/dsh-deep-reading-runtime/.venv/Scripts/python.exe',['-c',"import sqlite3,sys;d=sqlite3.connect(sys.argv[1]);d.execute('PRAGMA user_version=1');d.close()",join(first,'topics.sqlite3')],{windowsHide:true});
    rmSync(settingsFile,{recursive:true});writeFileSync(settingsFile,saved);
    await api('/control/retry',{});assert.equal((await api('/control/status')).status,'ready');
    picked='WAIT';const waiting=api('/control/pick',{},false);
    while(opened<3)await new Promise(resolve=>setTimeout(resolve,10));
    await fiber.dispose();await waiting;
    const again=ctx.plugin(plugin,{settingsFile,python:'D:/code/dsh-deep-reading-runtime/.venv/Scripts/python.exe'});await again;
    while(!server?.listening)await new Promise(resolve=>setTimeout(resolve,10));
    url=`http://127.0.0.1:${server.address().port}/deep-reading`;
    await ready();assert.equal(realpathSync((await api('/control/status')).home),realpathSync(first));
    assert.equal((await api('/api/state')).topics[0].name,'kept');
    await again.dispose();
    const early=ctx.plugin(plugin,{dataDir:join(tmp,'early'),settingsFile:join(tmp,'early.json'),python:'D:/code/dsh-deep-reading-runtime/.venv/Scripts/python.exe'});await early;await early.dispose();
    console.log('Installed Cordis runtime controller: PASS (injection, picker/cancel, auth, busy switch, invalid folder, empty/existing library, failed-save rollback, persisted restart, awaited dispose/reload, dispose before ready)');
  }finally{await fiber.dispose();rmSync(tmp,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
