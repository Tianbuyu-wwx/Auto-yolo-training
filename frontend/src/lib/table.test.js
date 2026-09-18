/**
 * 表格排序。三个页面共用同一份逻辑，行为必须一致 —— 这些用例就是"一致"的定义：
 * 切方向、空值归位、数字按数值比、含数字的字符串按 numeric 比。
 */
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { useSort } from './table.js'

const make = () => ref([
  { name: 'b', n: 2, at: '2026-01-02', metrics: { mAP50: 0.5 } },
  { name: 'a', n: 10, at: '2026-01-03', metrics: { mAP50: 0.8 } },
  { name: 'ckpt-10', n: null, at: '', metrics: {} },
  { name: 'ckpt-2', n: 1, at: '2026-01-01', metrics: { mAP50: 0.1 } },
])

describe('useSort', () => {
  it('未指定排序列时保持原顺序（后端给的顺序有意义，不要擅自改）', () => {
    const { sorted } = useSort(make())
    expect(sorted.value.map((r) => r.name)).toEqual(['b', 'a', 'ckpt-10', 'ckpt-2'])
  })

  it('点同一列切换升降序，点另一列回到升序', () => {
    const s = useSort(make(), { initial: 'name' })
    expect(s.sortDir.value).toBe('asc')
    s.toggle('name')
    expect(s.sortDir.value).toBe('desc')
    s.toggle('n')
    expect(s.sortKey.value).toBe('n')
    expect(s.sortDir.value).toBe('asc')
  })

  it('数字按数值比大小（10 要排在 2 后面，字典序会排反）', () => {
    const { sorted } = useSort(make(), { initial: 'n' })
    expect(sorted.value.map((r) => r.n)).toEqual([1, 2, 10, null])
  })

  it('字符串按 numeric 比较（ckpt-2 在 ckpt-10 前面）', () => {
    const { sorted } = useSort(make(), { initial: 'name' })
    expect(sorted.value.map((r) => r.name)).toEqual(['a', 'b', 'ckpt-2', 'ckpt-10'])
  })

  it('空值永远排最后，升降序都成立', () => {
    const asc = useSort(make(), { initial: 'n' })
    expect(asc.sorted.value.at(-1).n).toBeNull()
    const desc = useSort(make(), { initial: 'n' })
    desc.toggle('n')
    expect(desc.sortDir.value).toBe('desc')
    expect(desc.sorted.value.at(-1).n).toBeNull()
  })

  it('支持点号路径（嵌套的 metrics.mAP50）', () => {
    const { sorted } = useSort(make(), { initial: 'metrics.mAP50' })
    expect(sorted.value.map((r) => r.metrics.mAP50)).toEqual([0.1, 0.5, 0.8, undefined])
  })

  it('indicator / ariaSort 只对当前排序列返回方向', () => {
    const s = useSort(make(), { initial: 'name' })
    expect(s.indicator('name')).toBe('↑')
    expect(s.indicator('n')).toBe('')
    expect(s.ariaSort('name')).toBe('ascending')
    expect(s.ariaSort('n')).toBe('none')
    s.toggle('name')
    expect(s.indicator('name')).toBe('↓')
    expect(s.ariaSort('name')).toBe('descending')
  })

  it('sorted 是新数组：排序不改动传入的行数组（拉取刷新时不能原地重排）', () => {
    const rows = make()
    const order = [...rows.value]
    const { sorted } = useSort(rows, { initial: 'n' })
    expect(sorted.value).not.toBe(rows.value)
    expect(rows.value).toEqual(order)
  })
})
