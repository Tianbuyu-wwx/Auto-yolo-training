<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import { lockScroll, onEscape } from '../lib/overlay.js'

/**
 * 右侧抽屉（详情面板）。
 *
 * 为什么用抽屉而不是在页面里再放一张卡：数据集详情原先挂在列表**下方**，
 * 点一行以后内容长出来、把回收站继续往下推 —— 列表越长，"点一行"和"看到
 * 详情"之间的滚动距离越大，而且同一时间页面上有两处都在说"当前选中"。
 * 抽屉把详情提到浮动层里：不改变下方布局、不与列表抢注意力，关掉即回到原位。
 *
 * Teleport 到 body：遮罩与面板必须脱离带 transform/filter 的祖先（否则
 * position:fixed 会以那个祖先为包含块，被裁在卡片里）。
 */
defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
})
const emit = defineEmits(['close'])

let releaseEsc = null
let releaseScroll = null

onMounted(() => {
  // 用共享浮层栈：抽屉里再开图片放大时，Esc 归最上层，滚动锁按引用计数
  releaseEsc = onEscape(() => emit('close'))
  releaseScroll = lockScroll()
})
onBeforeUnmount(() => {
  releaseEsc && releaseEsc()
  releaseScroll && releaseScroll()
})
</script>

<template>
  <Teleport to="body">
    <div class="drawer-scrim" @click.self="emit('close')">
      <aside class="drawer" role="dialog" aria-modal="true" :aria-label="title">
        <header class="drawer-head">
          <div style="min-width:0">
            <h3 class="drawer-title">{{ title }}</h3>
            <p v-if="subtitle" class="drawer-sub">{{ subtitle }}</p>
          </div>
          <button class="btn sm" type="button" @click="emit('close')">关闭（Esc）</button>
        </header>
        <div class="drawer-body">
          <slot />
        </div>
      </aside>
    </div>
  </Teleport>
</template>
