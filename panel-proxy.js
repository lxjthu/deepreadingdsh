import { request as httpRequest } from 'node:http';

/** Same-origin panel transport, admitted by dsh's own browser connection fence. */
export function panelProxy({ connection, backend, token, control }) {
  return async (req, res) => {
    const admission = connection.admit(req);
    if ('rejection' in admission) { res.writeHead(admission.rejection); res.end('Unauthorized'); return; }
    const url = new URL(req.url, 'http://localhost');
    const path = url.pathname.slice('/deep-reading'.length) || '/';
    if (path.startsWith('/control/') && control) {
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.setHeader('Cache-Control', 'no-store');
      try {
        if ((path === '/control/status' ? 'GET' : 'POST') !== req.method) { res.writeHead(405); res.end('{}'); return; }
        let body = {};
        if (req.method === 'POST') {
          if (!req.headers['content-type']?.startsWith('application/json')) throw new Error('JSON required');
          let raw = '';
          for await (const chunk of req) { raw += chunk; if (Buffer.byteLength(raw) > 16384) throw new Error('Request too large'); }
          body = JSON.parse(raw);
        }
        res.end(JSON.stringify(await control(path, body)));
      } catch (error) { res.writeHead(400); res.end(JSON.stringify({ error: error.message })); }
      return;
    }
    if (!['GET', 'POST'].includes(req.method) || !(['/', '/app.js', '/wiki.js', '/style.css'].includes(path) || path.startsWith('/api/'))) {
      res.writeHead(404); res.end('Not found'); return;
    }
    const target = backend();
    const base = typeof target === 'string' ? target : target?.base;
    if (!base) { res.writeHead(503, { 'Content-Type': 'text/plain; charset=utf-8', 'Retry-After': '2' }); res.end('文献工作台正在启动，请稍后刷新。'); return; }
    const headers = { 'X-Reading-Token': typeof target === 'string' ? token : target.token };
    for (const key of ['content-type', 'content-length', 'range']) if (req.headers[key]) headers[key] = req.headers[key];
    // Browser cookies and dsh authentication never enter the Python service.
    const upstream = httpRequest(new URL(path + url.search, base), { method: req.method, headers }, incoming => {
      const safeHeaders = {};
      for (const key of ['content-type', 'content-length', 'cache-control', 'content-range', 'accept-ranges', 'x-content-type-options', 'content-security-policy', 'referrer-policy']) {
        if (incoming.headers[key]) safeHeaders[key] = incoming.headers[key];
      }
      res.writeHead(incoming.statusCode || 502, safeHeaders);
      incoming.pipe(res);
      incoming.on('error', () => res.destroy());
    });
    upstream.on('error', () => { if (!res.headersSent) { res.writeHead(502, { 'Content-Type': 'text/plain; charset=utf-8' }); res.end('文献后台暂不可用，请刷新或检查 dsh 插件状态。'); } else res.destroy(); });
    req.on('aborted', () => upstream.destroy());
    res.on('close', () => upstream.destroy());
    req.pipe(upstream);
  };
}
