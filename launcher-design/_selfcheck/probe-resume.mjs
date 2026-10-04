// 断点续训遮挡探测：config 页点击 #cfgResume 前后对比 + 遮挡判定
import { createRequire } from 'module';
const require = createRequire('C:/Users/Tianbuyu/AppData/Local/hermes/skills/creative/ui-craft-studio/package.json');
const { chromium } = require('playwright');
const URL = 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/launcher-design/AYT-Launcher-v4.html?page=config#';
const OUT = 'E:/项目/Auto-yolo-training/launcher-design/_selfcheck/';
const [VW, VH] = (process.env.VIEW || '1560x940').split('x').map(Number);

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const ctx = await browser.newContext({ viewport: { width: VW, height: VH }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.goto(URL, { waitUntil: 'domcontentloaded' });
await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
await page.waitForTimeout(600);

await (await page.$('#stageInner')).screenshot({ path: OUT + 'probe-resume-before.png' });

// 点击「断点续训」
await page.click('#cfgResume'); await page.waitForTimeout(500);
await (await page.$('#stageInner')).screenshot({ path: OUT + 'probe-resume-after.png' });

const r = await page.evaluate(() => {
  const box = document.getElementById('cfgResumeBox');
  const exec = document.getElementById('cfgExec');
  const sc = document.querySelector('#page-config .pscroll');
  if (!box) return { err: 'no box' };
  const br = box.getBoundingClientRect();
  const er = exec.getBoundingClientRect();
  const sr = sc.getBoundingClientRect();
  // 中心点命中测试：被谁盖住
  const cx = br.left + br.width / 2, cy = br.top + br.height / 2;
  const topEl = document.elementFromPoint(cx, cy);
  const topDesc = topEl ? topEl.tagName + '.' + String(topEl.className).split(' ').slice(0, 2).join('.') : null;
  const boxVisible = br.width > 0 && br.height > 0 && !box.hidden;
  // 是否与吸底卡相交
  const ix = Math.min(br.right, er.right) - Math.max(br.left, er.left);
  const iy = Math.min(br.bottom, er.bottom) - Math.max(br.top, er.top);
  return {
    boxVisible, boxRect: [Math.round(br.left), Math.round(br.top), Math.round(br.width), Math.round(br.height)],
    execRect: [Math.round(er.left), Math.round(er.top), Math.round(er.width), Math.round(er.height)],
    scrollRect: [Math.round(sr.left), Math.round(sr.top), Math.round(sr.width), Math.round(sr.height)],
    intersectExec: ix > 0 && iy > 0 ? Math.round(ix * iy) : 0,
    topElAtCenter: topDesc, centerInsideBox: box.contains(topEl),
    boxBelowExecTop: br.bottom > er.top,
    scrollTop: sc.scrollTop, scrollMax: sc.scrollHeight - sc.clientHeight,
    overflowBottom: Math.round(br.bottom - sr.bottom)
  };
});
console.log(JSON.stringify(r, null, 1));
await browser.close();
