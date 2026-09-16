<script setup>
import { computed } from 'vue'

/**
 * 训练状态徽标。判定逻辑原先在总览（statusBadge/statusText）与训练监控
 * （模板内三联三元表达式 + 另一份 dot 类名判断）各写一遍，两处对同一份
 * TrainingState 得出不同的类名与文案：
 *   总览   徽标无圆点，成功文案「上次训练完成」
 *   监控   徽标带圆点，成功文案「训练完成」
 * 类名映射本身是纯函数，重复两遍迟早会漂移（例如只给一处补 is_stopping）。
 * 抽到这里，两处差异收敛为 doneLabel 一个 prop。
 */
const props = defineProps({
  /** TrainingState；为 null 时渲染 idle 占位（总览首帧就是这个状态） */
  status: { type: Object, default: null },
  /** 是否渲染前置状态圆点（监控页头部用，总览的系统状态表格里不用） */
  dot: { type: Boolean, default: false },
  /** 非运行状态下 success 的文案：总览要「上次」以免被读成刚刚完成 */
  doneLabel: { type: String, default: '训练完成' },
})

const isFailed = (s) => !!(s && s.error_message && !s.is_running)

const tone = computed(() => {
  const s = props.status
  if (!s) return 'idle'
  if (s.is_running) return 'warn'
  if (s.success) return 'ok'
  if (isFailed(s)) return 'err'
  return 'idle'
})

// 圆点与徽标不同色系：运行中徽标是琥珀底、圆点是实心琥珀并脉冲
const dotTone = computed(() => {
  const s = props.status
  if (!s) return 'idle'
  if (s.is_running) return 'run'
  if (s.success) return 'ok'
  if (isFailed(s)) return 'bad'
  return 'idle'
})

const text = computed(() => {
  const s = props.status
  if (!s) return '—'
  if (s.is_running) return s.is_stopping ? '正在停止…' : `训练中 · ${s.current_stage}`
  if (s.success) return props.doneLabel
  if (isFailed(s)) return '失败'
  return '空闲'
})
</script>

<template>
  <span class="badge" :class="tone"><span v-if="dot" class="dot" :class="dotTone"></span>{{ text }}</span>
</template>
