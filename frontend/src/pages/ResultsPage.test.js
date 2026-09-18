/**
 * 结果页 · 产物去向。
 *
 * 这一页承担「我的产物去哪了」：审计里出现过「界面显示 runs 路径但文件已被搬走」
 * 的误导（训练成功后结果页只有一句「无权重」）。用例按三种真实场景钉住表现：
 * 产物齐全、best.pt 已不在原位但有数据集级副本、接口挂了（不能退化成「暂无产物」）。
 */
import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../lib/api.js', async () => {
  const { makeApiModule } = await import('../../test/support.js')
  return makeApiModule()
})

import { api, handlers } from '../lib/api.js'
import { mountPage } from '../../test/support.js'
import ResultsPage from './ResultsPage.vue'

const RUN_ROW = {
  run: 'ds_auto',
  path: 'E:/repo/runs/detect/ds_auto',
  has_best: true,
  has_last: true,
  has_results: true,
  resumable: true,
  size_bytes: 6618906,
  size_mb: 6.31,
  modified: '2026-09-17 21:53',
  dataset: 'ds',
  exported_copy: true,
}

function runsPayload(artifacts) {
  return { runs: ['ds_auto'], checkpoints: [], checkpoint_details: [], artifacts }
}

const ARTS_OK = {
  runs: [RUN_ROW],
  exports: { ds: { path: 'E:/repo/exports/ds.pt', size_bytes: 6188906, size_mb: 5.9, modified: '2026-09-17 21:53' } },
  recycle_dir: 'E:/repo/runs/.recycle',
  recycled_count: 2,
  recycled_sample: ['ds_auto-2', 'ds_auto-3'],
}

async function render() {
  const w = await mountPage(ResultsPage)
  await flushPromises()
  return w
}

describe('ResultsPage', () => {
  beforeEach(() => {
    handlers['/api/trainings/runs'] = { runs: [], checkpoints: [], checkpoint_details: [], artifacts: null }
    handlers['/api/trainings/results'] = {
      run_name: 'ds_auto',
      has_weights: true,
      download_url: '/api/trainings/runs/ds_auto/download',
      final_metrics: { mAP50: 0.81, mAP50_95: 0.52, epoch: 3 },
      plot_urls: [],
      metric_labels: ['mAP@50', 'mAP@50-95'],
    }
    handlers['/api/registry'] = { datasets: {} }
  })

  it('一个 run 都没有时，指向「去训练」而不是报错', async () => {
    const w = await render()
    expect(w.text()).toContain('暂无训练产物，先去「训练配置」启动一次训练')
  })

  it('产物齐全时列出 best.pt / 断点 / results.csv / 导出件，并给出回收站可恢复项', async () => {
    handlers['/api/trainings/runs'] = runsPayload(ARTS_OK)
    const w = await render()
    const text = w.text()

    expect(text).toContain('产物去向')
    expect(text).toContain('在 run 内')
    expect(text).toContain('可续训')
    expect(text).toContain('E:/repo/exports/ds.pt')
    expect(text).toContain('E:/repo/runs/detect/ds_auto')
    expect(text).toContain('回收站有 2 项可恢复')
    // 产物齐全 → 导出按钮可用，且不该出现任何「不在原位」的解释
    expect(w.find('button.primary').attributes('disabled')).toBeUndefined()
    expect(text).not.toContain('已不在原位')
  })

  it('best.pt 不在 run 内但有数据集级副本时：解释清楚，并禁用导出', async () => {
    handlers['/api/trainings/runs'] = runsPayload({
      ...ARTS_OK,
      runs: [{ ...RUN_ROW, has_best: false, exported_copy: true }],
    })
    handlers['/api/trainings/results'] = {
      ...handlers['/api/trainings/results'],
      has_weights: false,
      download_url: null,
    }
    const w = await render()
    const text = w.text()

    expect(text).toContain('不在 run 内')
    expect(text).toContain('副本')
    expect(text).toContain('已不在原位')
    // 没有 best.pt 就不能导出（后端读的就是 run 内的那个文件）
    expect(w.find('button.primary').attributes('disabled')).toBeDefined()
    expect(w.text()).not.toContain('下载 best.pt')
  })

  it('图库点缩略图在页内放大：可翻页、可 Esc 关闭，不再跳新标签页', async () => {
    handlers['/api/trainings/runs'] = runsPayload(ARTS_OK)
    handlers['/api/trainings/results'] = {
      ...handlers['/api/trainings/results'],
      plot_urls: ['/runs/ds_auto/plot1.png', '/runs/ds_auto/plot2.png'],
    }
    const w = await render()

    const thumbs = w.findAll('.gallery .thumb')
    expect(thumbs).toHaveLength(2)
    // 缩略图必须是按钮（页内放大）而不是 target=_blank 的链接：连着看五六张图
    // 时来回切标签会把 run 选中态和滚动位置全丢掉
    expect(w.find('.gallery a').exists()).toBe(false)

    await thumbs[0].trigger('click')
    const box = document.body.querySelector('.lightbox')
    expect(box).toBeTruthy()
    expect(box.querySelector('img').getAttribute('src')).toBe('/runs/ds_auto/plot1.png')
    expect(box.textContent).toContain('1 / 2')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
    await flushPromises()
    expect(document.body.querySelector('.lightbox img').getAttribute('src')).toBe('/runs/ds_auto/plot2.png')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(document.body.querySelector('.lightbox')).toBeFalsy()
    w.unmount()
  })

  it('接口失败时给错误态与重试，而不是伪装成「暂无训练产物」', async () => {
    api.get.mockImplementationOnce(async () => {
      const e = new Error('Internal Server Error')
      e.status = 500
      throw e
    })
    const w = await render()
    const text = w.text()

    expect(text).toContain('训练记录加载失败')
    expect(text).toContain('Internal Server Error')
    expect(text).toContain('重试')
    expect(text).not.toContain('暂无训练产物')
  })
})
