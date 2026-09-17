<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

/**
 * 指标卡（2026-09 改版：左对齐 + 去辉光 + 更新脉冲）。
 *
 * 上一版是「居中大数字 + 彩色辉光」—— 仪表盘模板的默认长相。四张并排时四个
 * 发光数字互相抢注意力，而它们本来没有层级差异；辉光在这里不携带信息。
 *
 * 现在的结构：标签在上（小字 + 语义色点）、数值在下（等宽 + tabular-nums + 左对齐）。
 * 左对齐让四张卡的数字落在同一条基线上，扫读时视线不用左右跳。
 */
const props = defineProps({
  value: { type: [String, Number], default: '—' },
  label: { type: String, default: '' },
  /** 色相：green | blue | amber | red，空串走默认色 */
  tone: { type: String, default: '' },
  /** 可选补注（单位、口径、来源），一行小字 */
  hint: { type: String, default: '' },
})

/**
 * 占位（无数据）与真实数值必须分开渲染：辉光代表「有值且值有意义」，
 * 挂在一个破折号上就只剩装饰。判据是字符本身，避免每个调用点各自传标记。
 */
const isPlaceholder = computed(() => {
  const v = props.value
  return v === null || v === undefined || v === '' || v === '—'
})

/**
 * 数值变化时闪一下底色。
 *
 * WS 每秒推一帧，若数值变了却什么都没发生，界面看起来「不活着」；但每帧都动
 * 又会变成噪音。所以只在**值真的变了**时触发一次 420ms 的底色脉冲
 * （只动 background，不产生位移，重绘代价极低）。
 */
const tick = ref(false)
let timer = null

function placeholderOf(v) {
  return v === null || v === undefined || v === '' || v === '—'
}

watch(() => props.value, (next, prev) => {
  if (prev === undefined || next === prev) return
  if (placeholderOf(next) && placeholderOf(prev)) return   // 占位之间切换不算变化
  tick.value = true
  clearTimeout(timer)
  timer = setTimeout(() => { tick.value = false }, 460)
})

onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <div class="metric">
    <div class="metric-head">
      <span v-if="tone" class="dot" :class="tone"></span>
      <span>{{ label }}</span>
    </div>
    <div class="value" :class="[tone, { placeholder: isPlaceholder, tick }]">{{ value }}</div>
    <div v-if="hint" class="hint">{{ hint }}</div>
  </div>
</template>
