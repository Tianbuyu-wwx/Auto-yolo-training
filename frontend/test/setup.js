/**
 * Vitest 全局脚手架。
 *
 * jsdom 里没有 canvas：echarts / zrender 一 init 就会在 `clearRect` 上炸，
 * 于是任何渲染折线图的页面（总览、训练监控）连挂载都过不去。这里把 echarts 的
 * 核心模块换成空壳 —— 组件用例关心的是「数据有没有喂给图表」，不是像素。
 */
import { vi } from 'vitest'

const chartStub = vi.hoisted(() => ({
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
  on: vi.fn(),
  off: vi.fn(),
}))

vi.mock('echarts/core', () => ({
  use: vi.fn(),
  init: vi.fn(() => chartStub),
  getInstanceByDom: vi.fn(() => chartStub),
  __chart: chartStub,
}))
vi.mock('echarts/charts', () => ({ LineChart: {}, BarChart: {} }))
vi.mock('echarts/components', () => ({ GridComponent: {}, TooltipComponent: {} }))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))

/**
 * jsdom 没有实现 scrollIntoView（Element.prototype 上不存在）。
 * 日志联动"滚到该轮第一行"、配置页"定位到出错字段"都会调它 —— 缺这个桩，
 * 用例不会失败在断言上，而是以 **Unhandled Error** 的形式让 vitest 以非零码
 * 退出（本地用 grep 看摘要时极易漏掉，CI 上直接打红）。
 */
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {}
}
