<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from './lib/api.js'

const route = useRoute()
const apiOk = ref(null)     // null=检测中
const running = ref(false)
let timer = null

const NAV = [
  { to: '/', icon: '▣', label: '总览' },
  { to: '/datasets', icon: '▤', label: '数据集' },
  { to: '/train/config', icon: '⚙', label: '训练配置' },
  { to: '/train/monitor', icon: '⏱', label: '训练监控' },
  { to: '/results', icon: '▥', label: '结果 · 模型库' },
  { to: '/queue', icon: '▦', label: '任务队列' },
]

async function pollHealth() {
  try {
    const status = await api.get('/api/trainings/status')
    apiOk.value = true
    running.value = !!status.is_running
  } catch {
    apiOk.value = false
    running.value = false
  }
}

onMounted(() => {
  pollHealth()
  timer = setInterval(pollHealth, 5000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">▌AYT <span>训练控制台</span></div>
      <nav class="nav">
        <router-link v-for="item in NAV" :key="item.to" :to="item.to">
          <span style="width:16px;text-align:center">{{ item.icon }}</span>
          {{ item.label }}
        </router-link>
      </nav>
      <div class="sidebar-foot">Auto YOLO Training<br />v1.0 · 工业控制台</div>
    </aside>

    <div class="main">
      <header class="topbar">
        <h2>{{ route.meta.title || 'AYT' }}</h2>
        <div class="spacer"></div>
        <span v-if="running" class="badge warn"><span class="dot run"></span>训练运行中</span>
        <span class="health">
          <span class="dot" :class="{ ok: apiOk === true, bad: apiOk === false }"></span>
          API {{ apiOk === null ? '…' : apiOk ? '在线' : '离线' }}
        </span>
      </header>
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>
