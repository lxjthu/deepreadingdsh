/* PDF original viewer: renders pages from the local service and stores marks. */
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const round = value => Math.round(value * 100000) / 100000;
const endpoint = path => new URL('.' + path, document.baseURI).href;
const COLOR_NAMES = {yellow: '黄色', green: '绿色', pink: '粉色', blue: '蓝色', orange: '橙色'};
const COLORS = Object.keys(COLOR_NAMES);
const KIND_NAMES = {highlight: '高亮', box: '框选', note: '便签', underline: '下划线'};

const hash = new URLSearchParams(location.hash.slice(1));
let token = hash.get('token') || sessionStorage.getItem('pdf-token') || '';
const entryId = hash.get('entry_id') || sessionStorage.getItem('pdf-entry') || '';
if (token) sessionStorage.setItem('pdf-token', token);
if (entryId) sessionStorage.setItem('pdf-entry', entryId);
if (location.hash) history.replaceState(null, '', location.pathname + location.search);

const state = {
  meta: null, marks: [], pages: new Map(), scale: 1, fit: 1, raster: 1,
  zoom: clamp(Number(localStorage.getItem('pdf-zoom')) || 1, 0.25, 4),
  tool: 'select', color: COLORS.includes(localStorage.getItem('pdf-color')) ? localStorage.getItem('pdf-color') : 'yellow',
  editor: null, observer: null,
};
const selectedHighlights = new Set();
const selectedVisualBoxes = new Set();
let visualBusy=false,visualSignature='';

function updateVisualSelection(){
  $('#visual-count').textContent='已选 '+selectedVisualBoxes.size+' 个框选区域';
  $('#visual-generate').disabled=visualBusy||!selectedVisualBoxes.size;
}
$('#visual-all').onclick=()=>{for(const mark of state.marks)if(mark.kind==='box')selectedVisualBoxes.add(mark.id);renderMarkList();};
$('#visual-none').onclick=()=>{selectedVisualBoxes.clear();renderMarkList();};
$('#visual-generate').onclick=guarded(()=>submitVisual([...selectedVisualBoxes]));
async function submitVisual(ids){
  if(visualBusy||!ids.length)return;
  visualBusy=true;updateVisualSelection();$('#visual-status').textContent='正在提交视觉识别任务…';
  try{
    const result=await api('/api/cards/visual',{entry_id:entryId,annotation_ids:ids,generation_mode:$('#visual-generation-mode').value});
    const tasks=[...new Map(result.items.map(item=>[item.id,item])).values()];
    $('#visual-status').textContent='提交 '+tasks.length+' 个任务，其中复用 '+tasks.filter(item=>item.duplicate).length+' 个；失败 '+result.errors.length+' 条。'+result.errors.map(item=>'\n区域 '+item.annotation_id+'：'+item.error).join('');
    if(result.generation_mode==='combined'&&result.errors.length)$('#visual-status').textContent+='\n合并未提交，请核对全部区域。';
    for(const item of result.items)selectedVisualBoxes.delete(item.annotation_id);
    renderMarkList();await refreshCards();toggleMarksPanel(true);
  }catch(error){$('#visual-status').textContent='提交失败：'+error.message;}
  finally{visualBusy=false;updateVisualSelection();}
}
async function refreshVisualResults(){
  const result=await api('/api/visuals?'+new URLSearchParams({entry_id:entryId}));
  const signature=JSON.stringify(result);if(signature===visualSignature)return;visualSignature=signature;
  const host=$('#visual-results');host.textContent='';
  for(const part of result.items){
    const detail=element('details'),title=element('summary','','物理页 '+part.page+' · '+({text:'文字',formula:'公式',table:'表格',figure:'图形',mixed:'混合'}[part.kind]||part.kind)+' · 待核对');
    const image=element('img');image.alt='原始框选裁剪图';image.loading='lazy';image.src=endpoint('/api/visual/image?'+new URLSearchParams({entry_id:entryId,id:part.id,token}));
    detail.append(title,image,element('pre','',part.markdown),element('p','','待核对：'+(part.uncertainties.join('；')||'需人工核对识别结果')));host.append(detail);
  }
}

function updateHighlightSelection() {
  const mode=$('#highlight-generation-mode').value;
  $('#highlight-selection-count').textContent='已选 '+selectedHighlights.size+' 条高亮'+(mode==='combined'?'（合并生成一张卡片）':'（每条生成一张卡片）');
  $('#highlights-generate').disabled=!selectedHighlights.size;
}
$('#highlight-generation-mode').onchange=updateHighlightSelection;
$('#highlights-all').onclick=()=>{for(const mark of state.marks)if(mark.kind==='highlight'&&mark.quote)selectedHighlights.add(mark.id);renderMarkList();};
$('#highlights-none').onclick=()=>{selectedHighlights.clear();renderMarkList();};
$('#highlights-generate').onclick=guarded(async()=>{
  if(!selectedHighlights.size)return;
  const button=$('#highlights-generate');button.disabled=true;
  const status=$('#highlight-batch-status');status.textContent='正在提交所选高亮…';
  try{
    const result=await api('/api/cards/batch',{entry_id:entryId,annotation_ids:[...selectedHighlights],generation_mode:$('#highlight-generation-mode').value});
    const tasks=[...new Map(result.items.map(item=>[item.id,item])).values()];
    const duplicates=tasks.filter(item=>item.duplicate).length;
    status.textContent='新建 '+(tasks.length-duplicates)+' 个任务，复用 '+duplicates+' 个任务，失败 '+result.errors.length+' 条。'+result.errors.map(item=>'\n高亮 '+item.annotation_id+'：'+item.error).join('');
    if(result.generation_mode==='combined'&&result.errors.length)status.textContent+='\n合并未提交，请修正失败条目或取消勾选后重试。';
    for(const item of result.items)selectedHighlights.delete(item.annotation_id);
    renderMarkList();await refreshCards();
  }catch(error){status.textContent='批量提交失败：'+error.message;}
  finally{updateHighlightSelection();}
});

