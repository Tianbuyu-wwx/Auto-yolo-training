<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, errMsg, trainingSocket } from '../lib/api.js'
import StatusBadge from '../components/StatusBadge.vue'
import Skeleton from '../components/Skeleton.vue'

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

const num = (v) => (v == null ? '—' : v)

/**
 * 首屏那句「下一步做什么」。按「有没有可训练数据 → 有没有在训 → 有没有告警」
 * 的优先级给一条具体建议，而不是复读状态徽标（"空闲"两个字用户已经看到了）。
 */
const guidance = computed(() => {
  if (loading.value) return '正在读取数据集、队列与模型清单…'
  if (!trainableCount.value) return '还没有可训练的数据集：去「数据集」上传一个 ZIP，或运行 make smoke 用内置烟雾数据跑通链路。'
  if (status.value?.is_running) return `正在训练：第 ${status.value.current_epoch} / ${status.value.total_epochs} 轮，曲线与日志见「训练监控」。`
  if (issueCount.value) return `${issueCount.value} 个数据集的标注不完整，训练前建议先在「数据集」页看「问题」列。`
  return '一切就绪：选一个数据集即可开始训练。'
})
</script>

<template>
  <div>
    <div v-if="error" class="state-msg error">
      概览数据加载失败：{{ error }}
      <div class="retry"><button class="btn sm" @click="refresh">重试</button></div>
    </div>

    <!-- 状态头：首屏第一眼要回答「现在能不能训、缺什么、下一步做什么」。
         原先这里是与监控页完全重复的四张指标卡（Epoch / Loss / mAP），
         空闲时四张卡全是破折号 —— 焦点落在"没有的东西"上。 -->
    <div class="card" style="margin-bottom:16px">
      <div class="status-hero">
        <div class="hero-main">
          <div class="hero-title">
            <StatusBadge :status="status" done-label="上次训练完成" dot />
            <span v-if="hasRun" class="mono muted" style="font-size:12px">
              第 {{ status.current_epoch }} / {{ status.total_epochs }} 轮
            </span>
          </div>
          <div class="hero-sub">{{ guidance }}</div>
        </div>
        <div class="hero-actions">
          <router-link class="btn primary" to="/train/config">配置并启动训练</router-link>
          <router-link class="btn" to="/train/monitor">查看训练监控</router-link>
        </div>
      </div>

      <!-- 次要计数压成一行：标签在上、数值在下、发丝线分隔，不用四张等权大卡 -->
      <!-- 骨架按真实结构摆：上面一行 11px 标签、下面一行 19px 数值。
           之前只放一块 26px 高的方块，数据到达时高度变化会推一次下面的内容。 -->
      <div v-if="loading" class="stat-strip" style="margin-top:20px">
        <div v-for="i in 4" :key="i" class="stat">
          <!-- 高度按真实行盒算：标签 11px×1.6≈18px、数值 19px×1.6≈30px。
               差几个像素就会在数据到达时把下面的内容整体推动一次。 -->
          <div class="sk" style="margin:0 0 3px;height:18px;width:74px"></div>
          <div class="sk" style="height:30px;width:56px"></div>
        </div>
      </div>
      <div v-else class="stat-strip" style="margin-top:20px">
        <div class="stat">
          <div class="k">可训练数据集</div>
          <div class="v">{{ num(trainableCount) }}<small> / {{ num(scanCount) }} 全部</small></div>
        </div>
        <div class="stat">
          <div class="k">队列</div>
          <div class="v">{{ num(queueCount) }}<small> 待执行/执行中</small></div>
        </div>
        <div class="stat">
          <div class="k">本地预训练模型</div>
          <div class="v">{{ num(localModels) }}<small> 个</small></div>
        </div>
        <div class="stat">
          <div class="k">数据告警</div>
          <div class="v" :class="issueCount ? 'amber' : ''">
            {{ num(issueCount) }}<small> 个数据集</small>
          </div>
        </div>
      </div>
    </div>

    <div class="grid c2">
      <div class="card">
        <h3>系统状态</h3>
        <table class="tbl">
          <tbody>
          <tr>
            <td>训练状态</td>
            <td><StatusBadge :status="status" done-label="上次训练完成" /></td>
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
              <router-link to="/datasets" style="color:var(--blue);margin-left:8px;font-size:12px">查看</router-link>
            </td>
          </tr>
          <tr><td>队列</td><td><span class="mono">{{ num(queueCount) }}</span> 个待执行 / 执行中</td></tr>
          <tr><td>本地预训练模型</td><td><span class="mono">{{ num(localModels) }}</span> 个</td></tr>
          </tbody>
        </table>
        <!-- 骨架行数对齐真实行数（4 行固定 + 可能的告警行），避免加载完成时
             表格高度变化把下方内容推一次 -->
        <div v-if="loading" style="margin-top:10px"><Skeleton variant="row" :count="5" /></div>
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
