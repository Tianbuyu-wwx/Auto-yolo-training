<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

/**
 * 图库放大查看。
 *
 * 此前点缩略图是 `target="_blank"` 开一个新标签页看原图：离开当前上下文
 * （run 选中态、滚动位置全丢），训练图往往一次要连着看五六张，来回切标签最烦。
 * 现在在页内开一层遮罩：← → 翻页、Esc 关、点遮罩关、底部保留"新标签打开"
 * 给需要原图尺寸的场景。
 *
 * 用 Teleport 到 body：遮罩必须脱离任何带 transform/filter 的祖先
 * （否则 position:fixed 会以那个祖先为包含块，遮罩会被裁在卡片里）。
 */
const props = defineProps({
  images: { type: Array, required: true },
  index: { type: Number, default: 0 },
})
const emit = defineEmits(['close'])

const current = ref(props.index)
watch(() => props.index, (v) => { current.value = v })

const name = (p) => String(p).split('/').pop()

function step(delta) {
  const n = props.images.length
  if (!n) return
  current.value = (current.value + delta + n) % n
}

function onKey(e) {
  if (e.key === 'Escape') emit('close')
  else if (e.key === 'ArrowRight') step(1)
  else if (e.key === 'ArrowLeft') step(-1)
}

// 打开时锁住背景滚动：否则滚轮会穿透到下面的长页面，关闭后位置全乱
onMounted(() => {
  window.addEventListener('keydown', onKey)
  document.body.classList.add('no-scroll')
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  document.body.classList.remove('no-scroll')
})
</script>

<template>
  <Teleport to="body">
    <div class="lightbox" role="dialog" aria-modal="true" aria-label="结果图预览"
         @click.self="emit('close')">
      <img class="lightbox-img" :src="images[current]" :alt="name(images[current])" />

      <button v-if="images.length > 1" class="lightbox-nav prev" type="button"
              aria-label="上一张" @click.stop="step(-1)">‹</button>
      <button v-if="images.length > 1" class="lightbox-nav next" type="button"
              aria-label="下一张" @click.stop="step(1)">›</button>

      <div class="lightbox-bar">
        <span class="mono">{{ name(images[current]) }}</span>
        <span class="muted">{{ current + 1 }} / {{ images.length }}</span>
        <div class="spacer"></div>
        <a class="link" :href="images[current]" target="_blank" rel="noopener">新标签打开</a>
        <button class="btn sm" type="button" @click="emit('close')">关闭（Esc）</button>
      </div>
    </div>
  </Teleport>
</template>
