<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, errMsg, trainingSocket } from '../lib/api.js'

const status = ref(null)
const trainableCount = ref(null)   // 可训练（有 data.yaml）
const scanCount = ref(null)        // 磁盘上全部数据集目录
const issueCount = ref(null)
const queueCount = ref(null)
const localModels = ref(null)
const loading = ref(true)
const error = ref('')

let closeWs = null

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const [ds, q, models] = await Promise.all([
      api.get('/api/datasets'),
      api.get('/api/queue/tasks'),
      api.get('/api/models'),
    ])
    trainableCount.value = ds.datasets.length
    scanCount.value = ds.statuses.length
    issueCount.value = ds.statuses.filter(s => s.issues?.length).length
    queueCount.value = q.tasks.filter(t => t.status === 'queued' || t.status === 'running').length
    localModels.value = models.models.filter(m => m.local).length
  } catch (e) {
    error.value = errMsg(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  closeWs = trainingSocket((msg) => { status.value = msg.status })
  refresh()
})
onBeforeUnmount(() => closeWs && closeWs())

/**
 * 后端 TrainingState 的字段默认值全是 0（total_epochs=0 / current_loss=0.0），
 * 而 WS 每秒推送一次，所以 status 恒非空 —— 原先写作 `status ? 值 : '—'`
 * 的兜底永远不触发，空闲时四张卡渲染出 `0/0`、`0.0000`×3，与同屏的「空闲」
 * 徽标语义直接冲突。判据换成「这个服务进程是否真的跑过训练」。
 */
const hasRun = computed(() => !!status.value && status.value.total_epochs > 0)

const epochText = computed(() => hasRun.value ? `${status.value.current_epoch} / ${status.value.total_epochs}` : '—')
const fmt4 = (v) => (v == null ? '—' : Number(v).toFixed(4))
const lossText = computed(() => hasRun.value ? fmt4(status.value.current_loss) : '—')
const mapText = computed(() => hasRun.value ? fmt4(status.value.current_map50) : '—')
const map95Text = computed(() => hasRun.value ? fmt4(status.value.current_map50_95) : '—')

const labels = computed(() => status.value?.metric_labels || ['mAP@50', 'mAP@50-95'])

const statusText = (s) => {
  if (!s) return '—'
  if (s.is_running) return s.is_stopping ? '正在停止' : `训练中 · ${s.current_stage}`
  if (s.success) return '上次训练完成'
  if (s.error_message) return '失败'
  return '空闲'
}
const statusBadge = (s) => {
  if (!s) return 'idle'
  if (s.is_running) return 'warn'
  if (s.success) return 'ok'
  if (s.error_message) return 'err'
  return 'idle'
}
const num = (v) => (v == null ? '—' : v)
</script>

<template>
  <div>
    <p v-if="error" class="state-msg error">
      概览数据加载失败：{{ error }}
      <div class="retry"><button class="btn sm" @click="refresh">重试</button></div>
    </p>

    <div class="grid c4">
      <div class="metric">
        <div class="value amber">{{ epochText }}</div>
        <div class="label">Epoch</div>
      </div>
      <div class="metric">
        <div class="value blue">{{ lossText }}</div>
        <div class="label">Loss</div>
      </div>
      <div class="metric">
        <div class="value green">{{ mapText }}</div>
        <div class="label">{{ labels[0] }}</div>
      </div>
      <div class="metric">
        <div class="value green">{{ map95Text }}</div>
        <div class="label">{{ labels[1] }}</div>
      </div>
    </div>

    <div class="grid c2" style="margin-top:16px">
      <div class="card">
        <h3>系统状态</h3>
        <table class="tbl">
          <tr>
            <td>训练状态</td>
            <td><span class="badge" :class="statusBadge(status)">{{ statusText(status) }}</span></td>
          </tr>
          <tr>
            <td>数据集</td>
            <!-- 两个口径并列：可训练 = 有 data.yaml（训练页下拉的来源），
                 全部 = 磁盘扫描到的目录数。只报一个数字会让用户对不上账。 -->
            <td><span class="mono">{{ num(trainableCount) }} / {{ num(scanCount) }}</span> 可训练 / 全部</td>
          </tr>
          <tr v-if="issueCount">
            <td>数据告警</td>
            <td>
              <span class="badge warn">{{ issueCount }} 个数据集标注不完整</span>
              <router-link to="/datasets" style="color:var(--blue);margin-left:8px;font-size:12.5px">查看</router-link>
            </td>
          </tr>
          <tr><td>队列</td><td><span class="mono">{{ num(queueCount) }}</span> 个待执行 / 执行中</td></tr>
          <tr><td>本地预训练模型</td><td><span class="mono">{{ num(localModels) }}</span> 个</td></tr>
        </table>
        <p v-if="loading" class="muted" style="font-size:12.5px;margin-top:10px">加载中…</p>
      </div>

      <div class="card">
        <h3>快捷入口</h3>
        <div style="display:flex;flex-direction:column;gap:10px">
          <router-link to="/datasets" style="color:var(--blue)">管理数据集（上传 ZIP / 校验 / 转换）</router-link>
          <router-link to="/train/config" style="color:var(--blue)">配置并启动训练</router-link>
          <router-link to="/train/monitor" style="color:var(--blue)">查看训练监控（实时日志 / 曲线）</router-link>
          <router-link to="/queue" style="color:var(--blue)">任务队列</router-link>
        </div>
      </div>
    </div>
  </div>
</template>
