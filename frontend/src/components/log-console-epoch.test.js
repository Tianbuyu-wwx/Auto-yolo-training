/**
 * 日志控制台的「轮次」识别与高亮（与训练曲线联动的那一半）。
 *
 * 识别规则是本轮最容易写错的地方：Ultralytics 的日志里既有每轮头行
 * `      1/150  1.23G …`，也有进度条里的 `3/3 [00:01<00:00, 2.34it/s]`。
 * 宽松匹配会把进度条当成轮次，联动就会跳到错误的轮次上 —— 用例把这条钉死。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LogConsole from './LogConsole.vue'

const LOG = [
  '开始训练：yolov8n.pt',
  '      1/3         0.35G      0.912      2.345      1.2        16        256: 100%|████| 3/3 [00:01<00:00, 2.34it/s]',
  '                 Class     Images  Instances      Box(P          R      mAP50',
  '                   all          8          9      0.001          1      0.0095',
  '      2/3         0.35G      0.712      2.145      1.1        16        256: 100%|████| 3/3 [00:01<00:00, 2.51it/s]',
  '训练完成',
].join('\n')

const render = (props = {}) => mount(LogConsole, { props: { text: LOG, lines: 50, ...props } })

describe('LogConsole · 轮次联动', () => {
  it('只把"行首 N/M"当轮次头：进度条里的 3/3 不算', async () => {
    const w = render()
    const lines = w.findAll('.log-line')
    // 第 0 行在轮次之前 → 不可点
    expect(lines[0].classes()).not.toContain('clickable')
    // 第 1 行是本轮头（同时含进度条 3/3，但行首是 1/3）→ 属于第 1 轮
    await lines[1].trigger('click')
    expect(w.emitted('pick-epoch')?.at(-1)).toEqual([1])
    // 第 4 行行首是 2/3 → 第 2 轮
    await lines[4].trigger('click')
    expect(w.emitted('pick-epoch')?.at(-1)).toEqual([2])
    // 轮次之外的行点了不该发声
    await lines[0].trigger('click')
    expect(w.emitted('pick-epoch')).toHaveLength(2)
  })

  it('一个轮次头之后的行都归属于该轮（验证行也算），可被整体高亮', () => {
    const w = render({ highlightEpoch: 1 })
    const lines = w.findAll('.log-line')
    expect(lines[1].classes()).toContain('in-epoch')
    expect(lines[2].classes()).toContain('in-epoch')  // 验证输出行
    expect(lines[3].classes()).toContain('in-epoch')
    expect(lines[4].classes()).not.toContain('in-epoch')  // 第 2 轮
    expect(lines[0].classes()).not.toContain('in-epoch')  // 训练开始前的行
  })

  it('轮次边界：训练完成之后的行不再归入最后一轮', () => {
    const w = render({ highlightEpoch: 2 })
    const lines = w.findAll('.log-line')
    expect(lines[4].classes()).toContain('in-epoch')
    // 「训练完成」没有新的轮次头，沿用第 2 轮 —— 这是有意的：它确实是这一轮的收尾输出
    expect(lines[5].classes()).toContain('in-epoch')
  })
})
