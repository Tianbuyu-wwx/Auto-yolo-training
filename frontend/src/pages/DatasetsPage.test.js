/**
 * 数据集页 · 详情抽屉。
 *
 * 详情原先挂在列表下方：点一行 → 内容长出来 → 把回收站继续往下推，列表越长
 * 「点行」与「看到详情」之间的滚动距离越大，同一屏还有两处在说"当前选中"。
 * 这组用例钉住抽屉化之后的四件事：打开、样本放大、Esc 只关最上层、
 * 滚动锁按引用计数（关掉上层不能把下层的锁一起放掉）。
 */
import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../lib/api.js', async () => {
  const { makeApiModule } = await import('../../test/support.js')
  return makeApiModule()
})

import { handlers } from '../lib/api.js'
import { mountPage } from '../../test/support.js'
import DatasetsPage from './DatasetsPage.vue'

const STATUS = {
  name: 'ds', format: 'yolo', image_count: 10, label_count: 9,
  is_trainable: true, is_ready: true, needs_conversion: false,
  issues: ['val 集 1 张图片无标注'],
}

const pressEscape = () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))

async function render() {
  const w = await mountPage(DatasetsPage)
  await flushPromises()
  return w
}

/** 点第一行 → 打开抽屉 */
async function openDrawer(w) {
  await w.findAll('tbody tr')[0].trigger('click')
  await flushPromises()
  return w
}

describe('DatasetsPage · 详情抽屉', () => {
  beforeEach(() => {
    handlers['/api/datasets'] = { datasets: ['ds'], statuses: [STATUS] }
    // 详情与预览端点比列表更长，靠 support.js 的"最长前缀匹配"命中
    handlers['/api/datasets/ds'] = {
      name: 'ds', format: 'yolo', image_count: 10, label_count: 9,
      splits: { train: { images: 8, labels: 8 }, val: { images: 2, labels: 1 } },
    }
    handlers['/api/datasets/ds/preview'] = { images: ['/p/0.jpg', '/p/1.jpg'] }
    handlers['/api/recycle'] = { items: [] }
    document.body.className = ''
  })

  it('初始不显示抽屉；点一行才打开，并给出该数据集的明细与告警', async () => {
    const w = await render()
    expect(document.body.querySelector('.drawer')).toBeFalsy()

    await openDrawer(w)
    const drawer = document.body.querySelector('.drawer')
    expect(drawer).toBeTruthy()
    const text = drawer.textContent
    expect(text).toContain('ds')
    expect(text).toContain('10 图')
    expect(text).toContain('val')          // 划分明细
    expect(text).toContain('1 项告警')      // 事实条里的告警徽标
    expect(text).toContain('val 集 1 张图片无标注')
    expect(drawer.querySelectorAll('.gallery .thumb')).toHaveLength(2)
    w.unmount()
  })

  it('点样本缩略图在遮罩里放大（复用结果页那套）', async () => {
    const w = await render()
    await openDrawer(w)
    await document.body.querySelector('.gallery .thumb').click()
    await flushPromises()

    const box = document.body.querySelector('.lightbox')
    expect(box).toBeTruthy()
    expect(box.querySelector('img').getAttribute('src')).toBe('/p/0.jpg')
    w.unmount()
  })

  it('Esc 只关最上面那层：先关放大，再关抽屉', async () => {
    const w = await render()
    await openDrawer(w)
    await document.body.querySelector('.gallery .thumb').click()
    await flushPromises()

    pressEscape()
    await flushPromises()
    expect(document.body.querySelector('.lightbox')).toBeFalsy()
    expect(document.body.querySelector('.drawer')).toBeTruthy()   // 抽屉还在

    pressEscape()
    await flushPromises()
    expect(document.body.querySelector('.drawer')).toBeFalsy()
    w.unmount()
  })

  it('滚动锁按引用计数：关掉上层不能把下层的锁放掉', async () => {
    const w = await render()
    await openDrawer(w)
    expect(document.body.classList.contains('no-scroll')).toBe(true)

    await document.body.querySelector('.gallery .thumb').click()
    await flushPromises()
    expect(document.body.classList.contains('no-scroll')).toBe(true)

    pressEscape()   // 关掉放大，抽屉仍开着
    await flushPromises()
    expect(document.body.classList.contains('no-scroll')).toBe(true)

    pressEscape()   // 关掉抽屉 → 才解锁
    await flushPromises()
    expect(document.body.classList.contains('no-scroll')).toBe(false)
    w.unmount()
  })

  it('关闭按钮同样能关掉抽屉', async () => {
    const w = await render()
    await openDrawer(w)
    const closeBtn = [...document.body.querySelectorAll('.drawer-head button')]
      .find((b) => b.textContent.includes('关闭'))
    closeBtn.click()
    await flushPromises()
    expect(document.body.querySelector('.drawer')).toBeFalsy()
    w.unmount()
  })
})
