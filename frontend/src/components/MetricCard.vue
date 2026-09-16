<script setup>
import { computed } from 'vue'

/**
 * 指标卡。总览 / 训练监控 / 结果页各写了一遍同样的
 * `div.metric > div.value[.tone] + div.label` 结构（共 12 处），
 * 改一次内边距要在三个文件里找。
 */
const props = defineProps({
  value: { type: [String, Number], default: '—' },
  label: { type: String, default: '' },
  /** 色相：green | blue | amber | red，空串走 .value 的默认色 */
  tone: { type: String, default: '' },
})

/**
 * 占位（无数据）与真实数值必须分开渲染。
 * 34px 的 em dash 加辉光会读成"一根发光的横条"而不是"没有数据"——
 * 占位要退到背景里，数值才是主角。判据是字符本身，避免每个调用点各自传标记。
 */
const isPlaceholder = computed(() => {
  const v = props.value
  return v === null || v === undefined || v === '' || v === '—'
})
</script>

<template>
  <div class="metric">
    <div class="value" :class="[tone, { placeholder: isPlaceholder }]">{{ value }}</div>
    <div class="label">{{ label }}</div>
  </div>
</template>
