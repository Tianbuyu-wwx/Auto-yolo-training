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