async function api(path, body) {
  const response = await fetch(endpoint(path), {
    method: body === undefined ? 'GET' : 'POST',
    headers: {'X-Reading-Token': token, 'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const value = await response.json().catch(() => ({error: '服务返回内容无法解析'}));
  if (!response.ok) throw new Error(value.error || String(response.status));
  return value;
}
const fileURL = path => endpoint('/api/file?' + new URLSearchParams({path, token}));
const imageURL = page => endpoint('/api/pdf/page?' + new URLSearchParams({entry_id: entryId, page, scale: state.raster, token}));

let statusTimer = null;
function setStatus(text, warn = false) {
  const bar = $('#status');
  bar.textContent = text;
  bar.classList.toggle('warn', !!warn);
  bar.classList.add('show');
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => bar.classList.remove('show'), warn ? 7000 : 3600);
}
function guarded(fn) {
  return async (...args) => {
    try { return await fn(...args); } catch (error) { setStatus(error.message, true); }
  };
}
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function button(label, onClick, className) {
  const node = element('button', className || '', label);
  node.type = 'button';
  node.addEventListener('click', onClick);
  return node;
}

/* ---------- layout ---------- */

function buildPages() {
  const host = $('#pages');
  host.textContent = '';
  state.pages.clear();
  for (const page of state.meta.pages) {
    const section = element('section', 'page');
    section.dataset.page = String(page.number);
    section.id = 'page-' + page.number;
    const image = element('img', 'page-image');
    image.alt = '第 ' + page.number + ' 页';
    image.decoding = 'async';
    const text = element('div', 'text-layer');
    const marks = element('div', 'mark-layer');
    const label = element('div', 'page-label', '第 ' + page.number + ' 页');
    section.append(image, text, marks, label);
    host.append(section);
    state.pages.set(page.number, {section, image, text, marks, loaded: false, textLoaded: false, raster: 0});
  }
}

function layout() {
  if (!state.meta) return;
  const host = $('#pages');
  const style = getComputedStyle(host);
  const available = Math.max(240, host.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight));
  const widest = Math.max(...state.meta.pages.map(page => page.width));
  state.fit = clamp(available / widest, 0.2, 3);
  state.scale = state.fit * state.zoom;
  state.raster = Math.round(clamp(state.scale * (window.devicePixelRatio || 1), 0.4, 3) * 100) / 100;
  for (const page of state.meta.pages) {
    const node = state.pages.get(page.number);
    node.section.style.width = (page.width * state.scale) + 'px';
    node.section.style.height = (page.height * state.scale) + 'px';
    for (const span of node.text.children) span.style.fontSize = (Number(span.dataset.height) * state.scale * 0.94) + 'px';
    if (node.loaded && node.raster !== state.raster) {
      node.raster = state.raster;
      node.image.src = imageURL(page.number);
    }
  }
  $('#zoom-label').textContent = Math.round(state.zoom * 100) + '%';
}

function loadPage(number) {
  const node = state.pages.get(number);
  if (!node || node.loaded) return;
  node.loaded = true;
  node.raster = state.raster;
  node.image.src = imageURL(number);
  if (!node.textLoaded) {
    node.textLoaded = true;
    loadText(number).catch(error => setStatus('第 ' + number + ' 页文字层读取失败：' + error.message, true));
  }
}

function observePages() {
  state.observer?.disconnect();
  state.observer = new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) loadPage(Number(entry.target.dataset.page));
  }, {rootMargin: '900px 0px'});
  for (const node of state.pages.values()) state.observer.observe(node.section);
}

async function loadText(number) {
  const data = await api('/api/pdf/text?' + new URLSearchParams({entry_id: entryId, page: number}));
  const node = state.pages.get(number);
  const page = state.meta.pages[number - 1];
  const layer = node.text;
  layer.textContent = '';
  for (const [wordIndex, word] of (data.words || []).entries()) {
    const [x0, y0, x1, y1, text] = word;
    const span = element('span', '', text);
    span.dataset.word = String(wordIndex);
    span.dataset.height = String(y1-y0);
    span.style.left = (x0 / page.width * 100) + '%';
    span.style.top = (y0 / page.height * 100) + '%';
    span.style.width = ((x1 - x0) / page.width * 100) + '%';
    span.style.height = ((y1 - y0) / page.height * 100) + '%';
    span.style.fontSize = Math.max(1, (y1 - y0) * state.scale * 0.94) + 'px';
    layer.append(span);
  }
}

