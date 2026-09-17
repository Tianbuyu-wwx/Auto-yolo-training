<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, errMsg, trainingSocket } from '../lib/api.js'
import { toastErr, toastOk } from '../lib/toast.js'
import { CHART, axisPair } from '../lib/chart-theme.js'
import LineChart from '../components/LineChart.vue'
import LogConsole from '../components/LogConsole.vue'
import MetricCard from '../components/MetricCard.vue'
import StatusBadge from '../components/StatusBadge.vue'

const status = ref(null)
const logs = ref('')
const wsState = ref('…')
const busy = ref(false)

// 曲线数据：前端按 tick 累积（每个 epoch 一个点）
const lossSeries = ref([])
const mapSeries = ref([])
let lastEpoch = -1

function onMessage(msg) {
  status.value = msg.status
  logs.value = msg.logs || ''
  const s = msg.status
  if (s.current_epoch > lastEpoch && s.current_epoch > 0) {
    lastEpoch = s.current_epoch
    lossSeries.value.push([s.current_epoch, Number(s.current_loss.toFixed(4))])
    mapSeries.value.push([s.current_epoch, Number(s.current_map50.toFixed(4))])
    // 上限保护
    if (lossSeries.value.length > 2000) { lossSeries.value.shift(); mapSeries.value.shift() }
  }
}

async function stop() {
  busy.value = true
  try {
    await api.post('/api/trainings/stop')
    toastOk('已发送停止信号（当前 epoch 结束后生效）')
  } catch (e) { toastErr(errMsg(e)) } finally { busy.value = false }
}

const progressPct = computed(() => status.value ? Math.min(100, status.value.progress ?? 0) : 0)
const etaText = computed(() => {
  const eta = status.value?.eta_seconds
  if (eta == null) return ''
  if (eta <= 0) return '即将完成'
  const m = Math.floor(eta / 60), s = Math.round(eta % 60)
  return m < 60 ? `预计剩余 ${m} 分 ${String(s).padStart(2, '0')} 秒` : `预计剩余 ${Math.floor(m / 60)} 时 ${String(m % 60).padStart(2, '0')} 分`
})

const labels = computed(() => status.value?.metric_labels || ['mAP@50', 'mAP@50-95'])

/**
 * 训练结束后后端给的一句话产物去向（best.pt 归档到 exports/、断点留在 run 内）。
 * 只在「跑完且没在跑」时显示：一次新训练会重置 state，但训练中读到的仍是上一次的值。
 */
const artifactNote = computed(() => {
  const s = status.value
  if (!s || s.is_running || !s.artifact_note) return ''
  return s.artifact_note
})

/**
 * 与总览页同一判据：后端字段默认值就是 0，且 WS 每秒推送让 status 恒非空，
 * 所以 `status ? 值 : '—'` 兜底永远不触发 —— 空闲时四张卡显示 0/0 与 0.0000×3。
 */
const hasRun = computed(() => !!status.value && status.value.total_epochs > 0)
const epochText = computed(() => hasRun.value ? `${status.value.current_epoch} / ${status.value.total_epochs}` : '—')
const fmt = (key) => (hasRun.value && status.value[key] != null ? Number(status.value[key]).toFixed(4) : '—')

const lossOption = computed(() => ({
  grid: { ...CHART.grid },
  title: { text: '训练损失', textStyle: { color: CHART.label, fontSize: 12 }, left: 8, top: 4 },
  ...axisPair(),
  series: [{ type: 'line', data: lossSeries.value, showSymbol: false, lineStyle: { color: CHART.line.blue, width: 2 }, areaStyle: { color: CHART.area.blue } }],
}))
const mapOption = computed(() => ({
  grid: { ...CHART.grid },
  title: { text: labels.value.join(' / '), textStyle: { color: CHART.label, fontSize: 12 }, left: 8, top: 4 },
  // mAP 的定义域固定为 0~1，锁死上限否则无数据时纵轴会塌成一条线
  ...axisPair({ yMax: 1 }),
  series: [{ type: 'line', data: mapSeries.value, showSymbol: false, lineStyle: { color: CHART.line.green, width: 2 }, areaStyle: { color: CHART.area.green } }],
}))

let closeWs = null
onMounted(() => { closeWs = trainingSocket(onMessage, (s) => { wsState.value = s }) })
onBeforeUnmount(() => closeWs && closeWs())
</script>

<template>
  <div>
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:20px">
      <StatusBadge v-if="status" :status="status" dot />
      <div style="flex:1"></div>
      <span v-if="wsState === 'disconnected'" class="badge err">实时连接已断开，正在重连…</span>
      <span class="muted mono" style="font-size:11px">WS: {{ wsState }}</span>
      <button class="btn danger" :disabled="busy || !status?.is_running || status?.is_stopping" @click="stop">
        {{ busy ? '发送中…' : '■ 停止训练' }}
      </button>
    </div>

    <!-- 进度条 -->
    <div class="card" style="margin-bottom:16px">
      <!-- 空闲时不放扫光：没有训练在跑，"正在发生"的动效就成了假信号 -->
      <div class="progress-track" :class="{ 'is-idle': !status?.is_running }">
        <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
      </div>
      <div class="progress-meta">
        <span>{{ progressPct.toFixed(1) }}%</span>
        <span class="eta">{{ etaText }}</span>
      </div>
    </div>

    <!-- 产物去向：训练跑完告诉用户"东西放哪了"，不用去猜 runs 路径 -->
    <div v-if="artifactNote" class="card" style="margin-bottom:16px">
      <h3>产物去向</h3>
      <p class="muted" style="font-size:12.5px;margin:0">{{ artifactNote }}完整清单见「结果 · 模型库 → 产物去向」。</p>
    </div>

    <!-- 指标卡 -->
    <div class="grid c4" style="margin-bottom:16px">
      <!-- 四张卡的补注用同一句式：<口径> · <每轮/汇总>。混着写（"尚未开始" /
           "当前轮训练损失" / "训练开始后更新"）会让同一排文字看起来像没填完。 -->
      <MetricCard :value="epochText" label="Epoch" tone="amber"
                  :hint="hasRun ? `总计 ${status.total_epochs} 轮` : '总计轮数待定'" />
      <MetricCard :value="fmt('current_loss')" label="Loss" tone="blue"
                  :hint="hasRun ? '本轮训练损失' : '每轮更新'" />
      <MetricCard :value="fmt('current_map50')" :label="labels[0]" tone="green"
                  :hint="hasRun ? '验证集 · 本轮' : '每轮更新'" />
      <MetricCard :value="fmt('current_map50_95')" :label="labels[1]" tone="green"
                  :hint="hasRun ? '验证集 · 本轮' : '每轮更新'" />
    </div>

    <!-- 曲线 -->
    <div class="grid c2" style="margin-bottom:16px">
      <div class="card">
        <LineChart :option="lossOption" :height="260"
                   empty-text="还没有数据：开始训练后按 epoch 绘制训练损失" />
      </div>
      <div class="card">
        <LineChart :option="mapOption" :height="260"
                   :empty-text="`还没有数据：开始训练后按 epoch 绘制 ${labels.join(' / ')}`" />
      </div>
    </div>

    <!-- 日志 -->
    <div class="card">
      <h3>训练日志</h3>
      <LogConsole :text="logs" :lines="22" />
    </div>
  </div>
</template>
