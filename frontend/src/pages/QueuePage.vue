<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api, errMsg } from '../lib/api.js'
import EmptyState from '../components/EmptyState.vue'
import Skeleton from '../components/Skeleton.vue'
import { toastErr, toastOk } from '../lib/toast.js'

const tasks = ref([])
const error = ref('')
const loading = ref(true)
let timer = null

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

        <div v-else class="table-wrap">
          <table class="tbl">
            <thead>
              <tr><th>#</th><th>数据集</th><th>模型</th><th>状态</th><th>创建时间</th><th>结束时间</th><th>备注</th><th></th></tr>
            </thead>
            <tbody>
              <tr v-for="t in tasks" :key="t.id">
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
                <td>
                  <button v-if="['queued','running','cancel_requested'].includes(t.status)"
                          class="btn danger sm" @click="cancel(t.id)">取消</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>
  </div>
</template>