/* ---------- marks ---------- */

function updateCount() {
  $('#mark-count').textContent = state.marks.length;
}

function renderMarks() {
  for (const node of state.pages.values()) node.marks.textContent = '';
  for (const mark of state.marks) {
    const node = state.pages.get(mark.page);
    if (!node) continue;
    const rects = mark.rects || [];
    if (mark.kind === 'note') {
      const point = rects[0] || [0, 0, 0, 0];
      const pin = element('div', 'mark kind-note color-' + mark.color);
      pin.dataset.id = mark.id;
      pin.title = mark.note || '便签';
      pin.style.left = ((point[0] + point[2]) / 2 * 100) + '%';
      pin.style.top = ((point[1] + point[3]) / 2 * 100) + '%';
      pin.style.width = '24px';
      pin.style.height = '24px';
      pin.style.marginLeft = '-12px';
      pin.style.marginTop = '-12px';
      node.marks.append(pin);
      continue;
    }
    for (const rect of rects) {
      const patch = element('div', 'mark kind-' + mark.kind + ' color-' + mark.color);
      patch.dataset.id = mark.id;
      patch.title = mark.quote || mark.note || KIND_NAMES[mark.kind] || '标记';
      patch.style.left = (rect[0] * 100) + '%';
      patch.style.top = (rect[1] * 100) + '%';
      patch.style.width = ((rect[2] - rect[0]) * 100) + '%';
      patch.style.height = ((rect[3] - rect[1]) * 100) + '%';
      if(mark.kind==='box'){
        const remove=button('×',guarded(async event=>{event.stopPropagation();await removeMark(mark.id);}), 'box-remove');
        remove.title='删除此框选';remove.setAttribute('aria-label','删除第 '+mark.page+' 页框选');patch.append(remove);
      }
      node.marks.append(patch);
    }
  }
  renderDraftBox();
  updateCount();
}

function sortedMarks() {
  return [...state.marks].sort((left, right) => left.page - right.page || (left.created || 0) - (right.created || 0));
}

function renderMarkList() {
  const list = $('#marks-list');
  const live = new Set(state.marks.filter(mark=>mark.kind==='highlight'&&mark.quote).map(mark=>mark.id));
  for(const id of selectedHighlights)if(!live.has(id))selectedHighlights.delete(id);
  for(const id of selectedVisualBoxes)if(!state.marks.some(mark=>mark.id===id&&mark.kind==='box'))selectedVisualBoxes.delete(id);
  updateHighlightSelection();updateVisualSelection();
  list.textContent = '';
  if (!state.marks.length) {
    list.append(element('p', 'marks-empty', '还没有标记。选“高亮”后选中文字，或用“框选”“便签”在页面上添加。'));
    return;
  }
  for (const mark of sortedMarks()) {
    const row = element('article', 'mark-row');
    const header = element('header');
    const swatch = element('span', 'swatch color-' + mark.color);
    header.append(swatch, document.createTextNode('第 ' + mark.page + ' 页 · ' + (KIND_NAMES[mark.kind] || '标记') + ' · ' + (COLOR_NAMES[mark.color] || '')));
    if (mark.kind === 'highlight' && mark.quote) {
      const check = element('input'); check.type = 'checkbox'; check.checked = selectedHighlights.has(mark.id);
      check.setAttribute('aria-label', '选择第 '+mark.page+' 页高亮');
      check.onchange = () => { if(check.checked)selectedHighlights.add(mark.id);else selectedHighlights.delete(mark.id);updateHighlightSelection(); };
      header.prepend(check);
    }
    if(mark.kind==='box'){
      const check=element('input');check.type='checkbox';check.checked=selectedVisualBoxes.has(mark.id);check.setAttribute('aria-label','选择第 '+mark.page+' 页框选进行视觉识别');
      check.onchange=()=>{if(check.checked)selectedVisualBoxes.add(mark.id);else selectedVisualBoxes.delete(mark.id);updateVisualSelection();};header.prepend(check);
    }
    row.append(header);
    if (mark.quote) row.append(element('blockquote', '', mark.quote));
    const note = element('textarea');
    note.rows = 2;
    note.placeholder = '备注：这条标记说明了什么';
    note.value = mark.note || '';
    note.addEventListener('change', guarded(async () => {
      const result = await api('/api/annotations', {entry_id: entryId, op: 'update', item: {id: mark.id, note: note.value}});
      state.marks = result.items;
      renderMarks();
      renderMarkList();
      setStatus('备注已保存。');
    }));
    row.append(note);
    const actions = element('div', 'row-actions');
    actions.append(
      button('定位', () => locate(mark)),
      button('复制引文', guarded(() => copyText(mark.quote || mark.note || ''))),
      button('删除', guarded(() => removeMark(mark.id)), 'danger'),
    );
    if(mark.kind==='box')actions.append(button('视觉识别并制卡',guarded(()=>submitVisual([mark.id]))));
    row.append(actions);
    list.append(row);
  }
}

