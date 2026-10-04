// 场景原型截图：软件 WebGL（SwiftShader）headless
import { chromium } from 'playwright';
const URL = process.env.SCENE_URL || 'file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/launcher-design/_selfcheck/proto-yozakura.html';
const OUT = process.env.SCENE_OUT || 'E:/项目/Auto-yolo-training/launcher-design/_selfcheck/proto-yozakura.png';

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH,
  headless: true,
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist']
});
const page = await browser.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1.5 });
const errs = [];
page.on('pageerror', e => errs.push(String(e)));
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
await page.goto(URL + '?t=' + Date.now(), { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(600);
const ready = await page.evaluate(() => window.__sceneReady === true).catch(() => false);
console.log('sceneReady =', ready);
// 模拟鼠标移动感受视差
await page.mouse.move(1050, 380); await page.waitForTimeout(120);
await page.mouse.move(1200, 420); await page.waitForTimeout(120);
await page.waitForTimeout(2200);   // 让花瓣落到有层次的状态
await page.screenshot({ path: OUT });
console.log('shot ->', OUT);
if (errs.length) console.log('ERRORS:', errs.slice(0, 5).join(' | '));
await browser.close();
