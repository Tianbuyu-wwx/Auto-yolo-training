<script setup>
import { dismissToast, toasts } from '../lib/toast.js'
</script>

<template>
  <!-- 由 App.vue 挂载一次。aria-live=polite 让读屏用户在操作后收到结果 -->
  <div class="toast-host" aria-live="polite" aria-atomic="false">
    <TransitionGroup name="toast">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="t.tone" role="status">
        <!-- 状态点取代原先的 border-left 色条：与顶栏健康点、训练状态点同构，
             语义落在"点的颜色"上而不是贴在旁边的一根装饰线 -->
        <span class="dot" aria-hidden="true"></span>
        <span class="toast-text">{{ t.text }}</span>
        <button class="toast-close" type="button" aria-label="关闭" @click="dismissToast(t.id)">×</button>
      </div>
    </TransitionGroup>
  </div>
</template>
