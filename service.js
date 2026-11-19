/** Own one Python process and its model bridge until both have settled. */
import { spawn, execFile } from 'node:child_process';
import { readFileSync, writeFileSync, renameSync, existsSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { randomBytes } from 'node:crypto';
import { requestOptions, generate, admitVisionRequest } from './bridge.js';

/** Start, stop and inspect a single backend; callers serialize replacements. */
export class ReadingService {
  constructor({ root, home, settings, llm, attachments, messages, selection, log, spawnProcess = spawn }) {
    Object.assign(this, { root, home, settings, llm, attachments, messages, selection, log, spawnProcess });
    this.token = randomBytes(32).toString('hex');
    this.lifetime = new AbortController();
    this.status = 'starting';
    this.error = null;
  }
  async call(path, body, signal = this.lifetime.signal, timeoutMs=15000) {
    const response = await fetch(this.base + path, { method: body === undefined ? 'GET' : 'POST', headers: { 'X-Reading-Token': this.token, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)]) });
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || `Reading service ${response.status}`);
    return value;
  }
  async start() {
    const child = this.child = this.spawnProcess(this.settings.python || process.env.DSH_READING_PYTHON || 'python', [join(this.root, 'scripts/server.py'), '--home', this.home, '--token', this.token], {
      cwd: this.root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', PYTHONDONTWRITEBYTECODE: '1', DSH_READING_MACHINE_SETTINGS: JSON.stringify(Object.fromEntries(['python', 'ocrRoot', 'ocrPython'].filter(key => this.settings[key] !== undefined).map(key => [key, this.settings[key]]))) },
    });
    let ready, rejectReady, buffer = '', stderr = '';
    const readiness = new Promise((resolve, reject) => { ready = resolve; rejectReady = reject; });
    this.closed = new Promise(resolve => {
      child.once('close', code => {
        this.base = undefined;
        this.lifetime.abort();
        if (this.status !== 'stopping') { this.status = 'failed'; this.error = stderr.trim() || `后台已退出 (${code})，请重试连接`; }
        this.removeDescriptor();
        rejectReady(new Error(this.error || '后台在就绪前退出'));
        resolve();
      });
      child.once('error', error => { this.error = error.message; rejectReady(error); });
    });
    child.stderr.on('data', data => { stderr = (stderr + data.toString('utf8')).slice(-6000); });
    child.stdout.on('data', data => {
      buffer += data.toString('utf8');
      let end;
      while ((end = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, end); buffer = buffer.slice(end + 1);
        let event; try { event = JSON.parse(line); } catch { continue; }
        if (event.event !== 'ready' || this.lifetime.signal.aborted || this.status !== 'starting') continue;
        this.base = event.url;
        ready();
      }
    });
    const timeout = setTimeout(() => rejectReady(new Error('后台启动超时，请检查 Python 环境或目录占用')), this.settings.startTimeoutMs || 30000);
    const abort = () => rejectReady(new Error('后台启动已取消'));
    this.lifetime.signal.addEventListener('abort', abort, { once: true });
    try {
      await readiness;
      await this.call('/api/state');
      if (this.lifetime.signal.aborted) throw new Error('后台启动已取消');
      this.status = 'ready';
      const descriptor = join(this.home, 'connection.json');
      writeFileSync(descriptor, JSON.stringify({ url: this.base, token: this.token, pid: child.pid, model: this.selection().provider + '/' + this.selection().model }), { mode: 0o600 });
      this.bridge = this.poll();
      return this;
    } catch (error) {
      this.error = error.message;
      await this.stop();
      this.status = 'failed';
      throw error;
    } finally { clearTimeout(timeout); this.lifetime.signal.removeEventListener('abort', abort); }
  }
  async pause(ms, signal) {
    if (signal.aborted) return;
    await new Promise(resolve => {
      const done = () => { clearTimeout(timer); signal.removeEventListener('abort', done); resolve(); };
      const timer = setTimeout(done, ms);
      signal.addEventListener('abort', done, { once: true });
    });
  }
  async poll() {
    while (!this.lifetime.signal.aborted) {
      try {
        const { request } = await this.call('/bridge/next');
        if (request) await this.fulfill(request);
      } catch (error) { if (!this.lifetime.signal.aborted) this.log.warn('文献模型桥接：' + error.message); }
      await this.pause(500, this.lifetime.signal);
    }
  }
  async fulfill(request) {
    const active = new AbortController();
    const signal = AbortSignal.any([active.signal, this.lifetime.signal, AbortSignal.timeout(this.settings.modelTimeoutMs || 600000)]);
    const monitor = (async () => {
      while (!active.signal.aborted && !this.lifetime.signal.aborted) {
        await this.pause(300, AbortSignal.any([active.signal, this.lifetime.signal]));
        if (active.signal.aborted || this.lifetime.signal.aborted) break;
        try { if ((await this.call('/bridge/status?id=' + request.id, undefined, signal)).cancelled) active.abort(); }
        catch (error) { active.abort(error); }
      }
    })();
    let answer;
    try {
      const selected=this.selection();
      const admitted=await admitVisionRequest(request,this.llm,this.attachments,selected,signal);
      answer = await generate(this.llm, requestOptions(admitted, this.messages, selected, signal));
    }
    catch (error) { answer = { error: error.message, code: error.code || 'MODEL_ERROR' }; }
    finally { active.abort(); await monitor; }
    if (!this.lifetime.signal.aborted) await this.call('/bridge/respond', { id: request.id, lease: request.lease, ...answer });
  }
  removeDescriptor() {
    const path = join(this.home, 'connection.json');
    try { if (existsSync(path) && JSON.parse(readFileSync(path, 'utf8')).token === this.token) unlinkSync(path); }
    catch (error) { this.log.warn('连接描述清理失败：' + error.message); }
  }
  async stop() {
    if (this.stopping) return this.stopping;
    this.stopping = this.shutdown();
    return this.stopping;
  }
  async shutdown() {
    this.status = 'stopping';
    this.lifetime.abort();
    const child = this.child;
    if (!child) { this.status = 'stopped'; return; }
    try {
      if (this.base) await this.call('/bridge/shutdown', {}, AbortSignal.timeout(3000));
    } catch (error) { this.log.warn('后台正常关闭未确认：' + error.message); }
    let forced, rejectTermination;
    const terminationFailure = new Promise((resolve, reject) => { rejectTermination = reject; });
    const kill = setTimeout(() => {
      if (child.exitCode !== null || child.signalCode !== null) return;
      if (process.platform === 'win32') {
        forced = new Promise((resolve, reject) => execFile('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true }, error => {
          if (error && child.exitCode === null && child.signalCode === null) reject(error); else resolve();
        }));
        forced.catch(rejectTermination);
      } else child.kill('SIGKILL');
    }, this.settings.shutdownTimeoutMs || 5000);
    try {
      await Promise.race([Promise.all([this.closed, this.bridge]), terminationFailure]);
      await forced;
      this.base = undefined;
      this.removeDescriptor();
      this.status = 'stopped';
    } catch (error) {
      this.base = undefined;
      this.status = 'failed';
      this.error = '未能确认后台退出，请检查本实例进程后重试：' + error.message;
      throw new Error(this.error, { cause: error });
    } finally { clearTimeout(kill); }
  }
}

/** Replace a machine settings file atomically; no credentials are stored here. */
export function saveSettings(path, settings) {
  const temp = path + '.' + randomBytes(6).toString('hex') + '.tmp';
  try { writeFileSync(temp, JSON.stringify(settings, null, 2) + '\n'); renameSync(temp, path); }
  finally { if (existsSync(temp)) unlinkSync(temp); }
}
