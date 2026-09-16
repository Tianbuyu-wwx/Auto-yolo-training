<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api, errMsg } from '../lib/api.js'

const tasks = ref([])
const error = ref('')
const msg = ref('')
let timer = null

const ICONS = { queued: '🟡', running: '🟢', done: '✅', failed: '❌', cancelled: '⛔', cancel_requested: '🟠' }

async function refresh() {
  try {
    tasks.value = (await api.get('/api/queue/tasks')).tasks
    error.value = ''
  } catch (e) { error.value = errMsg(e) }
}

async function cancel(id) {
  try {
    await api.post(`/api/queue/${id}/cancel`)
    msg.value = `任务 #${id} 已取消`
  } catch (e) { msg.value = errMsg(e) }
  await refresh()
}

onMounted(() => { refresh(); timer = setInterval(refresh, 5000) })
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div>
    <h1 class="page-title">任务队列</h1>
    <p class="muted" style="margin-bottom:16px;font-size:13px">
      任务持久化到 SQLite，Web 重启不丢失；由队列按顺序执行，训练在独立子进程运行。
      在「训练配置」页点击「加入队列」提交任务。
    </p>

    <div class="card">
      <table class="tbl">
        <thead>
          <tr><th>#</th><th>数据集</th><th>模型</th><th>状态</th><th>创建时间</th><th>结束时间</th><th>备注</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="t in tasks" :key="t.id">
            <td class="mono">{{ t.id }}</td>
            <td>{{ t.dataset_name }}</td>
            <td class="mono">{{ t.config?.model }}</td>
            <td><span class="badge" :class="t.status === 'done' ? 'ok' : ['failed'].includes(t.status) ? 'err' : ['queued','running'].includes(t.status) ? 'warn' : 'idle'">
              {{ ICONS[t.status] || '·' }} {{ t.status }}</span></td>
            <td class="mono">{{ (t.created_at || '').slice(0, 19) }}</td>
            <td class="mono">{{ (t.finished_at || '').slice(0, 19) }}</td>
            <td class="muted" style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ t.error }}</td>
            <td>
              <button v-if="['queued','running','cancel_requested'].includes(t.status)"
                      class="btn danger sm" @click="cancel(t.id)">取消</button>
            </td>
          </tr>
          <tr v-if="!tasks.length"><td colspan="8" class="muted">队列为空</td></tr>
        </tbody>
      </table>
      <p v-if="msg" class="muted" style="margin-top:10px;font-size:12.5px">{{ msg }}</p>
      <p v-if="error" class="error-text">{{ error }}</p>
    </div>
  </div>
</template>
