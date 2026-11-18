// The dsh client loader supplies the shared React identity and slot registry.
window.__ModuleLoader__.load({
  id: 'dsh-deep-reading',
  factory(require) {
    const React = require('react');
    const h = React.createElement;
    function ReadingIcon() {
      return h('svg', { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, 'aria-hidden': true },
        h('path', { d: 'M3 4.5c3-1 6-.5 9 1.5 3-2 6-2.5 9-1.5V20c-3-1-6-.5-9 1-3-1.5-6-2-9-1V4.5Z' }),
        h('path', { d: 'M12 6v15M6 9h3M6 12h3M15 9h3M15 12h3' }));
    }
    function ReadingPanel() {
      const frame = React.useRef(null);
      return h('section', { 'data-deep-reading-panel': true, style: { display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, minWidth: 0 } },
        h('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 20px', borderBottom: '1px solid var(--dsw-alias-border-l3)', flexShrink: 0 } },
          h('strong', { style: { fontSize: 14 } }, '文献研究'),
          h('button', { type: 'button', onClick: () => frame.current?.contentWindow?.location.reload(), style: { font: 'inherit', fontSize: 12, cursor: 'pointer', border: 0, background: 'transparent', color: 'inherit', padding: '6px 10px' } }, '刷新工作台')),
        h('iframe', { ref: frame, title: '文献研究工作台', src: '/deep-reading/', style: { width: '100%', flex: 1, minHeight: 0, border: 0, background: '#f7f9f5' } }));
    }
    return {
      name: 'deep-reading-client',
      inject: ['slots'],
      apply(ctx) {
        ctx.slots.inject('main', () => ctx.slots.register({ name: 'main', key: 'deep-reading' }, ReadingPanel));
        ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({ name: 'sidebar.panellist', id: 'deep-reading', order: 20, label: '文献研究' }, ReadingIcon));
      },
    };
  },
});
