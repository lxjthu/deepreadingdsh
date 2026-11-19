import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

test('batch control sends chosen mode and counts one merged task for two highlights',async()=>{
  const source=readFileSync(new URL('../web/pdf.js',import.meta.url),'utf8');
  for(const mode of ['separate','combined']){
    const nodes={},requests=[],selected=new Set(['a','b']);
    const context=vm.createContext({entryId:'paper',selectedHighlights:selected,state:{marks:[]},
      $:selector=>nodes[selector]??(nodes[selector]={value:mode,disabled:false,textContent:''}),
      guarded:fn=>fn,renderMarkList(){},refreshCards:async()=>{},
      api:async(path,body)=>{requests.push({path,body});return {generation_mode:mode,items:[{id:'one',annotation_id:'a'},{id:mode==='combined'?'one':'two',annotation_id:'b'}],errors:[]};},
    });
    vm.runInContext(source.slice(source.indexOf('function updateHighlightSelection()'),source.indexOf('async function api(')),context);
    await nodes['#highlights-generate'].onclick();
    assert.equal(requests[0].body.generation_mode,mode);
    assert.equal(nodes['#highlight-batch-status'].textContent.startsWith(mode==='combined'?'新建 1 个任务':'新建 2 个任务'),true);
    assert.equal(selected.size,0);
  }
});
