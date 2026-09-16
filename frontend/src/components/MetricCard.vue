<script setup>
/**
 * 指标卡。总览 / 训练监控 / 结果页各写了一遍同样的
 * `div.metric > div.value[.tone] + div.label` 结构（共 12 处），
 * 改一次内边距要在三个文件里找。
 */
defineProps({
  value: { type: [String, Number], default: '—' },
  label: { type: String, default: '' },
  /** 色相：green | blue | amber | red，空串走 .value 的默认色 */
  tone: { type: String, default: '' },
})
</script>

<template>
  <div class="metric">
    <div class="value" :class="tone">{{ value }}</div>
    <div class="label">{{ label }}</div>
  </div>
</template>
