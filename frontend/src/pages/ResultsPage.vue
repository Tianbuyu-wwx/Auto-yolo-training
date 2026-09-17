<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, errMsg } from '../lib/api.js'
import { toastErr, toastOk } from '../lib/toast.js'
import EmptyState from '../components/EmptyState.vue'
import MetricCard from '../components/MetricCard.vue'

const runs = ref([])
const selected = ref('')
const results = ref(null)
// 产物去向：每个 run 的 best/last/results 是否还在、有没有数据集级导出件
// （后端 RunStore 的只读快照，随 /api/trainings/runs 一起下发）
const artifacts = ref({ runs: [], exports: {}, recycled_count: 0, recycle_dir: '' })
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
    artifacts.value = r.artifacts || { runs: [], exports: {}, recycled_count: 0, recycle_dir: '' }
    if (selectAfter && runs.value.includes(selectAfter)) selected.value = selectAfter
    if (!selected.value && runs.value.length) selected.value = runs.value[0]
    await loadResults()
  } catch (e) {
    // 不能退化成「暂无训练产物」——那是"跑过但没产物"，与"接口挂了"是两回事
    loadError.value = errMsg(e)
    runs.value = []; results.value = null
    artifacts.value = { runs: [], exports: {}, recycled_count: 0, recycle_dir: '' }
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

const artifact = computed(() => (artifacts.value.runs || []).find(a => a.run === selected.value) || null)
const exportInfo = computed(() => {
  const ds = artifact.value?.dataset
  return ds ? (artifacts.value.exports || {})[ds] || null : null
})
/**
 * best.pt 不在 run 内时要说清楚为什么、以及还能怎么办 —— 旧界面上这里只有一句
 * "无权重"，用户看到的是「明明训练成功了却说没有权重」。
 */
const weightsHint = computed(() => {
  if (!results.value || results.value.has_weights) return ''
  return exportInfo.value
    ? `本 run 的 best.pt 已不在原位。${exportInfo.value.path} 是该数据集最近一次训练的副本（不一定来自本 run）；要本 run 的权重可从回收站恢复或重新训练。`
    : '本 run 的 best.pt 已不在原位，也没有数据集级副本；需要权重请重新训练该数据集。'
})
</script>

<template>
  <div>
    <div v-if="loadError" class="state-msg error">
      训练记录加载失败：{{ loadError }}
      <div class="retry"><button class="btn sm" @click="refreshRuns()">重试</button></div>
    </div>

    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
      <select v-model="selected" style="max-width:280px" :disabled="loading || !runs.length" @change="loadResults">
        <option value="" disabled>{{ loading ? '加载中…' : runs.length ? '— 选择 run —' : '暂无 run' }}</option>
        <option v-for="r in runs" :key="r" :value="r">{{ r }}</option>
      </select>
      <span v-if="!loading && !loadError" class="hint">共 {{ runs.length }} 个 run</span>
    </div>

    <!-- 加载中：用骨架占住最终布局，数据到达只是"变清楚"，不是"跳一下" -->
    <div v-if="loading" class="grid c4" style="margin-bottom:16px">
      <div v-for="i in 4" :key="i" class="metric">
        <div class="sk sk-line w60" style="margin:0 0 4px"></div>
        <div class="sk sk-value"></div>
      </div>
    </div>

    <template v-if="results">
      <div class="grid c4" style="margin-bottom:16px">
        <MetricCard :value="fmt4(results.final_metrics?.mAP50)" :label="(results.metric_labels || ['mAP@50'])[0]" tone="green" />
        <MetricCard :value="fmt4(results.final_metrics?.mAP50_95)" :label="(results.metric_labels || ['mAP@50', 'mAP@50-95'])[1]" tone="green" />
        <MetricCard :value="results.final_metrics?.epoch ?? '—'" label="Best Epoch" tone="amber" />
        <MetricCard :value="results.has_weights ? '可下载' : '无权重'" label="best.pt" tone="blue" />
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
        <h3>产物去向</h3>
        <table v-if="artifact" class="tbl">
          <thead><tr><th>产物</th><th>状态</th><th>说明</th></tr></thead>
          <tbody>
            <tr>
              <td>best.pt</td>
              <td><span class="badge" :class="artifact.has_best ? 'ok' : 'idle'">{{ artifact.has_best ? '在 run 内' : '不在 run 内' }}</span></td>
              <td class="muted">{{ artifact.has_best ? '下载 / 导出 / 按 run 注册读的就是它' : (exportInfo ? '可用数据集级副本兜底' : '无任何副本') }}</td>
            </tr>
            <tr>
              <td>last.pt（断点）</td>
              <td><span class="badge" :class="artifact.has_last ? 'ok' : 'idle'">{{ artifact.has_last ? '可续训' : '缺' }}</span></td>
              <td class="muted">{{ artifact.has_last ? '「训练配置 → 断点续训」可从本 run 恢复' : '本 run 不能续训' }}</td>
            </tr>
            <tr>
              <td>results.csv</td>
              <td><span class="badge" :class="artifact.has_results ? 'ok' : 'idle'">{{ artifact.has_results ? '有' : '无' }}</span></td>
              <td class="muted">逐 epoch 指标与曲线图的来源</td>
            </tr>
            <tr>
              <td>导出件</td>
              <td><span class="badge" :class="exportInfo ? 'ok' : 'idle'">{{ exportInfo ? '有' : '无' }}</span></td>
              <td class="muted">{{ exportInfo ? `${exportInfo.path} · ${exportInfo.size_mb} MB · ${exportInfo.modified}` : '训练完成时自动归档为 exports/&lt;数据集&gt;.pt' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="artifact" class="muted" style="font-size:12.5px;margin:10px 0 0">
          run 目录 <code class="mono">{{ artifact.path }}</code> · {{ artifact.size_mb }} MB · {{ artifact.modified }}
          <template v-if="artifacts.recycled_count">
            <br />回收站有 {{ artifacts.recycled_count }} 项可恢复（<code class="mono">{{ artifacts.recycle_dir }}</code>）
          </template>
        </p>
        <p v-else class="muted" style="font-size:12.5px">该 run 无产物记录（可能已被回收）。</p>
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
        <p v-if="weightsHint" class="muted" style="font-size:12.5px;margin:10px 0 0">{{ weightsHint }}</p>
      </div>
    </template>

    <div v-else-if="!loading && !loadError" class="card" style="margin-bottom:16px">
      <EmptyState v-if="!runs.length" glyph="▥" title="暂无训练产物，先去「训练配置」启动一次训练。"
                  hint="训练结束后这里会列出每个 run 的指标、曲线、产物去向与导出入口；CPU 上跑一次 make smoke 也能生成一个可看的 run。">
        <router-link class="btn sm" to="/train/config">去配置训练</router-link>
      </EmptyState>
      <EmptyState v-else glyph="▥" title="该 run 无训练产物，换一个 run 试试。"
                  hint="当前 run 可能只是评估目录，或产物已被回收 —— 回收站里的记录见下方「产物去向」。" />
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
