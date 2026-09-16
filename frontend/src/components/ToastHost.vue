<script setup>
import { dismissToast, toasts } from '../lib/toast.js'
</script>

<template>
  <!-- 由 App.vue 挂载一次。aria-live=polite 让读屏用户在操作后收到结果 -->
  <div class="toast-host" aria-live="polite" aria-atomic="false">
    <TransitionGroup name="toast">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="t.tone" role="status">
        <span class="toast-text">{{ t.text }}</span>
        <button class="toast-close" type="button" aria-label="关闭" @click="dismissToast(t.id)">×</button>
      </div>
    </TransitionGroup>
  </div>
</template>
