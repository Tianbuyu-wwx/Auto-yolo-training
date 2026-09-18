<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, errMsg } from '../lib/api.js'
import EmptyState from '../components/EmptyState.vue'
import Skeleton from '../components/Skeleton.vue'
import { toastErr, toastOk } from '../lib/toast.js'
import { useSort } from '../lib/table.js'

const tasks = ref([])
const error = ref('')
const loading = ref(true)
const query = ref('')          // 按数据集名筛选
const statusFilter = ref('all') // all | active | done | failed
let timer = null

/**
 * 状态分组筛选。队列一长，"看还有谁在排队"与"看失败过什么"是两类不同问题，
 * 靠肉眼看颜色扫表太慢 —— 分类是表格该做的事。
 */
const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'active', label: '未完成' },
  { key: 'done', label: '已完成' },
  { key: 'failed', label: '失败/取消' },
]

/**
 * 状态谓词必须是**纯函数**。
 * 先前这段是 `filterCount()` 临时改写 statusFilter 再读回可见列表 —— 在渲染
 * 过程中改响应式状态，Vue 直接抛 "Maximum recursive updates exceeded"：
 * 每个分段按钮的计数都触发一次重渲染，重渲染又改状态，无限递归。
 */
const inStatus = (key, t) => {
  if (key === 'all') return true
  if (key === 'active') return ['queued', 'running', 'cancel_requested'].includes(t.status)
  if (key === 'done') return t.status === 'done'
  return ['failed', 'cancelled'].includes(t.status)
}
const matchQuery = (t) => {
  const q = query.value.trim().toLowerCase()
  return !q || String(t.dataset_name).toLowerCase().includes(q)
}

const visibleTasks = computed(() => tasks.value.filter((t) => inStatus(statusFilter.value, t) && matchQuery(t)))

/** 分段按钮上的计数：按状态数（不受搜索词影响），与右侧 "可见 / 全部" 各管一件事 */
const filterCount = (key) => tasks.value.filter((t) => inStatus(key, t)).length

/** 默认按 # 降序：最近提交的在最上面（队列的时间语义就是"新→旧"） */
const { sorted: sortedTasks, sortKey, toggle: toggleSort, indicator: sortInd, ariaSort } =
  useSort(visibleTasks, { initial: 'id', dir: 'desc' })

/**
 * 状态用「颜色 + 中文」表达，不再用彩色 Emoji。
 * 原先的 🟡🟢✅❌⛔🟠 走 Segoe UI Emoji 字形，基线与尺寸无法与表格文字对齐
 * （R6 截图里状态列明显偏大偏下），且 'running'/'done' 这类原始枚举不适合
 * 直接呈现给用户。原始枚举保留在 title 里，便于对日志排查。
 */
const STATUS = {
  queued: { cls: 'warn', dot: 'run', text: '排队中' },
  running: { cls: 'warn', dot: 'run', text: '执行中' },
  cancel_requested: { cls: 'idle', dot: 'idle', text: '取消中' },
  done: { cls: 'ok', dot: 'ok', text: '已完成' },
  failed: { cls: 'err', dot: 'bad', text: '失败' },
  cancelled: { cls: 'idle', dot: 'idle', text: '已取消' },
}
const st = (s) => STATUS[s] || { cls: 'idle', dot: 'idle', text: s || '未知' }

async function refresh() {
  try {
    tasks.value = (await api.get('/api/queue/tasks')).tasks
    error.value = ''
  } catch (e) { error.value = errMsg(e) } finally { loading.value = false }
}

async function cancel(id) {
  try {
    await api.post(`/api/queue/${id}/cancel`)
    toastOk(`任务 #${id} 已发送取消请求`)
  } catch (e) { toastErr(errMsg(e)) }
  await refresh()
}