function locate(mark) {
  const node = state.pages.get(mark.page);
  if (!node) return;
  loadPage(mark.page);
  node.section.scrollIntoView({behavior: 'smooth', block: 'start'});
  const patches = node.marks.querySelectorAll('.mark[data-id="' + mark.id + '"]');
  for (const patch of patches) {
    patch.classList.remove('flash');
    void patch.offsetWidth;
    patch.classList.add('flash');
  }
}

async function saveMarks(promise) {
  const result = await promise;
  state.marks = result.items;
  renderMarks();
  renderMarkList();
}

async function createMark(kind, page, rects, quote, note, source = {}) {
  const safe = cleanRects(rects);
  if (!safe.length) throw new Error('没有可保存的标记区域，请重新框选。');
  const before = new Set(state.marks.map(mark => mark.id));
  await saveMarks(api('/api/annotations', {entry_id: entryId, op: 'create', item: {page, kind, color: state.color, rects: safe, quote, note, ...source}}));
  setStatus('已保存' + (KIND_NAMES[kind] || '标记') + '（共 ' + state.marks.length + ' 处）。');
  return state.marks.find(mark => !before.has(mark.id)) || null;
}

function cleanRects(rects) {
  const safe = [];
  for (const rect of rects || []) {
    if (!Array.isArray(rect) || rect.length !== 4) continue;
    const values = rect.map(Number);
    if (!values.every(Number.isFinite)) continue;
    safe.push(values);
  }
  return safe;
}

async function removeMark(id) {
  await saveMarks(api('/api/annotations', {entry_id: entryId, op: 'delete', item: {id}}));
  setStatus('标记已删除（剩余 ' + state.marks.length + ' 处）。');
}

async function copyText(text) {
  if (!text) return setStatus('这条标记没有可复制的文字。', true);
  try {
    await navigator.clipboard.writeText(text);
    setStatus('已复制到剪贴板。');
  } catch {
    const area = element('textarea');
    area.value = text;
    document.body.append(area);
    area.select();
    document.execCommand('copy');
    area.remove();
    setStatus('已复制到剪贴板。');
  }
}

function marksMarkdown() {
  const lines = ['# ' + (state.meta?.title || 'PDF 原文') + ' 标记', '', '文献标识：' + entryId, ''];
  for (const mark of sortedMarks()) {
    lines.push('## 第 ' + mark.page + ' 页 · ' + (KIND_NAMES[mark.kind] || '标记'), '');
    if (mark.quote) lines.push('> ' + mark.quote.split('\n').join('\n> '), '');
    if (mark.note) lines.push(mark.note, '');
  }
  return lines.join('\n');
}

/* ---------- pointer tools ---------- */

let drag = null, draftBox = null;

function updateBoxControls(){
  $('#box-actions').hidden=!(state.tool==='box'||drag||draftBox);
  $('#box-save').disabled=!draftBox||draftBox.saving;
  $('#box-cancel').disabled=!!draftBox?.saving;
}
function renderDraftBox(){
  for(const node of state.pages.values())for(const patch of node.marks.querySelectorAll('.box-draft'))patch.remove();
  if(!draftBox)return;
  const node=state.pages.get(draftBox.page);if(!node)return;
  const patch=element('div','drag-rect box-draft');const rect=draftBox.rect;
  patch.style.left=rect[0]*100+'%';patch.style.top=rect[1]*100+'%';patch.style.width=(rect[2]-rect[0])*100+'%';patch.style.height=(rect[3]-rect[1])*100+'%';
  node.marks.append(patch);
}
function selectTool(tool){
  state.tool=tool;
  for(const button of $$('[data-tool]'))button.classList.toggle('active',button.dataset.tool===tool);
  document.body.dataset.tool=tool;updateBoxControls();
}
function cancelBoxSelection(exitTool=true){
  if(draftBox?.saving)return false;
  drag?.band?.remove();drag=null;draftBox=null;renderDraftBox();
  window.getSelection()?.removeAllRanges();
  if(exitTool)selectTool('select');else updateBoxControls();
  return true;
}
$('#box-cancel').onclick=()=>{if(cancelBoxSelection())setStatus('框选已取消，已返回选择工具。');};
$('#box-save').onclick=guarded(async()=>{
  const draft=draftBox;if(!draft||draft.saving)return;
  draft.saving=true;updateBoxControls();
  try{await createMark('box',draft.page,[draft.rect],'','');draftBox=null;renderDraftBox();selectTool('select');}
  catch(error){draft.saving=false;renderDraftBox();updateBoxControls();throw error;}
});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&(drag||draftBox||state.tool==='box')){
    if(cancelBoxSelection()){event.preventDefault();setStatus('框选已取消，已返回选择工具。');}
  }
});
window.addEventListener('blur',()=>{if(drag)cancelBoxSelection();});

function pagePoint(section, clientX, clientY) {
  const box = section.getBoundingClientRect();
  return {x: clamp((clientX - box.left) / box.width, 0, 1), y: clamp((clientY - box.top) / box.height, 0, 1)};
}

