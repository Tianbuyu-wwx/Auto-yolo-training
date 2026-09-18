/**
 * 指标方向。这是注册表版本对比的正确性根基：
 * 方向搞反 → `val/loss` 变大被染成绿色，读者照着颜色就会选错版本。
 */
import { describe, expect, it } from 'vitest'
import { compareMetric, fmtDiff, higherIsBetter } from './metrics.js'

describe('higherIsBetter', () => {
  it('检测/分类主指标越大越好', () => {
    for (const k of ['metrics/mAP50(B)', 'mAP@50', 'precision', 'recall', 'BoxF1', 'accuracy']) {
      expect(higherIsBetter(k), k).toBe(true)
    }
  })

  it('损失/错误率/耗时越小越好', () => {
    for (const k of ['train/box_loss', 'val/cls_loss', 'val/loss', 'mae', 'rmse', 'error_rate', 'inference_time']) {
      expect(higherIsBetter(k), k).toBe(false)
    }
  })
})

describe('compareMetric', () => {
  it('mAP 上升 = 后者更好（绿色那一侧）', () => {
    const r = compareMetric('mAP@50', 0.5, 0.62)
    expect(r.diff).toBeCloseTo(0.12)
    expect(r.winner).toBe('v2')
  })

  it('loss 上升 = 后者更差（不能被染绿）', () => {
    const r = compareMetric('val/box_loss', 1.1, 1.4)
    expect(r.diff).toBeCloseTo(0.3)
    expect(r.winner).toBe('v1')
    expect(r.higherIsBetter).toBe(false)
  })

  it('loss 下降 = 后者更好', () => {
    expect(compareMetric('train/box_loss', 2.0, 1.8).winner).toBe('v2')
  })

  it('相同值判为 same（不制造"提升"噪音）', () => {
    expect(compareMetric('mAP@50', 0.5, 0.5).winner).toBe('same')
    // 浮点回环：1e-17 级差异同样是 same
    expect(compareMetric('mAP@50', 0.5, 0.5 + 1e-17).winner).toBe('same')
  })

  it('缺数据时不编造胜负', () => {
    const r = compareMetric('mAP@50', null, 0.6)
    expect(r.diff).toBeNull()
    expect(r.winner).toBeNull()
  })
})

describe('fmtDiff', () => {
  it('带符号、±0 归零、缺值给占位', () => {
    expect(fmtDiff(0.1234)).toBe('+0.1234')
    expect(fmtDiff(-0.02)).toBe('-0.0200')
    expect(fmtDiff(0)).toBe('±0')
    expect(fmtDiff(null)).toBe('—')
  })
})
