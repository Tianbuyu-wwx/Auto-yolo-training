// live.js 加载诊断
import { createRequire } from 'module';
const require = createRequire('C:/Users/Tianbuyu/AppData/Local/hermes/skills/creative/ui-craft-studio/package.json');
const { chromium } = require('playwright');
import { spawn } from 'child_process';
import { setTimeout as sleep } from 'timers/promises';

const REPO = 'E:/项目/Auto-yolo-training';
const BOOT = [
  'import sys; sys.path.insert(0, ".")',
  'from src.launcher.backend import LauncherBackend',
  'b = LauncherBackend(base_dir=".")',
  'b.start()',
  'print("BACKEND_URL=" + b.url, flush=True)',
  'import time',
  'while True: time.sleep(3600)',
].join('\n');
const srv = spawn('C:/Python312/python.exe', ['-c', BOOT], { cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'] });
let buf = '', url = null;
srv.stdout.on('data', d => { buf += String(d); const m = /BACKEND_URL=(http:\/\/\S+)/.exec(buf); if (m && !url) url = m[1]; });
srv.stderr.on('data', d => { buf += String(d); });
for (let i = 0; i < 100 && !url; i++) await sleep(500);
console.log('backend:', url);

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 860 } });
page.on('response', r => { const u = r.url(); if (/live\.js|index\.html|\/api\/health|\/$/.test(u) || r.status() >= 400) console.log('RESP', r.status(), u.slice(0, 120)); });
page.on('console', m => console.log('[c.' + m.type() + ']', m.text().slice(0, 240)));
page.on('pageerror', e => console.log('[pageerror]', String(e).slice(0, 420)));
await page.goto(url, { waitUntil: 'domcontentloaded' }).catch(e => console.log('goto err', e.message));
await page.waitForTimeout(3500);
console.log('scripts:', await page.evaluate(() => [...document.scripts].map(s => s.src || '(inline)').join(' | ')));
console.log('typeof __live:', await page.evaluate(() => typeof window.__live));
console.log('healthFetch:', await page.evaluate(async () => { try { const r = await fetch('/api/health'); return r.status + ' ' + (await r.text()).slice(0, 90); } catch (e) { return 'ERR ' + e.message; } }));
await browser.close();
srv.kill();