function readSelection(section) {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
  const range = selection.getRangeAt(0);
  const box = section.getBoundingClientRect();
  const rects = [];
  for (const rect of range.getClientRects()) {
    if (rect.width < 2 || rect.height < 2) continue;
    const x0 = clamp((Math.max(rect.left, box.left) - box.left) / box.width, 0, 1);
    const x1 = clamp((Math.min(rect.right, box.right) - box.left) / box.width, 0, 1);
    const y0 = clamp((Math.max(rect.top, box.top) - box.top) / box.height, 0, 1);
    const y1 = clamp((Math.min(rect.bottom, box.bottom) - box.top) / box.height, 0, 1);
    if (x1 - x0 < 0.001 || y1 - y0 < 0.001) continue;
    rects.push([round(x0), round(y0), round(x1), round(y1)]);
  }
  if (!rects.length) return null;
  return {rects, quote: selection.toString().trim().slice(0, 4000)};
}

$('#pages').addEventListener('pointerdown', event => {
  if (event.button !== 0) return;
  if (event.target.closest('.mark.kind-note') || event.target.closest('.box-remove')) return;
  if(draftBox?.saving)return;
  const section = event.target.closest('.page');
  if (!section) return;
  if (state.tool === 'select') return;
  if (state.tool === 'note') {
    const page = Number(section.dataset.page);
    const rects = pointRect(pagePoint(section, event.clientX, event.clientY));
    const anchor = {x: event.clientX, y: event.clientY};
    createMark('note', page, rects, '', '').then(mark => {
      if (mark) openEditor({id: mark.id, quote: '', anchor});
    }).catch(error => setStatus(error.message, true));
    return;
  }
  if (state.tool === 'highlight' && event.target.closest('.text-layer span')) return;
  cancelBoxSelection(false);event.preventDefault();
  section.setPointerCapture?.(event.pointerId);
  drag = {pointerId:event.pointerId, section, page: Number(section.dataset.page), start: pagePoint(section, event.clientX, event.clientY), band: null, rect: null};
});

document.addEventListener('pointermove', event => {
  if (!drag || event.pointerId!==drag.pointerId) return;
  const current = pagePoint(drag.section, event.clientX, event.clientY);
  if (!drag.band) {
    if (Math.abs(current.x - drag.start.x) + Math.abs(current.y - drag.start.y) < 0.004) return;
    drag.band = element('div', 'drag-rect');
    drag.section.querySelector('.mark-layer').append(drag.band);
  }
  drag.rect = spanRect(drag.start, current);
  const rect = drag.rect;
  drag.band.style.left = (rect[0] * 100) + '%';
  drag.band.style.top = (rect[1] * 100) + '%';
  drag.band.style.width = ((rect[2] - rect[0]) * 100) + '%';
  drag.band.style.height = ((rect[3] - rect[1]) * 100) + '%';
});

document.addEventListener('pointerup', guarded(async event => {
  if(drag&&event.pointerId!==drag.pointerId)return;
  const finished = drag;
  drag = null;
  finished?.band?.remove();
  if (state.tool === 'highlight') {
    const payload = captureCardSelection();
    if (payload) {
      const parts = payload.segments.map(segment => ({segment, selection:readSelection(state.pages.get(segment.page).section)}));
      window.getSelection()?.removeAllRanges();
      for (const {segment,selection} of parts) if (selection) await createMark('highlight', segment.page, selection.rects, selection.quote, '', {source_sha256:payload.source_sha256,segments:[segment]});
      return;
    }
    const section = event.target.closest('.page') || finished?.section;
    const selected = section ? readSelection(section) : null;
    if (selected) {
      window.getSelection()?.removeAllRanges();
      return createMark('highlight', Number(section.dataset.page), selected.rects, selected.quote, '');
    }
  }
  if (!finished?.rect) return;
  const rect = finished.rect;
  if (rect[2] - rect[0] < 0.004 || rect[3] - rect[1] < 0.004) return;
  draftBox={page:finished.page,rect,saving:false};renderDraftBox();updateBoxControls();setStatus('框选尚未保存。点击“保存框选”，或按 Esc 取消。');
}));

document.addEventListener('pointercancel', event => {
  if(drag&&event.pointerId===drag.pointerId)cancelBoxSelection();
});
document.addEventListener('lostpointercapture', event => {
  if(drag&&event.pointerId===drag.pointerId)cancelBoxSelection();
});

$('#pages').addEventListener('click', event => {
  const pin = event.target.closest('.mark.kind-note');
  if (!pin) return;
  const mark = state.marks.find(item => item.id === pin.dataset.id);
  if (mark) openEditor({id: mark.id, quote: mark.quote, anchor: {x: event.clientX, y: event.clientY}});
});

function pointRect(point) {
  return [round(clamp(point.x - 0.006, 0, 1)), round(clamp(point.y - 0.006, 0, 1)),
    round(clamp(point.x + 0.006, 0, 1)), round(clamp(point.y + 0.006, 0, 1))];
}

function spanRect(start, end) {
  return [round(Math.min(start.x, end.x)), round(Math.min(start.y, end.y)),
    round(Math.max(start.x, end.x)), round(Math.max(start.y, end.y))];
}

