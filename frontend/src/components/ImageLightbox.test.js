/**
 * 图库放大遮罩：翻页 / 关闭 / 滚动锁。这块的失败模式都是"点了没反应"或
 * "关了以后页面滚不动"，因此逐个键位与卸载清理都要钉住。
 */
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import ImageLightbox from './ImageLightbox.vue'

const IMGS = ['/runs/a/plot1.png', '/runs/a/plot2.png', '/runs/a/plot3.png']

/** Teleport 的内容会真实挂到 document.body，wrapper.find 看不到 —— 用 DOM 查询 */
function render(props = {}) {
  return mount(ImageLightbox, {
    props: { images: IMGS, index: 0, ...props },
    global: { stubs: { teleport: true } },
  })
}

function key(k) {
  window.dispatchEvent(new KeyboardEvent('keydown', { key: k }))
}

afterEach(() => { document.body.classList.remove('no-scroll') })

describe('ImageLightbox', () => {
  it('显示当前图与位置（文件名 + 第几张 / 共几张）', () => {
    const w = render({ index: 1 })
    expect(w.find('img').attributes('src')).toBe(IMGS[1])
    expect(w.text()).toContain('plot2.png')
    expect(w.text()).toContain('2 / 3')
  })

  it('→ / ← 翻页，到头会绕回（不把用户卡在最后一张）', async () => {
    const w = render({ index: 2 })
    key('ArrowRight')
    await w.vm.$nextTick()
    expect(w.find('img').attributes('src')).toBe(IMGS[0])
    key('ArrowLeft')
    await w.vm.$nextTick()
    expect(w.find('img').attributes('src')).toBe(IMGS[2])
  })

  it('Esc 关闭、点遮罩关闭，但点图片本身不关', async () => {
    const w = render()
    key('Escape')
    expect(w.emitted('close')).toHaveLength(1)

    await w.find('.lightbox').trigger('click')
    expect(w.emitted('close')).toHaveLength(2)

    await w.find('img').trigger('click')
    expect(w.emitted('close')).toHaveLength(2)
  })

  it('保留"新标签打开"作为原图出口', () => {
    const w = render()
    const link = w.find('.lightbox-bar a')
    expect(link.attributes('href')).toBe(IMGS[0])
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')
  })

  it('只有一张图时不显示翻页按钮', () => {
    const w = render({ images: ['/x/only.png'] })
    expect(w.find('.lightbox-nav').exists()).toBe(false)
  })

  it('打开时锁背景滚动，关闭后解锁（否则滚轮会穿透到下面的长页面）', () => {
    const w = render()
    expect(document.body.classList.contains('no-scroll')).toBe(true)
    w.unmount()
    expect(document.body.classList.contains('no-scroll')).toBe(false)
  })
})