onMounted(() => { refresh(); timer = setInterval(refresh, 5000) })
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div>
    <p class="hint" style="margin-bottom:16px;font-size:13px">
      任务持久化到 SQLite，Web 重启不丢失；由队列按顺序执行，训练在独立子进程运行。
      在「训练配置」页点击「加入队列」提交任务。
    </p>

    <div class="card">
      <div v-if="error" class="state-msg error">
        队列读取失败：{{ error }}
        <div class="retry"><button class="btn sm" @click="refresh">重试</button></div>
      </div>

      <template v-else>
        <div v-if="loading" style="padding:6px 0"><Skeleton variant="row" :count="4" /></div>

        <EmptyState v-else-if="!tasks.length" glyph="▦" title="队列是空的"
                    hint="在「训练配置」页点「加入队列」，任务会在这里按顺序执行；执行中的任务会显示状态与取消按钮。">
          <router-link class="btn sm" to="/train/config">去配置训练</router-link>
        </EmptyState>

        <template v-else>
          <!-- 工具条：与其他表格页同一套（筛选 + 计数）。队列一长就必须能筛，
               而且"还有谁在排队"与"失败过什么"是两类问题，靠扫颜色太慢。 -->
          <div class="toolbar">
            <input v-model="query" type="search" placeholder="按数据集筛选…" />
            <div class="seg">
              <button v-for="f in FILTERS" :key="f.key" type="button"
                      :class="{ on: statusFilter === f.key }" @click="statusFilter = f.key">
                {{ f.label }} {{ filterCount(f.key) }}
              </button>
            </div>
            <div class="spacer"></div>
            <span class="count">{{ sortedTasks.length }} / {{ tasks.length }} 条</span>
          </div>

          <div class="table-wrap">
          <table class="tbl fixed">
            <colgroup>
              <col style="width:6%" /><col style="width:18%" /><col style="width:15%" />
              <col style="width:12%" /><col style="width:15%" /><col style="width:15%" /><col style="width:19%" />
            </colgroup>
            <thead>
              <tr>
                <th class="sortable" :class="{ sorted: sortKey === 'id' }" :aria-sort="ariaSort('id')" @click="toggleSort('id')">#<span class="ind">{{ sortInd('id') }}</span></th>
                <th class="sortable" :class="{ sorted: sortKey === 'dataset_name' }" :aria-sort="ariaSort('dataset_name')" @click="toggleSort('dataset_name')">数据集<span class="ind">{{ sortInd('dataset_name') }}</span></th>
                <th>模型</th>
                <th class="sortable" :class="{ sorted: sortKey === 'status' }" :aria-sort="ariaSort('status')" @click="toggleSort('status')">状态<span class="ind">{{ sortInd('status') }}</span></th>
                <th class="sortable" :class="{ sorted: sortKey === 'created_at' }" :aria-sort="ariaSort('created_at')" @click="toggleSort('created_at')">创建时间<span class="ind">{{ sortInd('created_at') }}</span></th>
                <th class="sortable" :class="{ sorted: sortKey === 'finished_at' }" :aria-sort="ariaSort('finished_at')" @click="toggleSort('finished_at')">结束时间<span class="ind">{{ sortInd('finished_at') }}</span></th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in sortedTasks" :key="t.id">
                <td class="mono">{{ t.id }}</td>
                <td>{{ t.dataset_name }}</td>
                <td class="mono">{{ t.config?.model }}</td>
                <td :title="t.status">
                  <span class="badge" :class="st(t.status).cls">
                    <span class="dot" :class="st(t.status).dot"></span>{{ st(t.status).text }}
                  </span>
                </td>
                <td class="mono">{{ (t.created_at || '').slice(0, 19) }}</td>
                <td class="mono">{{ (t.finished_at || '').slice(0, 19) }}</td>
                <!-- 备注列会被截断，完整文本放 title，否则失败原因看不全 -->
                <td class="muted truncate" :title="t.error">{{ t.error }}</td>
                <td class="actions">
                  <button v-if="['queued','running','cancel_requested'].includes(t.status)"
                          class="btn danger sm" @click="cancel(t.id)">取消</button>
                </td>
              </tr>
            </tbody>
          </table>
          </div>
        </template>

        <!-- 筛掉之后没有结果 ≠ 队列空了：两者要分开说 -->
        <p v-if="!loading && tasks.length && !sortedTasks.length" class="hint" style="margin-top:10px">
          当前筛选条件下没有任务（队列共 {{ tasks.length }} 条）。
        </p>
      </template>
    </div>
  </div>
</template>
