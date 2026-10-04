// v5 终版双态截图：液态玻璃（默认）与经典石墨回退
import { chromium } from 'playwright';
const URL = 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/launcher-design/AYT-Launcher-v5.html';
const OUT = 'E:/项目/Auto-yolo-training/launcher-design/_selfcheck/';
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });

async function shot(name, init){
  const ctx = await browser.newContext({ viewport: { width: 1560, height: 940 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  if (init) await page.addInitScript(init);
  await page.goto(URL + '?t=' + Date.now(), { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 3000))]));
  await page.waitForTimeout(800);
  // 制造涟漪后截图
  await page.mouse.move(430, 320);
  for (let i = 0; i < 20; i++){ await page.mouse.move(430 + i * 28, 320 + Math.sin(i / 3) * 70); await page.waitForTimeout(16); }
  await page.waitForTimeout(280);
  await (await page.$('#stageInner')).screenshot({ path: OUT + name + '.png' });
  await ctx.close(); console.log('shot ->', name);
}

await shot('v5-home-final', null);
await shot('v5-graphite-home', () => { localStorage.setItem('ayt.skin', 'graphite'); });
console.log('DONE');
await browser.close();
