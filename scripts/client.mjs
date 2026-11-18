import { readFileSync } from 'node:fs';
const args = process.argv.slice(2);
const index = args.indexOf('--connection');
if (index < 0) throw new Error('--connection required');
const config = JSON.parse(readFileSync(args[index + 1], 'utf8'));
args.splice(index, 2);
if (args[0] === 'open') console.log(config.url + '/#' + config.token);
else {
  const method = args[0] === 'request' ? args[1] : 'GET';
  const path = args[0] === 'request' ? args[2] : '/api/state';
  if (!path?.startsWith('/api/')) throw new Error('Only /api/ paths accepted');
  const r = await fetch(config.url + path, { method, headers: { 'X-Reading-Token': config.token, 'Content-Type': 'application/json' }, body: method === 'GET' ? undefined : args[3] || '{}' });
  console.log(await r.text());
  if (!r.ok) process.exitCode = 1;
}
