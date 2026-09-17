/** 图表主题：两张图共用同一套色值与坐标轴，防止一处改动导致图文不一致 */
import { describe, expect, it } from 'vitest'

import { CHART, axisPair } from './chart-theme.js'

describe('CHART 色板', () => {
  it('三个层级色齐备（标签 / 轴线 / 分隔线）', () => {
    expect(CHART.label).toBeTruthy()
    expect(CHART.axis).toBeTruthy()
    expect(CHART.split).toBeTruthy()
  })

  it('面积色是线色的低透明度版本（同色系，读数上不会另起一族）', () => {
    // 线色是 #rrggbb、面积色是 rgba(...)，要先归一成同一进制再比。
    // 直接抓数字会用错进制：#3b82f6 取到的是 "3,82,6"。
    const toRgb = (color) => {
      if (color.startsWith('#')) {
        const hex = color.slice(1)
        return [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(',')
      }
      return color.match(/[\d.]+/g).slice(0, 3).map(Number).join(',')
    }
    expect(toRgb(CHART.area.blue)).toBe(toRgb(CHART.line.blue))
    expect(toRgb(CHART.area.green)).toBe(toRgb(CHART.line.green))
  })
})

describe('axisPair()', () => {
  it('x 轴是 epoch，y 轴不设上限时完全跟随数据', () => {
    const { xAxis, yAxis } = axisPair()
    expect(xAxis.name).toBe('epoch')
    expect(yAxis).not.toHaveProperty('max')
  })

  it('传 yMax 时锁死上限（mAP 锁 1，否则无数据时纵轴会塌成一条线）', () => {
    const { xAxis, yAxis } = axisPair({ yMax: 1 })
    expect(yAxis.max).toBe(1)
    expect(xAxis).not.toHaveProperty('max')
  })

  it('两轴共用同一套标签色与分隔线', () => {
    const { xAxis, yAxis } = axisPair()
    expect(xAxis.axisLabel.color).toBe(CHART.label)
    expect(yAxis.splitLine.lineStyle.color).toBe(CHART.split)
  })
})
