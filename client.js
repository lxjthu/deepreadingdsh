// Shared React identity and locale translation come from the host loader.
window.__ModuleLoader__.load({
  id: 'dsh-deep-reading',
  factory(require) {
    const React = require('react'), h = React.createElement;
    const zh = { title:'文献研究', refresh:'刷新工作台', settings:'资料目录', current:'实际资料目录', choose:'选择文件夹', path:'完整路径', save:'保存并启用', cancel:'取消', retry:'重试连接', hint:'切换只启用所选目录，不搬迁、合并或删除原资料。空目录将初始化为新的空库。运行或排队任务结束后才能切换。', saved:'已保存并生效', saving:'正在验证并切换…', ready:'就绪', starting:'启动中', switching:'切换中', stopped:'已停止', stopping:'正在停止', failed:'连接失败', model:'后续模型请求使用宿主当前默认模型；已完成步骤保留。', error:'操作失败：{message}' };
    const en = { title:'Literature research', refresh:'Refresh workbench', settings:'Data directory', current:'Effective directory', choose:'Choose folder', path:'Full path', save:'Save and activate', cancel:'Cancel', retry:'Retry connection', hint:'Switching uses the chosen directory without moving, merging or deleting existing data. An empty folder creates a new library. Finish queued or running tasks first.', saved:'Saved and active', saving:'Validating and switching…', ready:'Ready', starting:'Starting', switching:'Switching', stopped:'Stopped', stopping:'Stopping', failed:'Connection failed', model:'Later model requests use the current host default model. Completed steps are retained.', error:'Operation failed: {message}' };
    zh.configured = '保留的资料目录（后台未就绪）';
    en.configured = 'Saved directory (backend not ready)';
    async function api(path, body) {
      const response = await fetch('/deep-reading/control/' + path, { credentials:'same-origin', method:body === undefined ? 'GET' : 'POST', headers:{'Content-Type':'application/json'}, body:body === undefined ? undefined : JSON.stringify(body) });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || String(response.status));
      return value;
    }
    function ReadingIcon() {
      return h('svg', {width:18,height:18,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','aria-hidden':true},h('path',{d:'M3 4.5c3-1 6-.5 9 1.5 3-2 6-2.5 9-1.5V20c-3-1-6-.5-9 1-3-1.5-6-2-9-1V4.5Z M12 6v15'}));
    }
    function ReadingPanel({ t }) {
      const [status,setStatus] = React.useState(null), [open,setOpen] = React.useState(false), [path,setPath] = React.useState(''), [message,setMessage] = React.useState(''), [busy,setBusy] = React.useState(false), [generation,setGeneration] = React.useState(0);
      const frame = React.useRef(null);
      React.useEffect(() => {
        let disposed = false;
        const update = async () => { try { const value = await api('status'); if (!disposed) setStatus(value); } catch (error) { if (!disposed) setMessage(t('error',{message:error.message})); } };
        update(); const timer = setInterval(update,2000);
        return () => { disposed = true; clearInterval(timer); };
      },[t]);
      const perform = fn => async () => { setBusy(true); setMessage(''); try { await fn(); } catch (error) { setMessage(t('error',{message:error.message})); } finally { setBusy(false); const value = await api('status').catch(()=>null); if(value)setStatus(value); } };
      const button = (key, onClick) => h('button',{type:'button',onClick,disabled:busy,style:{font:'inherit',padding:'6px 12px',cursor:'pointer'}},t(key));
      const save = perform(async () => { setMessage(t('saving')); await api('save',{path}); setStatus(await api('status')); localStorage.removeItem('reading-topic'); setGeneration(v=>v+1); setMessage(t('saved')); });
      return h('section',{'data-deep-reading-panel':true,style:{display:'flex',flexDirection:'column',height:'100%',minHeight:0,minWidth:0}},
        h('div',{style:{display:'flex',gap:12,alignItems:'center',flexWrap:'wrap',padding:'10px 20px',borderBottom:'1px solid var(--dsw-alias-border-l3)'}},
          h('strong',null,t('title')), h('span',{role:'status'},status ? t(status.status) : t('starting')),
          button('settings',()=>{setPath(status?.home||'');setOpen(true);setMessage('');}),
          button('refresh',()=>frame.current?.contentWindow?.location.reload()),
          button('retry',perform(async()=>{await api('retry',{});setGeneration(v=>v+1);}))),
        (open || status?.status==='failed' || status?.error) && h('div',{style:{padding:20,borderBottom:'1px solid var(--dsw-alias-border-l3)',overflow:'auto'}},
          h('p',null,t(status?.activeHome===null?'configured':'current')+': '+(status?.home||'')), h('p',null,t('hint')),h('p',null,t('model')),
          open && h('label',null,t('path'),h('input',{value:path,onChange:e=>setPath(e.target.value),disabled:busy,style:{display:'block',width:'100%',boxSizing:'border-box',font:'inherit',padding:8},'aria-label':t('path')})),
          open && h('div',{style:{display:'flex',gap:10,marginTop:12}},button('choose',perform(async()=>{const value=await api('pick',{});if(value.path)setPath(value.path);})),button('save',save),button('cancel',()=>{setOpen(false);setMessage('');})),
          h('p',{role:'alert'},message || status?.error || '')),
        h('iframe',{key:generation,ref:frame,title:t('title'),src:'/deep-reading/',style:{width:'100%',flex:1,minHeight:0,border:0}}));
    }
    return { name:'deep-reading-client', inject:['slots','locale'], apply(ctx) {
      ctx.effect(()=>ctx.locale.register('deep-reading',{zh,en}));
      const t = ctx.locale.bind('deep-reading');
      ctx.slots.inject('main',()=>ctx.slots.register({name:'main',key:'deep-reading',locale:'deep-reading'},ReadingPanel));
      ctx.slots.inject('sidebar.panellist',()=>ctx.slots.register({name:'sidebar.panellist',id:'deep-reading',order:20,label:()=>t('title')},ReadingIcon));
    } };
  },
});
