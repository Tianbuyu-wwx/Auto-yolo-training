/**
 * 训练监控页：状态徽标、停止按钮、以及训练结束后的「产物去向」。
 *
 * 产物去向是本轮新增的能力（后端 TrainingState.artifact_note）：训练跑完要告诉
 * 用户东西放哪了，而不是让人去猜 runs 路径。
 */
import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../lib/api.js', async () => {
  const { makeApiModule } = await import('../../test/support.js')
  return makeApiModule()
})

import { api, sockets } from '../lib/api.js'
import { mountPage } from '../../test/support.js'
import TrainMonitorPage from './TrainMonitorPage.vue'

const NOTE = 'best.pt → /as/exports/ds.pt（run 内原件保留）；断点 last.pt 在 /as/runs/detect/ds_auto/weights/。'

async function render(page) {
  const w = await mountPage(page)
  await flushPromises()
  return w
}

/** 喂一帧 WS 消息（页面用 useMessage 驱动整页状态） */
async function push(w, status, logs = '') {
  expect(sockets.length).toBeGreaterThan(0)
  sockets.at(-1).onMessage({ type: 'training', status, logs })
  await flushPromises()
  return w
}

describe('TrainMonitorPage', () => {
  beforeEach(() => { sockets.length = 0 })

  it('首帧之前不猜测状态（指标显示占位而不是 0）', async () => {
    const w = await render(TrainMonitorPage)
    expect(w.text()).toContain('—')
  })

  it('训练结束后显示后端给出的一句话产物去向', async () => {
    const w = await render(TrainMonitorPage)
    await push(w, {
      is_running: false, success: true, current_epoch: 3, total_epochs: 3,
      current_loss: 0.12, current_map50: 0.8, current_map50_95: 0.5, artifact_note: NOTE,
    })

    expect(w.text()).toContain('产物去向')
    expect(w.text()).toContain('/as/exports/ds.pt')
    expect(w.text()).toContain('断点 last.pt')
  })

  it('还在跑的时候不显示去向卡片（哪怕上一轮的 note 还挂在状态里）', async () => {
    const w = await render(TrainMonitorPage)
    await push(w, {
      is_running: true, current_stage: 'training', current_epoch: 1, total_epochs: 3,
      current_loss: 0.9, current_map50: 0.1, current_map50_95: 0.05, artifact_note: NOTE,
    })

    expect(w.text()).toContain('训练中')
    expect(w.text()).not.toContain('产物去向')
  })

  it('停止按钮：非运行态禁用，运行态可点且真的发停止请求', async () => {
    const w = await render(TrainMonitorPage)
    const stopBtn = () => w.findAll('button').find((b) => b.text().includes('停止训练'))

    expect(stopBtn().attributes('disabled')).toBeDefined()

    await push(w, {
      is_running: true, current_stage: 'training', current_epoch: 1, total_epochs: 5,
      current_loss: 0.9, current_map50: 0.1, current_map50_95: 0.05,
    })
    expect(stopBtn().attributes('disabled')).toBeUndefined()

    await stopBtn().trigger('click')
    await flushPromises()
    expect(api.post).toHaveBeenCalledWith('/api/trainings/stop')
  })

  it('WS 断开时明确提示在重连（不要让人以为页面卡住）', async () => {
    const w = await render(TrainMonitorPage)
    sockets.at(-1).onState('disconnected')
    await flushPromises()
    expect(w.text()).toContain('实时连接已断开')
  })
})