/* ---------- editor ---------- */

function openEditor({id, quote, anchor}) {
  const existing = state.marks.find(item => item.id === id);
  if (!existing) return;
  state.editor = {id: existing.id, quote: existing.quote};
  $('#editor-title').textContent = KIND_NAMES[existing.kind] === '便签' ? '便签内容' : '标记备注';
  $('#editor-quote').textContent = quote || '';
  $('#editor-quote').classList.toggle('hidden', !quote);
  $('#editor-note').value = existing.note || '';
  const editor = $('#editor');
  editor.classList.remove('hidden');
  $('#editor-delete').classList.remove('hidden');
  const width = Math.min(340, window.innerWidth - 24);
  const left = clamp((anchor?.x || window.innerWidth / 2) - width / 2, 12, Math.max(12, window.innerWidth - width - 12));
  const top = clamp((anchor?.y || 120) + 16, 66, Math.max(66, window.innerHeight - 250));
  editor.style.left = left + 'px';
  editor.style.top = top + 'px';
  $('#editor-note').focus();
}

function closeEditor() {
  state.editor = null;
  $('#editor').classList.add('hidden');
}

$('#editor-cancel').onclick = closeEditor;
$('#editor-save').onclick = guarded(async () => {
  const editor = state.editor;
  if (!editor?.id) return closeEditor();
  const note = $('#editor-note').value.trim();
  await saveMarks(api('/api/annotations', {entry_id: entryId, op: 'update', item: {id: editor.id, note}}));
  closeEditor();
  setStatus(note ? '备注已保存。' : '备注已清空，标记保留。');
});
$('#editor-delete').onclick = guarded(async () => {
  const editor = state.editor;
  if (!editor?.id) return;
  await removeMark(editor.id);
  closeEditor();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && state.editor) closeEditor();
});

/* ---------- controls ---------- */

function setZoom(value) {
  state.zoom = clamp(value, 0.25, 4);
  localStorage.setItem('pdf-zoom', String(state.zoom));
  layout();
}

for (const tool of $$('[data-tool]')) {
  tool.classList.toggle('active', tool.dataset.tool === state.tool);
  tool.addEventListener('click', () => {
    if(!cancelBoxSelection(false))return;
    selectTool(tool.dataset.tool);
  });
}
document.body.dataset.tool = state.tool;

const colors = $('#colors');
for (const color of COLORS) {
  const swatch = element('button', state.color === color ? 'active' : '');
  swatch.type = 'button';
  swatch.dataset.color = color;
  swatch.title = COLOR_NAMES[color];
  swatch.setAttribute('aria-label', COLOR_NAMES[color]);
  swatch.addEventListener('click', () => {
    state.color = color;
    localStorage.setItem('pdf-color', color);
    for (const other of colors.children) other.classList.toggle('active', other.dataset.color === color);
  });
  colors.append(swatch);
}

$('#zoom-in').onclick = () => setZoom(state.zoom * 1.15);
$('#zoom-out').onclick = () => setZoom(state.zoom / 1.15);
$('#fit').onclick = () => setZoom(1);
$('#pages').addEventListener('wheel', event => {
  if (!event.ctrlKey) return;
  event.preventDefault();
  setZoom(state.zoom * (event.deltaY < 0 ? 1.1 : 1 / 1.1));
}, {passive: false});

function toggleMarksPanel(force) {
  const open = document.body.classList.toggle('marks-open', force);
  localStorage.setItem('pdf-marks-open', open ? '1' : '0');
  layout();
}
$('#marks-toggle').onclick = () => toggleMarksPanel();
$('#marks-close').onclick = () => toggleMarksPanel(false);
$('#marks-copy').onclick = guarded(() => copyText(marksMarkdown()));
$('#marks-export').onclick = guarded(() => {
  if (!state.marks.length) return setStatus('还没有标记可导出。', true);
  const blob = new Blob([marksMarkdown()], {type: 'text/markdown;charset=utf-8'});
  const link = element('a');
  link.href = URL.createObjectURL(blob);
  link.download = (state.meta?.title || 'PDF原文').replace(/[\\/:*?"<>|]/g, '_').slice(0, 60) + '-标记.md';
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 4000);
  setStatus('已导出标记 Markdown。');
});

let resizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => layout(), 180);
});

/* ---------- boot ---------- */

function fatal(message) {
  $('#loading').classList.add('hidden');
  $('#fatal-message').textContent = message;
  $('#fatal').classList.remove('hidden');
}

