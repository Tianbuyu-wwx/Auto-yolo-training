// 免拷贝跑 Playwright：createRequire 指定 skill 目录解析 node_modules
import { createRequire } from 'module';
const require = createRequire('C:/Users/Tianbuyu/AppData/Local/hermes/skills/creative/ui-craft-studio/package.json');
const { chromium } = require('playwright');
console.log('createRequire ok:', typeof chromium.launch === 'function');
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true });
const page = await browser.newPage();
await page.goto('about:blank');
console.log('browser ok:', await page.title() === '');
await browser.close();
console.log('ALL OK — 脚本可从任意目录运行');
