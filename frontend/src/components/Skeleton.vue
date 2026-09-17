<script setup>
/**
 * 骨架块。加载时用它把最终布局占住，数据到达只是把灰块换成交付内容 ——
 * 位置不变，视觉上是「变清楚」而不是「跳一下」（顺带把 CLS 压到近 0）。
 */
defineProps({
  /** line | value | block | row */
  variant: { type: String, default: 'line' },
  count: { type: Number, default: 1 },
  width: { type: String, default: '' },
})
</script>

<template>
  <template v-if="count > 1">
    <div v-for="i in count" :key="i" class="sk" :class="`sk-${variant}`"
         :style="width ? { width } : {}" />
  </template>
  <div v-else class="sk" :class="`sk-${variant}`" :style="width ? { width } : {}" />
</template>