async function boot() {
  if (!entryId) throw new Error('缺少文献标识或访问标识，请从文献研究工作台重新点击“查看原文”。');
  const meta = await api('/api/pdf/meta?' + new URLSearchParams({entry_id: entryId}));
  if (!meta.pages?.length) throw new Error('这份 PDF 没有可显示的页面。');
  state.meta = meta;
  document.title = (meta.title || 'PDF 原文') + ' · PDF 原文';
  $('#doc-title').textContent = meta.title || 'PDF 原文';
  $('#doc-meta').textContent = meta.page_count + ' 页 · ' + (meta.source_name || 'PDF');
  $('#raw-file').href = endpoint('/api/pdf/raw?' + new URLSearchParams({entry_id:entryId,token}));
  buildPages();
  layout();
  observePages();
  for (const number of [1, 2]) loadPage(number);
  const saved = await api('/api/annotations?' + new URLSearchParams({entry_id: entryId}));
  state.marks = saved.items || [];
  renderMarks();
  renderMarkList();
  await refreshCards();
  $('#loading').classList.add('hidden');
  if (window.localStorage.getItem('pdf-marks-open') === null) toggleMarksPanel(window.innerWidth >= 1000);
  setStatus('已载入 PDF 原文。选“高亮”“框选”或“便签”即可做标记。');
}

/* PDF card selection uses word/character positions; the server reconstructs quotes. */
let selectionTimer, pendingSelection, lastSelection = '', pointerSelecting = false, cardsSignature = '';
const feedback = message => { $('#card-feedback').textContent = message; };

function captureCardSelection() {
  const selection = window.getSelection();
  if (!selection?.rangeCount || selection.isCollapsed) return null;
  const range = selection.getRangeAt(0);
  const parent = node => node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
  if (!parent(range.startContainer)?.closest('.text-layer') || !parent(range.endContainer)?.closest('.text-layer')) return null;
  const segments = [];
  for (const [page, node] of state.pages) {
    const selected = [...node.text.children].filter(span => range.intersectsNode(span));
    if (!selected.length) continue;
    const first = selected[0], last = selected.at(-1);
    const start = range.startContainer === first.firstChild ? range.startOffset : 0;
    const end = range.endContainer === last.firstChild ? range.endOffset : last.textContent.length;
    // Browser offsets count UTF-16 units; Python stores Unicode character indexes.
    segments.push({page, start_word:Number(first.dataset.word), end_word:Number(last.dataset.word),
      start_offset:[...first.textContent.slice(0, start)].length, end_offset:[...last.textContent.slice(0, end)].length});
  }
  return segments.length ? {entry_id:entryId,source_sha256:state.meta.source_sha256,segments} : null;
}

async function submitCardSelection(payload) {
  pendingSelection = payload;
  $('#retry-selection').hidden = true;
  feedback('选段已提交，等待桌面模型生成；可在下方取消。');
  try {
    const result = await api('/api/cards', payload);
    lastSelection = JSON.stringify(payload);
    feedback(result.duplicate ? '该选段已有卡片或任务，已显示原记录。' : '任务已保存，完成后卡片会出现在下方。');
    toggleMarksPanel(true);
    await refreshCards();
  } catch (error) {
    feedback('选段提交失败：' + error.message);
    $('#retry-selection').hidden = false;
  }
}

function scheduleCardSelection() {
  clearTimeout(selectionTimer);
  if (pointerSelecting || state.tool !== 'select' || !$('#auto-card').checked || !state.meta) return;
  const payload = captureCardSelection();
  if (!payload || JSON.stringify(payload) === lastSelection) return;
  feedback('选段稳定 1 秒后自动生成。按 Esc 可取消本次提交。');
  selectionTimer = setTimeout(() => submitCardSelection(payload), 1000);
}
document.addEventListener('selectionchange', scheduleCardSelection);
$('#pages').addEventListener('pointerdown', () => { pointerSelecting = true; clearTimeout(selectionTimer); });
document.addEventListener('pointerup', () => { pointerSelecting = false; scheduleCardSelection(); });
document.addEventListener('pointercancel', () => { pointerSelecting = false; clearTimeout(selectionTimer); });
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') { clearTimeout(selectionTimer); feedback('本次待提交选段已取消。'); }
});
$('#auto-card').onchange = () => { clearTimeout(selectionTimer); feedback($('#auto-card').checked ? '自动制卡已开启。' : '自动制卡已关闭。'); };
$('#retry-selection').onclick = () => pendingSelection && submitCardSelection(pendingSelection);
window.addEventListener('pagehide', () => clearTimeout(selectionTimer));

