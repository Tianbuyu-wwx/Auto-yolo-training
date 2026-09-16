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
  <div ref="el" class="log-console" :style="{ maxHeight: lines * 21 + 'px' }" @scroll="onScroll">{{ text }}</div>
</template>
