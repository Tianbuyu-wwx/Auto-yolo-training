// v5 水引擎诊断探针：canvas 像素采样 + 光斑几何 + 混合模式
import { chromium } from 'playwright';
const URL = 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/tools/launcher-design/AYT-Launcher-v5.html';
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const page = await browser.newPage({ viewport: { width: 1560, height: 940 } });
await page.goto(URL + '?t=' + Date.now(), { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1000);

const sample = () => page.evaluate(() => {
  const cv = document.getElementById('waterCv');
  const ctx = cv.getContext('2d');
  const w = cv.width, h = cv.height;
  const rows = [0.25, 0.5, 0.75];
  let maxA = 0, sum = 0, n = 0;
  rows.forEach(ry => {
    const d = ctx.getImageData(0, Math.floor(h * ry), w, 1).data;
    for (let i = 3; i < d.length; i += 4) { const a = d[i]; if (a > maxA) maxA = a; sum += a; n++; }
  });
  return { w, h, maxA, avgA: +(sum / n).toFixed(2) };
});

const before = await sample();
// 模拟指针划过
await page.mouse.move(600, 420); await page.waitForTimeout(50);
await page.mouse.move(700, 460); await page.waitForTimeout(50);
await page.mouse.move(800, 520); await page.waitForTimeout(50);
await page.waitForTimeout(400);
const after = await sample();

const geo = await page.evaluate(() => {
  const g = (s) => { const el = document.querySelector(s); if (!el) return null; const r = el.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; };
  const cv = document.getElementById('waterCv');
  const cap = getComputedStyle(cv);
  return {
    atmo: g('#atmo'), gA: g('.atmo-glow.gA'), gB: g('.atmo-glow.gB'),
    cv: { opacity: cap.opacity, mix: cap.mixBlendMode, display: cap.display, zIndex: cap.zIndex },
    winRect: g('#win'),
    mainBg: getComputedStyle(document.querySelector('.main')).backgroundColor,
    railBg: getComputedStyle(document.querySelector('.rail')).backgroundColor,
  };
});
console.log(JSON.stringify({ before, after, geo }, null, 1));
await browser.close();
