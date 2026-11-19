const $=s=>document.querySelector(s), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
if(window.parent!==window)document.documentElement.classList.add('dsh-embedded');
const endpoint=path=>new URL('.'+path,document.baseURI).href;
let token=location.hash.slice(1)||sessionStorage.getItem('reading-token')||'';
sessionStorage.setItem('reading-token',token); history.replaceState(null,'',location.pathname);
let state, topic=localStorage.getItem('reading-topic'), selected=new Set(), currentTab='library';
const statusNames={queued:'排队中',running:'运行中',completed:'已完成',failed:'失败',cancelled:'已取消',interrupted:'已中断'};
function notice(text){$('#notice').textContent=text;}
async function api(path,body){const r=await fetch(endpoint(path),{method:body===undefined?'GET':'POST',headers:{'X-Reading-Token':token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(v.error||r.status);return v;}
function guarded(fn){return async(...a)=>{try{await fn(...a);}catch(e){notice(e.message);}};}
function fileURL(path){return endpoint('/api/file?'+new URLSearchParams({path,token}));}
function switchTab(name){currentTab=name;document.querySelectorAll('.panel').forEach(e=>e.classList.toggle('hidden',e.id!==name));document.querySelectorAll('[data-tab]').forEach(e=>e.classList.toggle('active',e.dataset.tab===name));render();if(name==='wiki'&&window.loadWiki)guarded(()=>window.loadWiki())();}
function topicPapers(){const ids=new Set(state.links.filter(l=>l.topic_id===topic).map(l=>l.entry_id));return state.documents.filter(d=>ids.has(d.entry_id));}
const readingNames={none:'仅题录',has_pdf:'有原文',reading:'阅读中',read:'已阅读'}, completenessNames={full:'题录完整',partial:'部分题录',minimal:'题录待补充'};
function renderLibrary(papers){
  const ids=new Set(papers.map(p=>p.entry_id)),entries=(state.library||[]).filter(e=>ids.has(e.id));
  const oldTag=$('#tag-filter').value,tags=[...new Set(entries.flatMap(e=>e.tags))].sort();
  $('#tag-filter').innerHTML='<option value="">全部标签</option>'+tags.map(t=>`<option value="${esc(t)}">${esc(t)}</option>`).join('');$('#tag-filter').value=tags.includes(oldTag)?oldTag:'';
  const search=$('#search').value.toLowerCase(),status=$('#reading-filter').value,complete=$('#metadata-filter').value,tag=$('#tag-filter').value;
  const visible=entries.filter(e=>(!status||e.reading_status===status)&&(!complete||e.metadata_completeness===complete)&&(!tag||e.tags.includes(tag))&&JSON.stringify(e).toLowerCase().includes(search)).sort((a,b)=>b.is_pinned-a.is_pinned||a.title.localeCompare(b.title));
  $('#library-count').textContent=`显示 ${visible.length} / ${entries.length} 篇`;
  const markCounts=state.annotation_counts||{};
  $('#papers').innerHTML=visible.map(p=>`<div class="paper"><input type="checkbox" aria-label="选择 ${esc(p.title)}" data-select="${p.id}" ${selected.has(p.id)?'checked':''}><div class="paper-main"><h3><button class="title-button" data-detail="${p.id}">${p.is_pinned?'★ ':''}${esc(p.title)}</button></h3><div class="meta"><span class="badge">${esc(readingNames[p.reading_status])}</span><span class="badge">${esc(completenessNames[p.metadata_completeness])}</span>${esc(p.year||'年份待核对')} · ${esc(p.authors.join('、')||'作者待核对')} ${p.journal?' · '+esc(p.journal):''}</div>${p.abstract?`<p class="abstract-preview">${esc(p.abstract.slice(0,220))}${p.abstract.length>220?'…':''}</p>`:''}<div class="meta">${p.tags.map(t=>`<span class="badge">${esc(t)}</span>`).join('')} ${p.attachments.length} 个附件${markCounts[p.id]?` · <span class="badge marks">${markCounts[p.id]} 处标记</span>`:''}${p.review_warnings.length?' · 待核对':''}</div></div><div class="paper-actions"><button data-detail="${p.id}">题录与成果</button>${p.attachments.length?`<button data-source="${p.id}" class="primary">查看原文</button>`:''}</div></div>`).join('')||`<div class="empty"><h3>${entries.length?'没有匹配的文献':'让研究从一篇论文开始'}</h3><p>${entries.length?'调整搜索或筛选条件。':'导入整个文件夹，自动建立题录与原文附件。'}</p></div>`;
}
const fieldNames={title:'题名',authors:'作者（分号分隔）',year:'年份',journal:'期刊',doi:'DOI',language:'语言（zh/en/other）',volume:'卷',issue:'期',pages:'页码',venue_type:'文献类型',keywords:'关键词（分号分隔）',abstract:'原文摘要',abstract_cn:'中文摘要'};
let detailId=null;
function openLibraryDetail(id){
  const e=state.library.find(e=>e.id===id);detailId=id;
  $('#library-fields').innerHTML=Object.entries(fieldNames).map(([k,label])=>`<label class="${['title','abstract','abstract_cn'].includes(k)?'wide':''}">${label}${k.startsWith('abstract')?`<textarea rows="4" data-meta="${k}">${esc(e[k]||'')}</textarea>`:`<input data-meta="${k}" value="${esc(Array.isArray(e[k])?e[k].join('；'):e[k]||'')}" ${k==='title'?'required':''}>`}</label>`).join('');
  $('#entry-tags').value=e.tags.join('；');$('#entry-note').value=e.note;$('#entry-pinned').checked=!!e.is_pinned;$('#library-save-status').textContent=e.review_warnings.join('；');
  $('#entry-attachments').innerHTML=e.attachments.map(a=>`<p><a href="${esc(fileURL('workspace/'+a.path))}" target="_blank" rel="noopener">${esc(a.label)}</a> <small>${esc(a.relative_path||a.file_type)}</small>${a.file_type==='pdf'?` · <button type="button" data-pdf="${e.id}">查看 PDF 原文</button> · <button type="button" data-embed="${e.id}">嵌入查看</button>`:''}${a.markdown?` · <a href="${esc(fileURL('workspace/'+a.markdown))}" target="_blank" rel="noopener">提取文本</a>`:''}</p>`).join('')||'<p>尚未关联原文。</p>';
  $('#entry-timeline').innerHTML=e.timeline.map(t=>`<p>${new Date(t.created*1000).toLocaleString()} · ${esc(state.capabilities[t.task]||t.task)} · ${esc(statusNames[t.status])}</p>${(t.result?.artifacts||[]).map(a=>`<p><a href="${esc(fileURL('workspace/'+a.path))}" target="_blank" rel="noopener">${esc(a.kind)}</a></p>`).join('')}`).join('')||'<p>尚未开始阅读或分析。</p>';
  $('#entry-wiki').innerHTML='<p>正在读取关联实体…</p>';if(window.paperWiki)window.paperWiki(id);
  $('#library-detail').showModal();
}
function render(){if(!state)return;if(!state.topics.some(t=>t.id===topic)){topic=state.topics[0]?.id;selected.clear();}const current=state.topics.find(t=>t.id===topic);
  $('#topics').innerHTML=state.topics.map(t=>`<button data-topic="${t.id}" class="${t.id===topic?'active':''}">${esc(t.name)}</button>`).join('');
  $('#topic-name').textContent=current?.name||'开始你的文献研究';$('#topic-description').textContent=current?.description||'创建主题，导入论文，连接证据与研究问题。';
  const papers=topicPapers(),tasks=state.tasks.filter(t=>t.topic_id===topic);selected=new Set([...selected].filter(id=>papers.some(p=>p.entry_id===id)));
  $('#paper-count').textContent=papers.length;$('#result-count').textContent=tasks.filter(t=>t.status==='completed'&&t.task!=='import').length;$('#active-count').textContent=tasks.filter(t=>['queued','running'].includes(t.status)).length;
  renderLibrary(papers);if($('#wiki-selection'))$('#wiki-selection').textContent='当前勾选 '+selected.size+' 篇：'+papers.filter(p=>selected.has(p.entry_id)).map(p=>p.title).join('；');
  $('#shared-papers').innerHTML=state.documents.filter(d=>!papers.some(p=>p.entry_id===d.entry_id)).map(d=>`<div class="paper"><div class="paper-main">${esc(d.title)}</div><button data-link="${d.entry_id}">加入当前主题</button></div>`).join('')||'<p>没有其他可加入的文献。</p>';
  $('#selected-summary').innerHTML=papers.filter(p=>selected.has(p.entry_id)).map(p=>`<p>• ${esc(p.title)}</p>`).join('')||'<p>尚未选择文献。</p>';
  $('#tasks').innerHTML=tasks.map(t=>`<div class="task-row"><div class="paper-main"><span class="badge">${esc(statusNames[t.status]||t.status)}</span><b>${esc(state.capabilities[t.task]||t.task)}</b><p>${esc(t.params.question||t.params.path||(t.task==='wiki.extract'?'提取所选论文研究知识':t.task==='pdf.card'?'PDF 选段自动制卡':'文件夹批量导入'))}${t.error?'<br>'+esc(t.error):''}</p>${t.task==='wiki.extract'&&t.result?`<p>全文分段 ${t.result.chunks||0} / ${t.result.total_chunks||'?'} · 本次新增候选 ${t.result.new_records||0}</p>`:''}${t.task==='import'&&t.result?`<p>已处理 ${t.result.processed||0} / ${t.result.total||0} · 重复 ${t.result.duplicates||0} · 失败 ${t.result.failed||0} · 待核对 ${t.result.review_count||0} · 跳过 ${t.result.skipped?.length||0}</p>`:''}<div class="meta">${new Date(t.created*1000).toLocaleString()} · ${t.id.slice(0,8)}</div>${t.result?`<button data-result="${t.id}">查看结果</button>`:''}${['failed','interrupted','cancelled'].includes(t.status)?`<button data-resume="${t.id}">继续任务</button>`:''}${['running','queued'].includes(t.status)?`<button data-cancel="${t.id}">取消</button>`:''}</div></div>`).join('')||'<div class="empty">还没有研究任务。</div>';
  $('#idea-results').innerHTML=tasks.filter(t=>t.task.startsWith('idea-lab')&&t.status==='completed').map(t=>`<div class="card"><h3>${esc(state.capabilities[t.task])}</h3><p>构念 ${t.result.constructs?.length||0} · 证据缺口 ${t.result.gaps?.length||0} · 候选选题 ${t.result.ideas?.length||0}</p><button data-result="${t.id}">查看构思与证据</button></div>`).join('');
}
async function refresh(){state=await api('/api/state');if(!$('#task').options.length){$('#task').innerHTML=Object.entries(state.capabilities).filter(([k])=>!k.startsWith('idea-lab')&&k!=='import'&&k!=='pdf.card').map(([k,v])=>`<option value="${k}">${esc(v)}</option>`).join('');}render();}
async function start(task,question){if(!topic)throw Error('请先创建研究主题');if(!selected.size)throw Error('请在文献库选择文献');let variables={};if($('#variables').value.trim())variables=JSON.parse($('#variables').value);const dimensions=$('#dimensions').value.trim();await api('/api/tasks',{topic_id:topic,task,entry_ids:[...selected],question,variables,dimension_set:$('#dimension-set').value,...(dimensions?{dimensions:dimensions.split(/[,，]/).map(x=>x.trim()).filter(Boolean)}:{})});notice('任务已加入队列，模型由 dsh 提供。');switchTab('results');await refresh();}
document.addEventListener('click',guarded(async e=>{const b=e.target.closest('button');if(!b)return;
  if(b.dataset.tab)return switchTab(b.dataset.tab);
  if(b.dataset.close)return $('#'+b.dataset.close).close();
  if(b.dataset.topic){topic=b.dataset.topic;localStorage.setItem('reading-topic',topic);selected.clear();return render();}
  if(b.dataset.link){await api('/api/link',{topic_id:topic,entry_id:b.dataset.link});return refresh();}
  if(b.dataset.detail)return openLibraryDetail(b.dataset.detail);
  if(b.dataset.resume){await api('/api/resume',{id:b.dataset.resume});return refresh();}
  if(b.dataset.cancel){await api('/api/cancel',{id:b.dataset.cancel});return refresh();}
  if(b.dataset.source)return openSource(b.dataset.source);
  if(b.dataset.pdf)return openSource(b.dataset.pdf);
  if(b.dataset.embed)return openSource(b.dataset.embed);
  if(b.dataset.result){const t=state.tasks.find(t=>t.id===b.dataset.result);$('#viewer-title').textContent=state.capabilities[t.task];$('#viewer-links').innerHTML=(t.result.artifacts||[]).map(a=>`<a href="${esc(fileURL('workspace/'+a.path))}" target="_blank" rel="noopener">下载 ${esc(a.kind)}</a>`).join('');const artifacts=await Promise.all((t.result.artifacts||[]).map(async a=>{if(!a.path.endsWith('.md'))return '';const r=await fetch(fileURL('workspace/'+a.path));return r.text();}));$('#viewer-content').textContent=artifacts.filter(Boolean).join('\n\n────────────────\n\n')||(t.task==='import'?importMarkdown(t.result):t.task.startsWith('idea-lab')?ideaMarkdown(t.result):JSON.stringify(t.result,null,2));await previewContent();return $('#viewer').showModal();}
}));
function pdfAttachment(entryId){const e=state.library.find(item=>item.id===entryId);return e?e.attachments.find(a=>a.file_type==='pdf'):null;}
function pdfURL(entryId){return endpoint('/pdf')+'#'+new URLSearchParams({entry_id:entryId,token}).toString();}
let embedEntry=null;
function embedPdf(url){$('#pdf-frame').src=url;const dialog=$('#pdf-dialog');if(!dialog.open)dialog.showModal();return null;}
async function openPdfWindow(entryId){
  embedEntry=entryId;
  $('#pdf-open-status').textContent='正在准备浏览器阅读连接…';
  const session=await api('/api/pdf/session',{entry_id:entryId});
  if(embedEntry!==entryId)return null;
  const link=$('#pdf-external');link.href=session.url;link.hidden=false;
  const win=window.open(session.url,'_blank');
  $('#pdf-open-status').textContent='已准备浏览器阅读连接。如果浏览器没有打开，请点击旁边的“打开阅读页”。';
  return win;
}
function openSource(entryId){
  if(!pdfAttachment(entryId))return openTextViewer(entryId);
  embedEntry=entryId;$('#pdf-open-status').textContent='';$('#pdf-external').hidden=true;$('#pdf-external').removeAttribute('href');
  return embedPdf(pdfURL(entryId));
}
async function openTextViewer(entryId){const p=state.documents.find(d=>d.entry_id===entryId),doc=await api('/api/document?entry_id='+entryId);$('#viewer-title').textContent=p?.title||'研究内容';$('#viewer-content').textContent=(doc.pages||[]).map(page=>`── 第 ${page.page||'?'} 页 ──\n${page.text}`).join('\n\n')||doc.text;$('#viewer-links').innerHTML=(p?.sources||[]).map(s=>`<a href="${esc(fileURL('workspace/'+s.path))}" target="_blank" rel="noopener">打开原文件</a>`).join('');await previewContent();return $('#viewer').showModal();}
$('#pdf-pop').onclick=async()=>{try{if(!embedEntry)throw Error('请先打开一份原文');await openPdfWindow(embedEntry);}catch(error){$('#pdf-open-status').textContent='打开浏览器失败：'+error.message;}};
document.addEventListener('change',e=>{if(e.target.dataset.select){if(e.target.checked)selected.add(e.target.dataset.select);else selected.delete(e.target.dataset.select);render();}});
$('#search').addEventListener('input',render);
for(const id of ['reading-filter','metadata-filter','tag-filter'])$('#'+id).addEventListener('change',render);
$('#library-form').onsubmit=guarded(async e=>{e.preventDefault();const metadata={};document.querySelectorAll('[data-meta]').forEach(input=>{metadata[input.dataset.meta]=['authors','keywords'].includes(input.dataset.meta)?input.value.split(/[;；]/).map(x=>x.trim()).filter(Boolean):input.value;});await api('/api/library',{entry_id:detailId,metadata,tags:$('#entry-tags').value.split(/[;；]/).map(x=>x.trim()).filter(Boolean),note:$('#entry-note').value,is_pinned:$('#entry-pinned').checked});$('#library-save-status').textContent='已保存';await refresh();});
$('#new-topic').onclick=()=>$('#topic-dialog').showModal();
$('#topic-form').onsubmit=guarded(async e=>{e.preventDefault();const r=await api('/api/topics',{name:$('#new-name').value,description:$('#new-description').value});topic=r.id;localStorage.setItem('reading-topic',topic);selected.clear();$('#topic-dialog').close();e.target.reset();await refresh();});
$('#import-open').onclick=guarded(async()=>{if(!topic)throw Error('请先创建主题');$('#import-dialog').showModal();});
let stagedImports=[];
$('#import-submit').onclick=guarded(async()=>{
  const chosen=[...$('#import-file').files,...$('#import-folder').files],path=$('#import-path').value.trim(),engine=$('#engine').value,auto_organize=$('#auto-organize').checked;
  const supported=f=>/\.(pdf|md|markdown|txt)$/i.test(f.name)&&!f.name.toLowerCase().endsWith('.source.md');
  const files=chosen.filter(supported),skipped=chosen.filter(f=>!supported(f)).map(f=>({path:f.webkitRelativePath||f.name,reason:'不支持的格式或说明文件'}));
  if(!files.length&&!path)throw Error('请选择包含 PDF、Markdown 或题录的文件夹，或填写本机路径');
  if(files.some(f=>f.size>65*1024**2))throw Error('有文件超过 65 MiB，请使用本机文件夹路径导入');
  const button=$('#import-submit');button.disabled=true;
  try{
    for(let i=0;i<files.length;i++){
      const file=files[i],key=(file.webkitRelativePath||file.name)+':'+file.size+':'+file.lastModified;
      if(stagedImports.some(x=>x.key===key))continue;
      $('#import-progress').textContent=`正在准备 ${i+1} / ${files.length}：${file.webkitRelativePath||file.name}`;
      const data=new Uint8Array(await file.arrayBuffer());let binary='';for(let offset=0;offset<data.length;offset+=32768)binary+=String.fromCharCode(...data.subarray(offset,offset+32768));
      const item=await api('/api/upload',{topic_id:topic,name:file.name,relative_path:file.webkitRelativePath||file.name,data:btoa(binary),stage:true});stagedImports.push({key,item});
    }
    const keys=new Set(files.map(f=>(f.webkitRelativePath||f.name)+':'+f.size+':'+f.lastModified));
    const paths=stagedImports.filter(x=>keys.has(x.key)).map(x=>x.item);if(path)paths.unshift({path});
    await api('/api/import',{topic_id:topic,paths,engine,auto_organize,skipped});stagedImports=[];
    $('#import-dialog').close();$('#import-file').value='';$('#import-folder').value='';$('#import-path').value='';$('#import-progress').textContent='';
    notice('批量导入已排队。可查看逐文件进度；原始文件会保留。');switchTab('results');await refresh();
  }catch(e){$('#import-progress').textContent=e.message+'；已准备的文件保留，可重试。';throw e;}finally{button.disabled=false;}
});
$('#run').onclick=guarded(()=>start($('#task').value,$('#question').value));$('#idea-run').onclick=guarded(()=>start('idea-lab',''));$('#idea-deepen').onclick=guarded(()=>start('idea-lab.deepen',$('#idea-question').value));
$('#backup').onclick=guarded(async()=>{const r=await api('/api/backup',{});notice('备份已保存：'+r.path);const a=document.createElement('a');a.href=fileURL(r.relative_path);a.download=r.path.split(/[\\/]/).pop();a.click();});
$('#prompt-load').onclick=guarded(async()=>{$('#prompt-text').value=(await api('/api/prompt?slot='+encodeURIComponent($('#prompt-select').value))).text;});
$('#prompt-save').onclick=guarded(async()=>{await api('/api/prompt',{slot:$('#prompt-select').value,text:$('#prompt-text').value});notice('提示词已保存，旧版本已保留。');});
guarded(async()=>{await refresh();await loadDimensions();const p=await api('/api/prompts');$('#prompt-select').innerHTML=p.slots.map(s=>`<option>${esc(s)}</option>`).join('');if(!state.topics.length)$('#topic-dialog').showModal();})();setInterval(guarded(refresh),2500);

async function previewContent(){const r=await api('/api/render',{text:$('#viewer-content').textContent});$('#viewer-body').innerHTML=r.html;}
async function loadDimensions(){const d=await api('/api/dimensions');$('#dimension-set').innerHTML='<option value="">内置维度</option>'+d.custom.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('');}
$('#dimension-save').onclick=guarded(async()=>{await api('/api/dimensions',{name:$('#dimension-name').value,data:JSON.parse($('#dimension-json').value)});await loadDimensions();notice('维度模板已保存，可在精读与分析中选择。');});
function ideaMarkdown(r){let s='# '+(r.topic||'研究构思')+'\n\n';for(const c of r.constructs||[]){s+='## 构念：'+c.name+'\n\n'+c.definition+'\n\n';for(const [label,key] of [['理论基础','theory_base'],['机制','mechanisms'],['测量','measurement'],['情境','context']])s+='### '+label+'\n'+(c[key]||[]).map(v=>'- '+v).join('\n')+'\n\n';s+='### 原文证据\n'+(c.evidence||[]).map(e=>'- ['+e.entry_id+'] 第 '+(e.page_number||e.page||'未定位')+' 页：'+e.quote).join('\n')+'\n\n';}s+='## 当前材料的证据缺口\n\n'+(r.gaps||[]).map(g=>'- '+g.summary).join('\n')+'\n\n## 候选选题\n\n';for(const i of r.ideas||[])s+='### '+i.title+'\n\n'+(i.hypotheses||[]).map(h=>'- '+h).join('\n')+'\n\n'+JSON.stringify(i.data_strategy,null,2)+'\n\n';if(r.analysis)s+='## dsh 深化分析\n\n'+r.analysis+'\n\n';s+='## 研究限制\n\n'+(r.limitations||[]).map(l=>'- '+l).join('\n');return s;}

function importMarkdown(r){let text='# 批量导入结果\n\n已处理 '+r.processed+' / '+r.total+'；重复 '+r.duplicates+'；失败 '+r.failed+'；待核对 '+r.review_count+'。\n\n';for(const file of r.files||[]){text+='## '+(file.relative_path||file.path).replace(/[\r\n]/g,' ')+'\n\n'+(file.status==='duplicate'?'重复原文，已复用现有文献':file.status==='failed'?'导入失败：'+file.error:'已导入')+'\n\n';for(const warning of file.review_warnings||[])text+='- 待核对：'+warning+'\n';}if(r.skipped?.length)text+='\n## 跳过的文件\n\n'+r.skipped.map(f=>'- '+f.path+'：'+f.reason).join('\n');return text;}
