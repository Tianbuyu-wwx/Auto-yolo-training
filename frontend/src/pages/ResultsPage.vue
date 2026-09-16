<script setup>
import { onMounted, ref } from 'vue'
import { api, errMsg } from '../lib/api.js'
import { toastErr, toastOk } from '../lib/toast.js'

const runs = ref([])
const selected = ref('')
const results = ref(null)
const exportFmt = ref('onnx')
const exporting = ref(false)
const compareMd = ref('')
const registry = ref({})

const loading = ref(true)
const loadError = ref('')

async function refreshRuns(selectAfter) {
  loading.value = true
  loadError.value = ''
  try {
    const r = await api.get('/api/trainings/runs')
    runs.value = r.runs
    if (selectAfter && runs.value.includes(selectAfter)) selected.value = selectAfter
    if (!selected.value && runs.value.length) selected.value = runs.value[0]
    await loadResults()
  } catch (e) {
    // 不能退化成「暂无训练产物」——那是"跑过但没产物"，与"接口挂了"是两回事
    loadError.value = errMsg(e)
    runs.value = []; results.value = null
  } finally {
    loading.value = false
  }
}

async function loadResults() {
  results.value = null
  if (!selected.value) return
  try { results.value = await api.get(`/api/trainings/results?run=${encodeURIComponent(selected.value)}`) }
  catch { /* 该 run 无产物，由模板的空态承接 */ }
}

async function onExport() {
  exporting.value = true
  try {
    const r = await api.post('/api/exports', { run_name: selected.value, fmt: exportFmt.value })
    toastOk(`${r.format} 导出完成 → ${r.path}（${r.size_mb} MB）`)
  } catch (e) { toastErr(errMsg(e)) } finally { exporting.value = false }
}

async function loadCompare() {
  try { compareMd.value = (await api.get('/api/trainings/compare')).markdown }
  catch (e) { toastErr(errMsg(e)) }
}
async function loadRegistry() { registry.value = (await api.get('/api/registry')).datasets }

onMounted(async () => {
  await refreshRuns()
  loadRegistry().catch(() => {})
})

const fmt4 = (v) => (v == null ? '—' : Number(v).toFixed(4))
</script>

<template>
  <div>
    <p v-if="loadError" class="state-msg error">
      训练记录加载失败：{{ loadError }}
      <div class="retry"><button class="btn sm" @click="refreshRuns()">重试</button></div>
    </p>

    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
      <select v-model="selected" style="max-width:280px" :disabled="loading || !runs.length" @change="loadResults">
        <option value="" disabled>{{ loading ? '加载中…' : runs.length ? '— 选择 run —' : '暂无 run' }}</option>
        <option v-for="r in runs" :key="r" :value="r">{{ r }}</option>
      </select>
      <span v-if="!loading && !loadError" class="hint">共 {{ runs.length }} 个 run</span>
    </div>

    <template v-if="results">
      <div class="grid c4" style="margin-bottom:16px">
        <div class="metric">
          <div class="value green">{{ fmt4(results.final_metrics?.mAP50) }}</div>
          <div class="label">{{ (results.metric_labels || ['mAP@50'])[0] }}</div>
        </div>
        <div class="metric">
          <div class="value green">{{ fmt4(results.final_metrics?.mAP50_95) }}</div>
          <div class="label">{{ (results.metric_labels || ['mAP@50', 'mAP@50-95'])[1] }}</div>
        </div>
        <div class="metric">
          <div class="value amber">{{ results.final_metrics?.epoch ?? '—' }}</div>
          <div class="label">Best Epoch</div>
        </div>
        <div class="metric">
          <div class="value blue">{{ results.has_weights ? '可下载' : '无权重' }}</div>
          <div class="label">best.pt</div>
        </div>
      </div>

      <div class="card" style="margin-bottom:16px">
        <h3>结果图表</h3>
        <div class="gallery" v-if="results.plot_urls?.length">
          <a v-for="p in results.plot_urls" :key="p" :href="p" target="_blank">
            <img :src="p" loading="lazy" style="cursor:zoom-in" />
          </a>
        </div>
        <p v-else class="muted" style="font-size:12.5px">该 run 无结果图（训练可能未完成）</p>
      </div>

      <div class="card" style="margin-bottom:16px">
        <h3>模型操作</h3>
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          <code class="mono">{{ results.download_url ? `runs/detect/${results.run_name}/weights/best.pt` : '尚无 best.pt' }}</code>
          <div style="flex:1"></div>
          <select v-model="exportFmt" style="width:150px">
            <option v-for="f in ['onnx','torchscript','openvino','engine','coreml','tflite','saved_model','paddle','ncnn']"
                    :key="f" :value="f">{{ f }}</option>
          </select>
          <button class="btn primary" :disabled="!results.has_weights || exporting" @click="onExport">
            {{ exporting ? '导出中…' : '开始导出' }}
          </button>
          <a v-if="results.download_url" class="btn" :href="results.download_url">下载 best.pt</a>
        </div>
      </div>
    </template>

    <div v-else-if="!loading && !loadError" class="card muted" style="margin-bottom:16px">
      {{ runs.length ? '该 run 无训练产物，换一个 run 试试。' : '暂无训练产物，先去「训练配置」启动一次训练。' }}
    </div>

    <div class="grid c2">
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <h3 style="margin:0">训练对比</h3>
          <button class="btn sm" @click="loadCompare">生成对比</button>
        </div>
        <pre class="data-block">{{ compareMd || '点击「生成对比」查看最近 run 的最终指标' }}</pre>
      </div>

      <div class="card">
        <h3>ModelRegistry 版本记录</h3>
        <template v-if="Object.keys(registry).length">
          <details v-for="(versions, ds) in registry" :key="ds" style="margin-bottom:8px">
            <summary style="cursor:pointer;font-size:13px">{{ ds }}（{{ versions.length }} 个版本）</summary>
            <table class="tbl" style="margin-top:8px">
              <thead><tr><th>版本</th><th>mAP@50</th><th>状态</th></tr></thead>
              <tbody>
                <tr v-for="v in versions" :key="v.version_id">
                  <td class="mono">{{ v.version_id.slice(0, 12) }}</td>
                  <td class="mono">{{ fmt4(v.metrics?.mAP50) }}</td>
                  <td><span class="badge" :class="v.status === 'production' ? 'ok' : 'idle'">{{ v.status }}</span></td>
                </tr>
              </tbody>
            </table>
          </details>
        </template>
        <p v-else class="muted" style="font-size:12.5px">暂无注册版本（训练完成时自动注册）</p>
      </div>
    </div>
  </div>
</template>
