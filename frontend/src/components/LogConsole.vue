<script setup>
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps({
  text: { type: String, default: '' },
  lines: { type: Number, default: 20 },
})

const el = ref(null)

/**
 * 日志渲染上限。完整日志可能上万行，而一屏只看得到 20 多行 —— 全量渲染既浪费
 * 布局时间，也让「每秒追加一行」的 reflow 成本随训练时长线性增长。只渲染结尾
 * N 行，并在顶部注明省略了多少（不藏信息，只是不渲染）。
 */
const MAX_RENDERED = 600

const filter = ref('all')   // all | warn | error

const LEVEL_PATTERNS = {
  error: /\b(ERROR|CRITICAL|FAILED|Traceback)\b|错误|失败/i,
  warn: /\b(WARN(ING)?)\b|警告|缺少|不足/i,
}

const allLines = computed(() => (props.text || '').split('\n'))

const counts = computed(() => {
  let warn = 0, error = 0
  for (const line of allLines.value) {
    if (LEVEL_PATTERNS.error.test(line)) error++
    else if (LEVEL_PATTERNS.warn.test(line)) warn++
  }
  return { warn, error }
})

const kept = computed(() => {
  const lines = allLines.value
  if (filter.value === 'all') return lines
  const re = LEVEL_PATTERNS[filter.value]
  return lines.filter((l) => re.test(l))
})

const rendered = computed(() => {
  const lines = kept.value
  const tail = lines.length > MAX_RENDERED ? lines.slice(-MAX_RENDERED) : lines
  return {
    omitted: lines.length - tail.length,
    lines: tail.map((text) => ({
      text,
      // 级别只用于上色，不改内容。用整行正则而不是拆分 token：日志里的
      // 时间戳/级别/消息可能来自任意库，拆 token 会把未知格式的内容吃掉。
      level: LEVEL_PATTERNS.error.test(text) ? 'error'
        : LEVEL_PATTERNS.warn.test(text) ? 'warn' : '',
    })),
  }
})

// 新日志到达时自动滚到底部（用户手动上滚时暂停跟随）
let stick = true
function onScroll() {
  if (!el.value) return
  stick = el.value.scrollTop + el.value.clientHeight >= el.value.scrollHeight - 24
}
watch(() => [props.text, filter.value], async () => {
  if (!stick) return
  await nextTick()
  if (el.value) el.value.scrollTop = el.value.scrollHeight
})
</script>

<template>
  <div class="log-tools">
    <div class="seg">
      <button type="button" :class="{ on: filter === 'all' }" @click="filter = 'all'">全部</button>
      <button type="button" :class="{ on: filter === 'warn' }" @click="filter = 'warn'">
        警告 {{ counts.warn || '' }}
      </button>
      <button type="button" :class="{ on: filter === 'error' }" @click="filter = 'error'">
        错误 {{ counts.error || '' }}
      </button>
    </div>
    <div class="spacer"></div>
    <span class="count">{{ kept.length }} 行</span>
  </div>
  <!-- 行高从 CSS 变量取（tokens.css 的 .log-console --log-line-height），
       不要在 JS 里另写一个数 —— 原先按 lines*21px 算而实际行高 19.8px，
       460px 高度实际显示 23.3 行，与 lines=22 的语义不符。 -->
  <div ref="el" class="log-console"
       :style="{ maxHeight: `calc(var(--log-line-height, 19.8px) * ${lines})` }"
       @scroll="onScroll">
    <div v-if="rendered.omitted" class="log-omitted">… 更早的 {{ rendered.omitted }} 行未渲染（完整日志见 logs/）</div>
    <template v-if="kept.length">
      <div v-for="(l, i) in rendered.lines" :key="i" :class="['log-line', l.level]">{{ l.text }}</div>
    </template>
    <div v-else class="log-line muted">（没有匹配的日志行）</div>
  </div>
</template>
