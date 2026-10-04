import { createRequire } from 'module';
const require = createRequire('C:/Users/Tianbuyu/AppData/Local/hermes/skills/creative/ui-craft-studio/package.json');
const { chromium } = require('playwright');
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const page = await browser.newPage({ viewport: { width: 1560, height: 940 } });
page.on('console', m => console.log('[' + m.type() + ']', m.text().slice(0, 260)));
page.on('pageerror', e => console.log('[pageerror]', String(e).slice(0, 500)));
await page.goto('file:///E:/%E9%A1%B9%E7%9B%AE/Auto-yolo-training/launcher-design/AYT-Launcher-v8.html?page=config#', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(1800);
const st = await page.evaluate(() => {
  const btns = [...document.querySelectorAll('.grp-toggle')].map(b => ({
    grp: b.dataset.grp, vis: !!(b.offsetParent), text: b.textContent.trim(),
  }));
  const aug = document.querySelector('.grp-toggle[data-grp="aug"]');
  let parentChain = [];
  let n = aug;
  while (n && n !== document.body && parentChain.length < 6) {
    const cs = getComputedStyle(n);
    parentChain.push((n.id ? '#' + n.id : n.className && typeof n.className === 'string' ? '.' + n.className.split(' ')[0] : n.tagName) + ':' + cs.display + '/' + (n.hidden ? 'HIDDEN' : '') + '/' + cs.visibility);
    n = n.parentElement;
  }
  return {
    btns,
    chain: parentChain,
    recipeHidden: document.getElementById('cfgRecipe') ? document.getElementById('cfgRecipe').hidden : 'no-recipe',
    expertSegment: document.querySelector('.expert-seg .active, [data-expert].active, .seg-act') ? document.querySelector('.expert-seg .active, [data-expert].active, .seg-act').textContent : 'nf',
  };
});
console.log(JSON.stringify(st, null, 1));
await browser.close();