function downloadMarkdown(card) {
  const link = element('a');
  link.href = URL.createObjectURL(new Blob([card.markdown], {type:'text/markdown;charset=utf-8'}));
  link.download = card.title.replace(/[\\/:*?"<>|]/g, '_').slice(0, 60) + '.md';
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 4000);
}

function locateCard(card) {
  if (!card.source_current) return feedback('PDF 来源已变化，已保留原卡片；请使用相同哈希的原文件核对位置。');
  for (const node of state.pages.values()) for (const patch of node.marks.querySelectorAll('.card-location')) patch.remove();
  for (const segment of card.segments) {
    const node = state.pages.get(segment.page);
    loadPage(segment.page);
    for (const rect of segment.rects) {
      const patch = element('div', 'card-location');
      patch.style.left = rect[0]*100+'%'; patch.style.top = rect[1]*100+'%';
      patch.style.width = (rect[2]-rect[0])*100+'%'; patch.style.height = (rect[3]-rect[1])*100+'%';
      if(mark.kind==='box'){
        const remove=button('×',guarded(async event=>{event.stopPropagation();await removeMark(mark.id);}), 'box-remove');
        remove.title='删除此框选';remove.setAttribute('aria-label','删除第 '+mark.page+' 页框选');patch.append(remove);
      }
      node.marks.append(patch);
    }
  }
  state.pages.get(card.segments[0].page).section.scrollIntoView({behavior:'smooth',block:'start'});
}

function cardURL(card, accessToken = token) {
  return endpoint('/card')+'#'+new URLSearchParams({entry_id:entryId,card_id:card.id,token:accessToken});
}
let cardWindowDirty=false;
window.addEventListener('message',event=>{
  if(event.origin!==location.origin||event.source!==$('#card-frame').contentWindow||event.data?.type!=='card-editor-dirty')return;
  cardWindowDirty=event.data.dirty===true;
});
function previewCard(card) {
  cardWindowDirty=false;
  $('#card-frame').src=cardURL(card);
  $('#card-browser-link').hidden=true;
  $('#card-window-status').textContent='';
  $('#card-window').showModal();
  $('#card-browser').onclick=async()=>{
    if(cardWindowDirty){$('#card-window-status').textContent='请先保存修改，再在独立窗口打开。';return;}
    try{
    let accessToken=token;
    if(!accessToken){const session=await api('/api/pdf/session',{entry_id:entryId});accessToken=new URLSearchParams(new URL(session.url).hash.slice(1)).get('token');}
    const link=$('#card-browser-link');link.href=cardURL(card,accessToken);link.hidden=false;
    window.open(link.href,'_blank');
    $('#card-window-status').textContent='若新窗口没有出现，请点击“打开卡片窗口”链接。';
    }catch(error){$('#card-window-status').textContent='打开独立窗口失败：'+error.message;}
  };
}
function closeCardWindow(){
  if(cardWindowDirty&&!confirm('卡片有未保存的修改，仍要关闭吗？'))return;
  $('#card-window').close();$('#card-frame').removeAttribute('src');cardWindowDirty=false;refreshCards(true).catch(error=>feedback(error.message));
}
$('#card-window-close').onclick=closeCardWindow;
$('#card-window').addEventListener('cancel',event=>{event.preventDefault();closeCardWindow();});

async function refreshCards(force = false) {
  const value = await api('/api/cards?' + new URLSearchParams({entry_id:entryId}));
  await refreshVisualResults();
  const signature = JSON.stringify(value);
  if (!force && cardsSignature === signature) return;
  cardsSignature = signature;
  const list = $('#cards-list');
  list.textContent = '';
  for (const task of value.tasks.filter(task => task.status !== 'completed')) {
    const row = element('article', 'card-row');
    const names = {queued:'排队中',running:'生成中',failed:'生成失败',cancelled:'已取消',interrupted:'已中断'};
    row.append(element('strong', '', names[task.status] || task.status), element('blockquote', '', task.selected_text.slice(0, 180)));
    if (task.error) row.append(element('p', '', task.error));
    const op = ['queued','running'].includes(task.status) ? 'cancel' : 'retry';
    row.append(button(op === 'cancel' ? '取消生成' : '重试生成', guarded(async () => {
      await api('/api/cards/action', {entry_id:entryId,id:task.id,op}); await refreshCards();
    })));
    list.append(row);
  }
  for (const card of value.items) {
    const row = element('article', 'card-row');
    row.append(element('h3', '', card.title), element('p', '', card.summary), element('p', '', card.tags.join(' · ')),element('p','',card.generation_mode==='combined'?'合并卡片 · '+(card.regions?.length||card.selection_parts?.length||1)+' 个选段':'独立选段卡片'),
      element('p', '', '物理页 ' + [...new Set(card.segments.map(s=>s.page))].join(', ') + (card.source_current ? '' : ' · PDF 来源已变化')),
      element('blockquote', '', card.selected_text), element('p','card-citation',card.paper_citation||card.paper_title));
    const details = element('details'), summary = element('summary', '', '正文与上下文');
    details.append(summary, element('pre', '', card.body_markdown + '\n\n上文：\n' + card.context_before + '\n\n下文：\n' + card.context_after));
    if(card.note_file)row.append(element('p','card-citation',card.note_file.error?'笔记同步失败：'+card.note_file.error:'笔记：'+card.note_file.path));
    row.append(details, button('回溯原文', () => locateCard(card)), button('预览卡片', () => previewCard(card)), button('导出 Markdown / Obsidian', () => downloadMarkdown(card)));
    list.append(row);
  }
  if (!value.items.length && !value.tasks.length) list.append(element('p', '', '还没有卡片。使用“选择”工具拖选原文即可自动生成。'));
}
let cardPolling = false;
const cardTimer = setInterval(async () => {
  if (!state.meta || cardPolling || document.hidden) return;
  cardPolling = true;
  try { await refreshCards(); } catch (error) { feedback('卡片连接失败：' + error.message + '。若桌面已重启或资料目录已切换，请重新打开原文。'); }
  finally { cardPolling = false; }
}, 3000);
window.addEventListener('pagehide', () => clearInterval(cardTimer));

boot().catch(error => fatal(error.message));
