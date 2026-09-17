/**
 * 三个无副作用的展示组件：MetricCard / StatusBadge / LogConsole。
 *
 * 它们的判定逻辑（占位态、状态→文案映射、行高换算）原先散落在各页面里重复实现，
 * 抽成组件后就该在这里钉住 —— 页面层不该再关心「失败时徽标该是什么颜色」。
 */
import { describe, expect, it } from 'vitest'

import { mount } from '@vue/test-utils'

import LogConsole from './LogConsole.vue'
import MetricCard from './MetricCard.vue'
import StatusBadge from './StatusBadge.vue'

describe('MetricCard', () => {
  it('渲染数值与标签，tone 落在数值上', () => {
    const w = mount(MetricCard, { props: { value: '0.8123', label: 'mAP@50', tone: 'green' } })
    expect(w.text()).toContain('0.8123')
    expect(w.text()).toContain('mAP@50')
    expect(w.find('.value').classes()).toContain('green')
  })

  it('默认占位（—）退到背景里，读数时不与真值混淆', () => {
    const w = mount(MetricCard, { props: { value: '—', label: 'Loss' } })
    expect(w.find('.value').classes()).toContain('placeholder')
  })

  it('真值 0 不算占位（0.0 与「没有数据」是两回事）', () => {
    const w = mount(MetricCard, { props: { value: 0, label: 'Loss' } })
    expect(w.find('.value').classes()).not.toContain('placeholder')
    expect(w.text()).toContain('0')
  })
})

describe('StatusBadge', () => {
  const badge = (status, props = {}) => mount(StatusBadge, { props: { status, ...props } })

  it('无状态对象时是 idle 占位（总览首帧）', () => {
    const w = badge(null)
    expect(w.text()).toBe('—')
    expect(w.find('.badge').classes()).toContain('idle')
  })

  it('运行中显示阶段名', () => {
    const w = badge({ is_running: true, current_stage: 'training' })
    expect(w.text()).toContain('训练中 · training')
  })

  it('正在停止时文案不同于运行中（否则用户以为没点中）', () => {
    const w = badge({ is_running: true, is_stopping: true, current_stage: 'training' })
    expect(w.text()).toContain('正在停止')
  })

  it('成功文案可定制：总览要「上次训练完成」以免被读成刚刚完成', () => {
    const w = badge({ is_running: false, success: true }, { doneLabel: '上次训练完成' })
    expect(w.text()).toContain('上次训练完成')
    expect(w.find('.badge').classes()).toContain('ok')
  })

  it('失败要有独立色相', () => {
    const w = badge({ is_running: false, success: false, error_message: 'CUDA out of memory' })
    expect(w.text()).toContain('失败')
    expect(w.find('.badge').classes()).toContain('err')
  })

  it('dot 为真时渲染状态圆点，运行中圆点走脉冲档', () => {
    const w = badge({ is_running: true, current_stage: 'training' }, { dot: true })
    expect(w.find('.dot').classes()).toEqual(expect.arrayContaining(['dot', 'run']))
  })
})

describe('LogConsole', () => {
  it('渲染日志文本', () => {
    const w = mount(LogConsole, { props: { text: 'epoch 1/10\nepoch 2/10' } })
    expect(w.text()).toContain('epoch 2/10')
  })

  it('高度按 CSS 变量折算行数（不要在 JS 里另写行高常量）', () => {
    const w = mount(LogConsole, { props: { text: 'x', lines: 12 } })
    // jsdom 不解析 calc(var(...) * 12)，只能按渲染出来的 style 字符串断言
    expect(w.html()).toContain('--log-line-height')
    expect(w.html()).toContain('12')
  })
})
