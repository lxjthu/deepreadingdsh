/* A separately addressable card editor using the current document's admission. */
const $=selector=>document.querySelector(selector);
const params=new URLSearchParams(location.hash.slice(1));
const entryId=params.get('entry_id')||sessionStorage.getItem('card-entry')||'';
const cardId=params.get('card_id')||sessionStorage.getItem('card-id')||'';
const token=params.get('token')||sessionStorage.getItem('card-token')||'';
for(const [key,value] of [['card-entry',entryId],['card-id',cardId],['card-token',token]])sessionStorage.setItem(key,value);
history.replaceState(null,'',location.pathname+location.search);
let card,dirty=false,previewTimer,previewGeneration=0;
const status=message=>{$('#status').textContent=message;};
const endpoint=path=>new URL('.'+path,document.baseURI).href;
async function api(path,body){
  const response=await fetch(endpoint(path),{method:body===undefined?'GET':'POST',headers:{'X-Reading-Token':token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const result=await response.json();if(!response.ok)throw Error(result.error||response.status);return result;
}
function setDirty(value){dirty=value;$('#save').disabled=!dirty;if(parent!==window)parent.postMessage({type:'card-editor-dirty',dirty},location.origin==='null'?'*':location.origin);}
function values(){return {title:$('#title').value,summary:$('#summary').value,tags:$('#tags').value.split(/[;；]/).map(value=>value.trim()).filter(Boolean),body_markdown:$('#body').value};}
async function preview(){
  const generation=++previewGeneration,fields=values();
  $('#preview-title').textContent=fields.title;$('#preview-summary').textContent=fields.summary;$('#preview-tags').textContent=fields.tags.join(' · ');
  try{
    const result=await api('/api/cards/render',{entry_id:entryId,id:cardId,text:fields.body_markdown});
    if(generation!==previewGeneration)return;
    $('#preview-body').innerHTML=result.html;
    for(const formula of $('#preview-body').querySelectorAll('[data-tex]')){
      try{window.katex.render(formula.dataset.tex,formula,{output:'mathml',displayMode:formula.dataset.display==='true',throwOnError:true,trust:false,strict:'warn'});}
      catch(error){formula.textContent=formula.dataset.tex;formula.title='公式排版失败，已保留 LaTeX 原文。';}
    }
    for(const link of $('#preview-body').querySelectorAll('a')){link.target='_blank';link.rel='noopener noreferrer';}
  }catch(error){if(generation===previewGeneration){$('#preview-body').textContent=fields.body_markdown;status('预览失败：'+error.message);}}
}
function showSource(){
  $('#citation').textContent=card.paper_citation||card.paper_title;
  $('#metadata-origin').textContent=card.paper_metadata_origin==='generation_snapshot'?'题录为生成卡片时保存的快照。':'此旧卡片的题录补充自当前文献库。';
  const metadata=card.paper_metadata||{};
  const fields=[['题名',metadata.title],['作者',(metadata.authors||[]).join('、')],['年份',metadata.year],['期刊',metadata.journal],['卷',metadata.volume],['期',metadata.issue],['文献页码',metadata.pages],['DOI',metadata.doi],['文献标识',entryId],['生成方式',card.generation_mode==='combined'?'多选段合并':'独立选段'],['选段数量',card.regions?.length||card.selection_parts?.length||1],['PDF 物理页',[...new Set(card.segments.map(segment=>segment.page))].join(', ')],['来源版本',card.source_version],['文件 SHA256',card.source_sha256]];
  const list=$('#properties');list.textContent='';
  for(const [label,value] of fields){const term=document.createElement('dt'),description=document.createElement('dd');term.textContent=label;description.textContent=value||'未填写';list.append(term,description);}
  const excerpts=$('#excerpt-contexts');excerpts.textContent='';
  for(const [index,part] of (card.selection_parts||[]).entries()){
    const detail=document.createElement('details'),summary=document.createElement('summary'),body=document.createElement('p');
    summary.textContent='选段 '+(index+1)+' · 物理页 '+part.segments.map(segment=>segment.page).join(', ');
    body.textContent='上文：\n'+part.context_before+'\n\n原文：\n'+part.selected_text+'\n\n下文：\n'+part.context_after;body.className='excerpt-context';detail.append(summary,body);excerpts.append(detail);
  }
  const images=$('#card-images');images.textContent='';
  for(const asset of card.images||[]){const figure=document.createElement('figure'),image=document.createElement('img'),caption=document.createElement('figcaption');
    image.src=endpoint('/api/visual/image?'+new URLSearchParams({entry_id:entryId,id:asset.region_id,token}));image.alt='物理页 '+asset.page+' 原始裁剪图';caption.textContent=image.alt;figure.append(image,caption);images.append(figure);}
  const recognition=$('#card-recognition');recognition.textContent='';
  for(const part of card.visual_recognition||[]){const detail=document.createElement('details'),summary=document.createElement('summary'),text=document.createElement('pre');summary.textContent='视觉识别 · 物理页 '+part.page+' · 待核对';text.textContent=part.markdown+'\n\n待核对：'+(part.uncertainties.join('；')||'需人工核对');detail.append(summary,text);recognition.append(detail);}
  $('#quote').textContent=card.selected_text;$('#before').textContent=card.context_before;$('#after').textContent=card.context_after;
}
async function load(){
  if(!entryId||!cardId)throw Error('缺少卡片标识，请从原文阅读页重新点击预览卡片。');
  const result=await api('/api/cards?'+new URLSearchParams({entry_id:entryId}));
  card=result.items.find(item=>item.id===cardId);if(!card)throw Error('卡片不存在或不属于当前文献。');
  $('#card-title').textContent=card.title;document.title=card.title+' · 卡片';
  $('#title').value=card.title;$('#summary').value=card.summary;$('#tags').value=card.tags.join(';');$('#body').value=card.body_markdown;
  showSource();setDirty(false);$('#export').disabled=false;status(card.source_current?'卡片已载入。':'原 PDF 来源已变化，已保留卡片与原始来源记录。');await preview();
}
for(const id of ['title','summary','tags','body'])$('#'+id).oninput=()=>{setDirty(true);clearTimeout(previewTimer);previewTimer=setTimeout(preview,350);};
$('#save').onclick=async()=>{
  $('#save').disabled=true;
  try{
    const saveResult=await api('/api/cards/action',{entry_id:entryId,id:cardId,op:'edit',expected_updated:card.updated,...values()});
    // Keep edits made while the save request was in flight instead of replacing them.
    const result=await api('/api/cards?'+new URLSearchParams({entry_id:entryId}));
    const saved=result.items.find(item=>item.id===cardId);if(!saved)throw Error('保存后未找到卡片，请重新加载核对。');
    card=saved;const local=values();setDirty(JSON.stringify(local)!==JSON.stringify({title:card.title,summary:card.summary,tags:card.tags,body_markdown:card.body_markdown}));
    $('#card-title').textContent=card.title;showSource();status(saveResult.note_file?.error?'数据库已保存，笔记同步失败：'+saveResult.note_file.error:dirty?'已保存提交时的内容，后续输入尚未保存。':'卡片与本地笔记已保存。');
  }catch(error){status('保存失败：'+error.message);$('#save').disabled=!dirty;}
};
$('#reload').onclick=()=>{if(dirty&&!confirm('有未保存的修改，仍要重新加载吗？'))return;clearTimeout(previewTimer);load().catch(error=>status(error.message));};
$('#export').onclick=()=>{
  if(dirty){status('请先保存修改后再导出。');return;}
  const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([card.markdown],{type:'text/markdown;charset=utf-8'}));link.download=card.title.replace(/[\\/:*?"<>|]/g,'_').slice(0,60)+'.md';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),4000);
};
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
load().catch(error=>status('无法读取卡片：'+error.message));
