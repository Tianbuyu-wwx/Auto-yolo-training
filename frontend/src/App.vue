<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, getApiKey, setApiKey } from './lib/api.js'
import { toastOk } from './lib/toast.js'
import ToastHost from './components/ToastHost.vue'

const route = useRoute()
const apiOk = ref(null)     // null=检测中 / true=在线 / false=离线 / 'auth'=缺密钥
const running = ref(false)
let timer = null

// 管理面凭据。后端「方案 A」未配置 YOLO_API_KEY 时不校验，因此默认为空。
const keyOpen = ref(false)
const keyDraft = ref('')
const hasKey = ref(false)
const keyInput = ref(null)

function openKeyPanel() {
  keyDraft.value = getApiKey()
  keyOpen.value = true
  // 面板展开后再聚焦：v-if 之下元素此刻才存在
  requestAnimationFrame(() => keyInput.value && keyInput.value.focus())
}

function saveKey() {
  const next = keyDraft.value.trim()
  setApiKey(next)
  hasKey.value = !!next
  keyOpen.value = false
  // 刻意不刷新页面：顶栏健康检查和训练 WS 每次请求/重连都会重新读 key，
  // 前者 5s 一轮、后者断开后 2s 重连，改完很快就会自动生效。
  toastOk(next ? '密钥已保存，正在重新连接' : '密钥已清除')
}

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
  } catch (e) {
    // 401 不等于「服务离线」—— 服务好好地在，只是不认你。两者混为一谈会把
    // 排查方向整个带偏（去查进程/端口，而真正要做的是填一个 key）。
    apiOk.value = e && e.status === 401 ? 'auth' : false
    running.value = false
  }
}

onMounted(() => {
  hasKey.value = !!getApiKey()
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
            <!-- 四态都要有底：此前 null 时 dot 不带任何类，渲染成透明方块 -->
            <span
              class="dot"
              :class="apiOk === true ? 'ok' : apiOk === 'auth' ? 'warn' : apiOk === false ? 'bad' : 'idle'"
            ></span>
            API {{ apiOk === null ? '…' : apiOk === true ? '在线' : apiOk === 'auth' ? '需要密钥' : '离线' }}
          </span>

          <div class="key-ctl">
            <button
              class="btn sm"
              type="button"
              :aria-expanded="keyOpen"
              title="管理面 API Key"
              @click="keyOpen ? (keyOpen = false) : openKeyPanel()"
            >
              <span class="dot" :class="hasKey ? 'ok' : 'idle'"></span>密钥
            </button>
            <div v-if="keyOpen" class="key-pop">
              <label class="field">
                管理面 API Key
                <input
                  ref="keyInput"
                  v-model="keyDraft"
                  type="password"
                  placeholder="后端未配置则留空"
                  @keyup.enter="saveKey"
                />
              </label>
              <p class="hint">
                后端设置 <code>YOLO_API_KEY</code> 后，这里必须填同一个值；<br />
                留空 = 不带凭据（后端未配置时不校验）。
              </p>
              <div class="key-actions">
                <button class="btn sm primary" type="button" @click="saveKey">保存</button>
                <button class="btn sm" type="button" @click="keyOpen = false">取消</button>
              </div>
            </div>
          </div>
        </div>
      </header>
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>

  <ToastHost />
</template>
