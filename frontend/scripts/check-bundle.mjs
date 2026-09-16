#!/usr/bin/env node
/**
 * 产物预算门禁。
 *
 * 首屏资产直接从 dist/index.html 解析 —— vite 会把入口 module 与它静态依赖的
 * modulepreload 写进 HTML，这正是浏览器首屏必须下载的那几个文件，比按文件名
 * 猜测更准，也不会因为改了 chunk 命名策略而失效。
 *
 * 懒加载的页面 chunk 与 echarts 不在 HTML 里，因此不计入首屏预算，但每个
 * chunk 仍各自受上限约束（防止哪天有人把 echarts 又静态引回来）。
 *
 * 用法：pnpm build && pnpm check-bundle
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
const DIST = join(ROOT, 'dist')

// 预算（字节）。定在当前实测值之上留约 40% 余量：
// 首屏实测 ~113KB / 单 chunk 最大 437KB（echarts）/ CSS ~9.4KB。
// 目的是拦住量级退化（例如整包 echarts 重新静态引入 = +740KB），
// 而不是卡住每次小改动。
const BUDGET = {
  firstPaint: 160 * 1024,
  firstPaintGzip: 64 * 1024,
  anyChunk: 500 * 1024,
  css: 32 * 1024,
}

function kb(n) {
  return (n / 1024).toFixed(1) + ' KB'
}

function size(file) {
  const path = join(DIST, file.replace(/^\//, ''))
  const buf = readFileSync(path)
  return { raw: buf.length, gzip: gzipSync(buf).length }
}

let failed = false
function check(label, actual, limit, extra = '') {
  const ok = actual <= limit
  if (!ok) failed = true
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${label.padEnd(38)} ${kb(actual).padStart(9)} / 预算 ${kb(limit).padStart(9)}${extra}`)
}

const html = readFileSync(join(DIST, 'index.html'), 'utf8')
const firstPaintFiles = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1])

if (!firstPaintFiles.length) {
  console.error('未在 dist/index.html 中找到任何首屏资源，构建产物可能不完整')
  process.exit(1)
}

console.log('首屏资产（由 dist/index.html 解析得出）')
let fpRaw = 0
let fpGzip = 0
let cssRaw = 0
for (const f of firstPaintFiles) {
  const { raw, gzip } = size(f)
  console.log(`    ${f.split('/').pop().padEnd(34)} ${kb(raw).padStart(9)}  gzip ${kb(gzip).padStart(9)}`)
  if (f.endsWith('.css')) cssRaw = raw
  else { fpRaw += raw; fpGzip += gzip }
}
console.log('')
check('首屏 JS 合计', fpRaw, BUDGET.firstPaint)
check('首屏 JS 合计（gzip）', fpGzip, BUDGET.firstPaintGzip)
check('首屏 CSS', cssRaw, BUDGET.css)

console.log('')
console.log('全部 chunk')
const assets = readdirSync(join(DIST, 'assets')).filter((f) => f.endsWith('.js')).sort()
for (const f of assets) {
  const { raw } = size('/assets/' + f)
  const lazy = firstPaintFiles.some((p) => p.endsWith(f)) ? '' : '  (按需)'
  check(f, raw, BUDGET.anyChunk, lazy)
}

console.log('')
if (failed) {
  console.error('产物预算超限 —— 若为有意变更，请一并更新 scripts/check-bundle.mjs 里的 BUDGET 并说明原因。')
  process.exit(1)
}
console.log('产物预算全部通过。')
