/**
 * 任务队列页 · 工具条与排序。
 *
 * 队列页此前是一张"只能看不能查"的长表：任务一多，"还有谁在排队"和
 * "失败过什么"只能靠肉眼扫颜色。这组用例钉住三件事：筛选（状态分段 +
 * 按数据集搜索）、默认排序（新的在前）、点表头切升降序。
 */
import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../lib/api.js', async () => {
  const { makeApiModule } = await import('../../test/support.js')
  return makeApiModule()
})

import { handlers } from '../lib/api.js'
import { mountPage } from '../../test/support.js'
import QueuePage from './QueuePage.vue'

const TASKS = [
  { id: 1, dataset_name: 'alpha', status: 'done', config: { model: 'yolov8n.pt' }, created_at: '2026-09-18 10:00:00', finished_at: '2026-09-18 10:20:00', error: '' },
  { id: 2, dataset_name: 'beta', status: 'running', config: { model: 'yolov8s.pt' }, created_at: '2026-09-18 11:00:00', finished_at: '', error: '' },
  { id: 3, dataset_name: 'alpha', status: 'failed', config: { model: 'yolov8n.pt' }, created_at: '2026-09-18 12:00:00', finished_at: '2026-09-18 12:05:00', error: 'CUDA out of memory' },
]

async function render(tasks = TASKS) {
  handlers['/api/queue/tasks'] = { tasks }
  const w = await mountPage(QueuePage)
  await flushPromises()
  return w
}

const rowIds = (w) => w.findAll('tbody tr').map((r) => r.findAll('td')[0].text())

describe('QueuePage', () => {
  beforeEach(() => { handlers['/api/queue/tasks'] = { tasks: TASKS } })

  it('默认按 # 倒序：最近提交的在最上面', async () => {
    const w = await render()
    expect(rowIds(w)).toEqual(['3', '2', '1'])
  })

  it('点表头切升降序，方向标记只出现在当前列', async () => {
    const w = await render()
    const idTh = w.findAll('th.sortable')[0]
    expect(idTh.text()).toContain('↓')

    await idTh.trigger('click')
    expect(rowIds(w)).toEqual(['1', '2', '3'])
    expect(w.findAll('th.sortable')[0].text()).toContain('↑')
    // 数据集列没被点过，不该带方向标记
    expect(w.findAll('th.sortable')[1].find('.ind').text()).toBe('')
  })

  it('状态分段筛选 + 右侧计数：筛掉 ≠ 队列空了', async () => {
    const w = await render()
    expect(w.find('.toolbar .count').text()).toContain('3 / 3 条')

    const segButtons = w.findAll('.toolbar .seg button')
    expect(segButtons.map((b) => b.text().split(' ')[0])).toEqual(['全部', '未完成', '已完成', '失败/取消'])
    expect(segButtons[0].text()).toContain('3')

    await segButtons[1].trigger('click') // 未完成 = queued / running / cancel_requested
    expect(rowIds(w)).toEqual(['2'])
    expect(w.find('.toolbar .count').text()).toContain('1 / 3 条')

    await segButtons[3].trigger('click') // 失败/取消
    expect(rowIds(w)).toEqual(['3'])
  })

  it('按数据集搜索（大小写无关）', async () => {
    const w = await render()
    await w.find('.toolbar input[type="search"]').setValue('ALPHA')
    expect(rowIds(w)).toEqual(['3', '1'])
  })

  it('筛到空时提示"当前筛选条件下没有任务"，而不是显示队列空态', async () => {
    const w = await render()
    await w.find('.toolbar input[type="search"]').setValue('不存在的数据集')
    expect(rowIds(w)).toEqual([])
    expect(w.text()).toContain('当前筛选条件下没有任务')
    expect(w.text()).not.toContain('队列是空的')
  })

  it('队列真的为空时给空态与入口，工具条不出现', async () => {
    const w = await render([])
    expect(w.text()).toContain('队列是空的')
    expect(w.find('.toolbar').exists()).toBe(false)
  })
})
