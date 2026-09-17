<script setup>
/**
 * 空态。统一成三段：等宽字形符号 + 一句「为什么是空的」+ 一句「下一步做什么」。
 *
 * 此前各页面各写一句「暂无数据」：既没有下一步指引，也没有任何视觉结构，
 * 读者无法区分「还没开始用」与「渲染失败」。
 */
defineProps({
  /** 单行字形符号（如 '▤' / '▥' / '⌁'）。刻意用等宽字形而不是 emoji —— 
      emoji 会随系统字体变样，也会把工业感的界面拉成消费级观感。 */
  glyph: { type: String, default: '⌁' },
  title: { type: String, required: true },
  hint: { type: String, default: '' },
})
</script>

<template>
  <div class="empty-state">
    <div class="glyph">{{ glyph }}</div>
    <div class="title">{{ title }}</div>
    <div v-if="hint" class="hint">{{ hint }}</div>
    <div v-if="$slots.default" class="actions"><slot /></div>
  </div>
</template>
