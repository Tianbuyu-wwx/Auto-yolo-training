<script setup>
import { nextTick, ref, watch } from 'vue'

const props = defineProps({
  text: { type: String, default: '' },
  lines: { type: Number, default: 20 },
})
const el = ref(null)

// 新日志到达时自动滚到底部（用户手动上滚时暂停跟随）
let stick = true
function onScroll() {
  if (!el.value) return
  stick = el.value.scrollTop + el.value.clientHeight >= el.value.scrollHeight - 24
}
watch(() => props.text, async () => {
  if (!stick) return
  await nextTick()
  if (el.value) el.value.scrollTop = el.value.scrollHeight
})
</script>

<template>
  <!-- 行高从 CSS 变量取（tokens.css 的 .log-console --log-line-height），
       不要在 JS 里另写一个数 —— 原先按 lines*21px 算而实际行高 19.8px，
       460px 高度实际显示 23.3 行，与 lines=22 的语义不符。 -->
  <div ref="el" class="log-console"
       :style="{ maxHeight: `calc(var(--log-line-height, 19.8px) * ${lines})` }"
       @scroll="onScroll">{{ text }}</div>
</template>
