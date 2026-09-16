<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api, errMsg, trainingSocket } from '../lib/api.js'

const status = ref(null)
const datasetCount = ref('—')
const queueCount = ref('—')
const localModels = ref('—')
const error = ref('')
let closeWs = null

onMounted(async () => {
  closeWs = trainingSocket((msg) => { status.value = msg.status })
  try {
    const [ds, q, models] = await Promise.all([
      api.get('/api/datasets'),
      api.get('/api/queue/tasks'),
      api.get('/api/models'),
    ])
    datasetCount.value = ds.datasets.length
    queueCount.value = q.tasks.filter(t => t.status === 'queued' || t.status === 'running').length
    localModels.value = models.models.filter(m => m.local).length
  } catch (e) { error.value = errMsg(e) }
})
onBeforeUnmount(() => closeWs && closeWs())

const statusText = (s) => {
  if (!s) return '—'
  if (s.is_running) return s.is_stopping ? '正在停止' : `训练中 · ${s.current_stage}`
  if (s.success) return '上次训练完成'
  if (s.error_message) return `失败`
  return '空闲'
}
const statusBadge = (s) => {
  if (!s) return 'idle'
  if (s.is_running) return 'warn'
  if (s.success) return 'ok'
  if (s.error_message) return 'err'
  return 'idle'
}
</script>

<template>
  <div>
    <div class="grid c4">
      <div class="metric">
        <div class="value amber">{{ status ? `${status.current_epoch}/${status.total_epochs}` : '—' }}</div>
        <div class="label">Epoch</div>
      </div>
      <div class="metric">
        <div class="value blue">{{ status ? status.current_loss.toFixed(4) : '—' }}</div>
        <div class="label">Loss</div>
      </div>
      <div class="metric">
        <div class="value green">{{ status ? status.current_map50.toFixed(4) : '—' }}</div>
        <div class="label">{{ status && status.metric_labels ? status.metric_labels[0] : 'mAP@50' }}</div>
      </div>
      <div class="metric">
        <div class="value green">{{ status ? status.current_map50_95.toFixed(4) : '—' }}</div>
        <div class="label">{{ status && status.metric_labels ? status.metric_labels[1] : 'mAP@50-95' }}</div>
      </div>
    </div>

    <div class="grid c2" style="margin-top:16px">
      <div class="card">
        <h3>系统状态</h3>
        <table class="tbl">
          <tr><td>训练状态</td><td><span class="badge" :class="statusBadge(status)">{{ statusText(status) }}</span></td></tr>
          <tr><td>数据集</td><td><span class="mono">{{ datasetCount }}</span> 个就绪</td></tr>
          <tr><td>队列</td><td><span class="mono">{{ queueCount }}</span> 个待执行 / 执行中</td></tr>
          <tr><td>本地预训练模型</td><td><span class="mono">{{ localModels }}</span> 个</td></tr>
        </table>
        <p v-if="error" class="error-text">{{ error }}</p>
      </div>

      <div class="card">
        <h3>快捷入口</h3>
        <div style="display:flex;flex-direction:column;gap:10px">
          <router-link to="/datasets" style="color:var(--blue)">▤ 管理数据集（上传 ZIP / 校验 / 转换）</router-link>
          <router-link to="/train/config" style="color:var(--blue)">⚙ 配置并启动训练</router-link>
          <router-link to="/train/monitor" style="color:var(--blue)">⏱ 查看训练监控（实时日志 / 曲线）</router-link>
          <router-link to="/queue" style="color:var(--blue)">▦ 任务队列</router-link>
        </div>
      </div>
    </div>
  </div>
</template>
