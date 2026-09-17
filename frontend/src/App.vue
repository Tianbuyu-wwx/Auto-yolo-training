<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from './lib/api.js'
import ToastHost from './components/ToastHost.vue'

const route = useRoute()
const apiOk = ref(null)     // null=检测中 / true=在线 / false=离线
const running = ref(false)
let timer = null

// 窄视口提示用：显示当前实际宽度，让用户知道还差多少
const viewportWidth = ref(typeof window === 'undefined' ? 0 : window.innerWidth)
function syncViewport() { viewportWidth.value = window.innerWidth }

const NAV = [
  { to: '/', icon: '▣', label: '总览' },
  { to: '/datasets', icon: '▤', label: '数据集' },
  { to: '/train/config', icon: '⚙', label: '训练配置' },
  { to: '/train/monitor', icon: '⏱', label: '训练监控' },
  { to: '/results', icon: '▥', label: '结果 · 模型库' },
  { to: '/registry', icon: '◈', label: '模型注册中心' },
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
  syncViewport()
  window.addEventListener('resize', syncViewport)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  window.removeEventListener('resize', syncViewport)
})
</script>

<template>
  <!-- 低于支持下限时接管整屏：宁可说清边界，也不让布局无声破版 -->
  <div class="viewport-guard">
    <div class="guard-card">
      <h1>需要更宽的窗口</h1>
      <p>
        AYT 训练控制台是桌面端工具，最低支持 <strong>1024px</strong> 视口宽度。<br />
        请放大浏览器窗口或改用桌面设备访问。
      </p>
      <p class="guard-now">当前视口宽度 {{ viewportWidth }}px</p>
    </div>
  </div>

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
        <div class="topbar-inner">
          <h1>{{ route.meta.title || 'AYT' }}</h1>
          <div class="spacer"></div>
          <span v-if="running" class="badge warn"><span class="dot run"></span>训练运行中</span>
          <span class="health">
            <!-- 三态都要有底：null 时 dot 不带任何类会渲染成透明方块 -->
            <span
              class="dot"
              :class="apiOk === true ? 'ok' : apiOk === false ? 'bad' : 'idle'"
            ></span>
            API {{ apiOk === null ? '…' : apiOk === true ? '在线' : '离线' }}
          </span>
        </div>
      </header>
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>

  <ToastHost />
</template>
