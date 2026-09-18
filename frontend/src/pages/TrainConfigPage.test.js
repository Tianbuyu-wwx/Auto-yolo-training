/**
 * 训练配置页：单位 / 范围校验 / 分组摘要。
 *
 * 这些用例的判据都是**用户能看到的后果**：量纲写清楚（px、轮）、填错了立刻在
 * 字段下方说清为什么不合法、不合法时主按钮不可点且能一键定位到出错的字段。
 * 之前这些都没有：字段只有一行灰标签 + 裸输入框，填错要等提交才失败。
 */
import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../lib/api.js', async () => {
  const { makeApiModule } = await import('../../test/support.js')
  return makeApiModule()
})

import { handlers } from '../lib/api.js'
import { mountPage } from '../../test/support.js'
import TrainConfigPage from './TrainConfigPage.vue'

async function render({ pickDataset = true } = {}) {
  const w = await mountPage(TrainConfigPage)
  await flushPromises()
  // 未选数据集时主按钮本来就是禁用的（canSubmit 要求 dataset_name），
  // 所以校验类用例先选上数据集，才能把"禁用"归因到校验本身
  if (pickDataset) {
    await w.findAll('select')[0].setValue('ds')
    await flushPromises()
  }
  return w
}

/** 主操作按钮（立即开始训练 / 加入队列 之前那个 primary） */
const submit = (w) => w.findAll('button.primary')[0]

beforeEach(() => {
  handlers['/api/datasets'] = {
    datasets: ['ds'],
    statuses: [{
      name: 'ds', is_trainable: true, is_ready: true, needs_conversion: false,
      image_count: 100, label_count: 100, issues: [],
    }],
  }
  handlers['/api/models'] = { models: ['yolov8n.pt'], local: ['yolov8n.pt'] }
  handlers['/api/trainings/runs'] = {
    runs: [], checkpoints: [], checkpoint_details: [], artifacts: null,
  }
})

describe('TrainConfigPage', () => {
  it('字段带单位与说明：数量级一眼可辨（640 是像素、150 是轮）', async () => {
    const w = await render()
    const imgsz = w.find('[data-field="imgsz"]')
    expect(imgsz.exists()).toBe(true)
    expect(imgsz.element.closest('.field').textContent).toContain('px')
    expect(imgsz.element.closest('.field').textContent).toContain('32 的倍数')
    expect(w.find('[data-field="epochs"]').element.closest('.field').textContent).toContain('轮')
  })

  it('越界值当场标红并说明原因，主按钮同时不可点', async () => {
    const w = await render()
    expect(submit(w).attributes('disabled')).toBeUndefined()

    await w.find('[data-field="epochs"]').setValue(0)
    expect(w.find('[data-field="epochs"]').classes()).toContain('invalid')
    expect(w.text()).toContain('不能小于 1')
    expect(w.text()).toContain('项参数需要修正')
    expect(submit(w).attributes('disabled')).toBeDefined()

    // 改回合法值 → 立刻恢复（校验不是一次性的表单级报错）
    await w.find('[data-field="epochs"]').setValue(150)
    expect(w.text()).not.toContain('项参数需要修正')
    expect(submit(w).attributes('disabled')).toBeUndefined()
  })

  it('输入尺寸必须是 32 的倍数（下采样步长，否则训练中途才会炸）', async () => {
    const w = await render()
    await w.find('[data-field="imgsz"]').setValue(100)
    expect(w.text()).toContain('必须是 32 的倍数')
    await w.find('[data-field="imgsz"]').setValue(640)
    // 提示文案里同样含"必须是 32 的倍数"，所以按"红框是否消失"判断，而不是按文本
    expect(w.find('[data-field="imgsz"]').classes()).not.toContain('invalid')
    expect(submit(w).attributes('disabled')).toBeUndefined()
  })

  it('跨字段校验：预热轮数不能超过总轮数', async () => {
    const w = await render()
    await w.find('[data-field="epochs"]').setValue(10)
    await w.find('[data-field="warmup_epochs"]').setValue(50)
    expect(w.text()).toContain('不能超过训练轮数')
  })

  it('高级组默认收起但显示当前取值摘要，展开后才出现输入框', async () => {
    const w = await render()
    // 收起 ≠ 看不见：数据增强那一组收起时也要能读到关键取值
    expect(w.find('[data-field="mosaic"]').exists()).toBe(false)
    expect(w.text()).toContain('Mosaic 1')

    const aug = w.findAll('.card').find((c) => c.text().includes('数据增强'))
    await aug.findAll('button').find((b) => b.text().includes('展开')).trigger('click')
    expect(w.find('[data-field="mosaic"]').exists()).toBe(true)
  })

  it('执行卡常显配置摘要，滚到任何位置都能核对将提交什么', async () => {
    const w = await render()
    const summary = w.find('.exec-summary')
    expect(summary.exists()).toBe(true)
    expect(summary.text()).toContain('ds')
    expect(summary.text()).toContain('150 轮')
    expect(summary.text()).toContain('640 px')
  })
})
