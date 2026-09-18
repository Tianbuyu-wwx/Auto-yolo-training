/**
 * 表格排序（客户端、可复用）。
 *
 * 为什么做成 composable 而不是每个页面各写一份 sort 逻辑：队列 / 数据集 /
 * 注册表三张表都要按列排序，而"点同一列切换升降序、点另一列回到升序、
 * 空值排最后"这几条规则写三遍必然漂移（其中一处忘了切方向，用户就会觉得
 * "这两个表行为不一样"）。
 *
 * 取值的点号路径（`config.model`）让排序依据可以是嵌套字段，不必为了排序
 * 在数据里铺一层扁平副本。
 */
import { computed, ref } from 'vue'

function pick(row, key) {
  return key.split('.').reduce((acc, k) => (acc == null ? acc : acc[k]), row)
}

const isEmpty = (v) => v === null || v === undefined || v === ''

function compare(a, b) {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  if (typeof a === 'boolean' && typeof b === 'boolean') return Number(a) - Number(b)
  // numeric:true 让 "ckpt-2" 排在 "ckpt-10" 前面；中文按拼音
  return String(a).localeCompare(String(b), 'zh-Hans-CN', { numeric: true })
}

/**
 * @param rows   Ref<Array>：要排序的行
 * @param opts.initial 初始排序列（'' = 保持原序）
 * @param opts.dir     初始方向
 */
export function useSort(rows, { initial = '', dir = 'asc' } = {}) {
  const sortKey = ref(initial)
  const sortDir = ref(dir)

  function toggle(key) {
    if (sortKey.value === key) {
      sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortKey.value = key
      sortDir.value = 'asc'
    }
  }

  /** 表头里的方向标记；未排序的列返回空串 */
  function indicator(key) {
    if (sortKey.value !== key) return ''
    return sortDir.value === 'asc' ? '↑' : '↓'
  }

  function ariaSort(key) {
    if (sortKey.value !== key) return 'none'
    return sortDir.value === 'asc' ? 'ascending' : 'descending'
  }

  const sorted = computed(() => {
    const key = sortKey.value
    if (!key) return rows.value
    const factor = sortDir.value === 'asc' ? 1 : -1
    return [...rows.value].sort((a, b) => {
      const av = pick(a, key)
      const bv = pick(b, key)
      // 空值排最后 —— **与方向无关**。直接把方向乘进 compare 会把空值
      // 在降序时顶到最前面（这正是本文件第一条用例钉住的回归）。
      if (isEmpty(av) || isEmpty(bv)) return (isEmpty(av) ? 1 : 0) - (isEmpty(bv) ? 1 : 0)
      return factor * compare(av, bv)
    })
  })

  return { sorted, sortKey, sortDir, toggle, indicator, ariaSort }
}
