/**
 * 页面挂载冒烟：后端「什么都没有」时，7 个页面都必须能挂载。
 *
 * 这是前端唯一一类能自动发现的整页崩溃 —— 模板里读了 undefined 的字段、
 * 页面忘了处理空列表、组件 prop 传错，都会在这里以「挂载即抛错」的形式暴露；
 * 而这类问题在真机上表现为整页白屏，用户只会说「控制台打不开」。
 *
 * 新增页面 / 新增端点时：在 PAGES 里加一行、在 test/support.js 的
 * EMPTY_PAYLOADS 里补该端点的空形状。
 */
import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../lib/api.js', async () => {
  const { makeApiModule } = await import('../../test/support.js')
  return makeApiModule()
})

import { api } from '../lib/api.js'
import { EMPTY_PAYLOADS, mountPage } from '../../test/support.js'
import DatasetsPage from './DatasetsPage.vue'
import NotFoundPage from './NotFoundPage.vue'
import OverviewPage from './OverviewPage.vue'
import QueuePage from './QueuePage.vue'
import RegistryPage from './RegistryPage.vue'
import ResultsPage from './ResultsPage.vue'
import TrainConfigPage from './TrainConfigPage.vue'
import TrainMonitorPage from './TrainMonitorPage.vue'

const PAGES = [
  ['总览', OverviewPage, '/api/datasets'],
  ['数据集', DatasetsPage, '/api/datasets'],
  ['训练配置', TrainConfigPage, '/api/models'],
  ['训练监控', TrainMonitorPage, null],
  ['结果 · 模型库', ResultsPage, '/api/trainings/runs'],
  ['模型注册中心', RegistryPage, '/api/registry'],
  ['任务队列', QueuePage, '/api/queue/tasks'],
  ['404', NotFoundPage, null],
]

describe('页面挂载冒烟（后端空数据）', () => {
  it.each(PAGES)('%s 页能挂载并渲染出内容', async (_label, component, endpoint) => {
    const w = await mountPage(component)
    await flushPromises()

    expect(w.exists()).toBe(true)
    expect(w.text().trim().length).toBeGreaterThan(0)
    if (endpoint) {
      expect(api.get.mock.calls.some(([p]) => p.startsWith(endpoint))).toBe(true)
    }
    w.unmount()
  })

  it('空数据契约覆盖了所有被页面用到的端点前缀', () => {
    // 页面若新调一个端点，这里会红 —— 提醒去 EMPTY_PAYLOADS 补空形状，
    // 否则那个页面在「后端没有数据」时会拿到 undefined
    const known = Object.keys(EMPTY_PAYLOADS)
    expect(known).toContain('/api/datasets')
    expect(known).toContain('/api/trainings/runs')
    expect(known).toContain('/api/trainings/status')
    expect(known).toContain('/api/queue/tasks')
    expect(known).toContain('/api/registry')
    expect(known).toContain('/api/models')
  })
})
