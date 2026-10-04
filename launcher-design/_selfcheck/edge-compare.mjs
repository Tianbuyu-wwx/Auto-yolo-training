// 浏览器渲染 v8 的边缘对照：采样 body/rail/tbar 颜色 + 出屏截图
import { createRequire } from 'module';
const require = createRequire('C:/Users/Tianbuyu/AppData/Local/hermes/skills/creative/ui-craft-studio/package.json');
const { chromium } = require('playwright');

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
await page.goto('file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/launcher-design/AYT-Launcher-v8.html', { waitUntil: 'domcontentloaded' });
await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
await page.waitForTimeout(1200);

const info = await page.evaluate(() => {
  const g = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return { bg: cs.backgroundColor, w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10, x: r.x, y: r.y };
  };
  return {
    htmlBg: getComputedStyle(document.documentElement).backgroundColor,
    bodyBg: getComputedStyle(document.body).backgroundColor,
    bodyMargin: getComputedStyle(document.body).margin,
    rail: g('.rail'),
    tbar: g('.tbar'),
    win: g('.win'),
  };
});
console.log(JSON.stringify(info, null, 1));
await page.screenshot({ path: 'edge-browser.png' });
await browser.close();
console.log('shot -> edge-browser.png');
