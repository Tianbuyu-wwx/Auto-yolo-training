<script setup>
/**
 * 模型注册中心（G-4）
 *
 * 后端 ModelRegistry 早就有 register / promote / 打标 / 对比 / 删除，
 * 但此前只暴露了一个只读列表 —— 这个页面把写操作接出来。
 *
 * 两处刻意的处理：
 * 1. 删除是两段式确认，且生产版本由后端 409 拦下（删掉它 get_production_model
 *    会静默变 None，调用方无从察觉）。
 * 2. 注册时不要求用户手抄 mAP：留空则由后端从该 run 的 results.csv 取最终指标，
 *    页面上明确标出指标是「自动取的」还是「没有」——不编造数字。
 */
import { computed, onMounted, ref } from 'vue'
import { api, errMsg } from '../lib/api.js'
import EmptyState from '../components/EmptyState.vue'
import { toastErr, toastOk } from '../lib/toast.js'

const registry = ref({})        // { 数据集: [版本, ...] }
const selectedDs = ref('')
const runs = ref([])
const runDataset = ref({})      // run → 数据集（借 checkpoint_details 反推）
const loading = ref(true)
const loadError = ref('')
const busy = ref('')

const showRegister = ref(false)
const form = ref({ run_name: '', weights: 'best', dataset_name: '', description: '', tags: '' })
const copyModel = ref(false)

const tagEdit = ref('')         // 正在加标签的 version_id
const tagDraft = ref('')
const confirmDel = ref('')      // 待二次确认删除的 version_id
const picked = ref([])          // 勾选用于对比的 version_id（≤2）
const cmp = ref(null)

const datasetNames = computed(() => Object.keys(registry.value).sort())
const versions = computed(() => registry.value[selectedDs.value] || [])
const production = computed(() => versions.value.find(v => v.status === 'production') || null)
const pickedCount = computed(() => picked.value.filter(id => versions.value.some(v => v.version_id === id)).length)
const cmpA = computed(() => picked.value[0] || '')
const cmpB = computed(() => picked.value[1] || '')

const SHORT = 14
const shortId = (id) => (id.length > SHORT ? `${id.slice(0, SHORT)}…` : id)
const fmt4 = (v) => (v == null ? '—' : Number(v).toFixed(4))
const fmtTime = (s) => (s ? String(s).replace('T', ' ').slice(0, 16) : '—')
const toneOf = (s) => (s === 'production' ? 'ok' : s === 'archived' ? 'idle' : 'warn')
const modeOf = (p) => {
  const v = String(p || '').replace(/\\/g, '/')
  const i = v.indexOf('model_registry/models/')
  return i >= 0 ? `注册表副本 · ${v.slice(i + 'model_registry/models/'.length)}` : v
}

async function load(keepDs = true) {
  loading.value = true
  loadError.value = ''
  try {
    registry.value = (await api.get('/api/registry')).datasets || {}
    const names = Object.keys(registry.value).sort()
    if (!keepDs || !selectedDs.value || !registry.value[selectedDs.value]) {
      selectedDs.value = names[0] || ''
    }
    picked.value = picked.value.filter(id => versions.value.some(v => v.version_id === id))
    cmp.value = null
  } catch (e) {
    // 「接口挂了」和「还没有注册版本」是两回事，不能都渲染成空态
    loadError.value = errMsg(e)
    registry.value = {}
  } finally {
    loading.value = false
  }
}

async function loadRuns() {
  try {
    const r = await api.get('/api/trainings/runs')
    runs.value = r.runs || []
    const map = {}
    for (const d of r.checkpoint_details || []) if (d.run) map[d.run] = d.dataset
    runDataset.value = map
  } catch { /* 注册表单允许手填 run，取不到列表不致命 */ }
}

function onRunChange() {
  const ds = runDataset.value[form.value.run_name]
  if (ds && !form.value.dataset_name.trim()) form.value.dataset_name = ds
}

async function doRegister() {
  const f = form.value
  if (!f.run_name) return toastErr('请选择要注册的 run')
  if (!f.dataset_name.trim()) return toastErr('请填写数据集名称')
  busy.value = 'register'
  try {
    const r = await api.post('/api/registry/register', {
      dataset_name: f.dataset_name.trim(),
      run_name: f.run_name,
      weights: f.weights,
      description: f.description,
      copy_model: copyModel.value,
      tags: f.tags.split(',').map(t => t.trim()).filter(Boolean),
    })
    const m = r.version.metrics || {}
    const where = r.metrics_auto_filled
      ? `指标取自 results.csv（mAP@50 ${fmt4(m.mAP50)}）`
      : r.metrics_source === 'request' ? '指标来自请求' : '该 run 无 results.csv，未记录指标'
    toastOk(`已注册 ${r.version.version_id} · ${where}`)
    showRegister.value = false
    form.value = { run_name: '', weights: 'best', dataset_name: '', description: '', tags: '' }
    copyModel.value = false
    selectedDs.value = r.version.dataset_name
    await load()
  } catch (e) {
    toastErr(errMsg(e))
  } finally {
    busy.value = ''
  }
}

async function act(v, action, label, payload) {
  busy.value = v.version_id
  try {
    const base = `/api/registry/${encodeURIComponent(selectedDs.value)}/${encodeURIComponent(v.version_id)}/${action}`
    // payload 必须显式传：/status 端点要求请求体，post(url) 不带体会被 FastAPI 判 422
    await api.post(base, payload)
    toastOk(`${shortId(v.version_id)} ${label}完成`)
    await load()
  } catch (e) {
    toastErr(errMsg(e))
  } finally {
    busy.value = ''
  }
}

async function doDelete(v) {
  busy.value = v.version_id
  try {
    const r = await api.del(`/api/registry/${encodeURIComponent(selectedDs.value)}/${encodeURIComponent(v.version_id)}`)
    toastOk(r.deleted_registry_copy
      ? `已删除 ${shortId(v.version_id)}（注册表内的副本已移除，原位权重保留）`
      : `已删除 ${shortId(v.version_id)}（注册记录，runs/ 下权重未动）`)
    confirmDel.value = ''
    await load()
  } catch (e) {
    toastErr(errMsg(e))
  } finally {
    busy.value = ''
  }
}

async function submitTags(v) {
  const tags = tagDraft.value.split(',').map(t => t.trim()).filter(Boolean)
  if (!tags.length) return toastErr('请输入标签，多个用逗号分隔')
  busy.value = v.version_id
  try {
    const r = await api.post(`/api/registry/${encodeURIComponent(selectedDs.value)}/${encodeURIComponent(v.version_id)}/tags`, { tags })
    toastOk(`标签已更新：${r.tags.join(', ')}`)
    tagEdit.value = ''
    tagDraft.value = ''
    await load()
  } catch (e) {
    toastErr(errMsg(e))
  } finally {
    busy.value = ''
  }
}

function togglePick(v) {
  const i = picked.value.indexOf(v.version_id)
  if (i >= 0) picked.value.splice(i, 1)
  else if (picked.value.length < 2) picked.value.push(v.version_id)
  else toastErr('最多同时对比两个版本')
}

async function doCompare() {
  if (picked.value.length !== 2) return toastErr('请勾选两个版本')
  busy.value = 'compare'
  try {
    cmp.value = await api.get(
      `/api/registry/${encodeURIComponent(selectedDs.value)}/compare`
      + `?a=${encodeURIComponent(cmpA.value)}&b=${encodeURIComponent(cmpB.value)}`)
  } catch (e) {
    toastErr(errMsg(e))
    cmp.value = null
  } finally {
    busy.value = ''
  }
}

onMounted(async () => {
  await load(false)
  loadRuns().catch(() => {})
})
</script>

<template>
  <div>
    <div v-if="loadError" class="state-msg error">
      注册表加载失败：{{ loadError }}
      <div class="retry"><button class="btn sm" @click="load(false)">重试</button></div>
    </div>

    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">
      <select v-model="selectedDs" style="max-width:280px" :disabled="loading || !datasetNames.length"
              @change="picked = []; cmp = null">
        <option value="" disabled>{{ loading ? '加载中…' : datasetNames.length ? '— 选择数据集 —' : '暂无注册版本' }}</option>
        <option v-for="ds in datasetNames" :key="ds" :value="ds">
          {{ ds }}（{{ registry[ds].length }} 个版本）
        </option>
      </select>
      <span v-if="!loading && !loadError" class="hint">
        {{ datasetNames.length }} 个数据集 · {{ datasetNames.reduce((n, d) => n + registry[d].length, 0) }} 个版本
      </span>
      <div style="flex:1"></div>
      <button class="btn" :disabled="loading" @click="showRegister = !showRegister">
        {{ showRegister ? '收起注册表单' : '＋ 注册新版本' }}
      </button>
    </div>

    <!-- 注册：权重来源只允许 run 派生或白名单内的 model_path，避免把任意路径写进注册表 -->
    <div v-if="showRegister" class="card" style="margin-bottom:16px">
      <h3>注册新版本</h3>
      <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px">
        <label>
          <span class="hint">来源 run</span>
          <select v-model="form.run_name" @change="onRunChange">
            <option value="" disabled>{{ runs.length ? '— 选择 run —' : '暂无 run' }}</option>
            <option v-for="r in runs" :key="r" :value="r">{{ r }}</option>
          </select>
        </label>
        <label>
          <span class="hint">权重</span>
          <select v-model="form.weights">
            <option value="best">best.pt（验证集最优）</option>
            <option value="last">last.pt（最后一轮）</option>
          </select>
        </label>
        <label>
          <span class="hint">数据集名称</span>
          <input v-model="form.dataset_name" placeholder="如 my-dataset" />
          <span v-if="runDataset[form.run_name]" class="hint">
            自动带出：{{ runDataset[form.run_name] }}
          </span>
        </label>
        <label>
          <span class="hint">标签（逗号分隔，可留空）</span>
          <input v-model="form.tags" placeholder="如 baseline, v2-aug" />
        </label>
        <label style="grid-column:1 / -1">
          <span class="hint">描述（可留空）</span>
          <input v-model="form.description" placeholder="这次注册的版本是做什么的" />
        </label>
      </div>

      <div class="row-check" style="margin-top:12px">
        <input id="reg-copy" v-model="copyModel" type="checkbox" />
        <label for="reg-copy" class="hint">
          复制权重到注册表（默认关）—— 开启后把 .pt 再存一份到
          <code>model_registry/models/</code>，代价是占额外磁盘；
          好处是训练目录被自动清理后注册版本仍然可用。
        </label>
      </div>

      <div style="display:flex;gap:10px;align-items:center;margin-top:14px">
        <button class="btn primary" :disabled="busy === 'register'" @click="doRegister">
          {{ busy === 'register' ? '注册中…' : '注册' }}
        </button>
        <span class="hint">指标留空则自动从该 run 的 <code>results.csv</code> 取最终 mAP。</span>
      </div>
    </div>

    <template v-if="!loadError && datasetNames.length">
      <!-- 生产版本是调用方真正要取的东西，单独提到最上面 -->
      <div class="card" style="margin-bottom:16px">
        <h3>当前生产版本</h3>
        <template v-if="production">
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
            <span class="badge ok">production</span>
            <code class="mono">{{ production.version_id }}</code>
            <span class="hint">mAP@50 {{ fmt4(production.metrics?.mAP50) }} · {{ fmtTime(production.created_at) }}</span>
          </div>
          <p class="hint" style="margin-top:8px">
            权重：<code>{{ modeOf(production.model_path) }}</code>
          </p>
          <p v-if="production.weights_missing" class="hint danger" style="margin-top:6px">
            该生产版本的权重文件已不在磁盘上（训练产物被滚动清理）——调用方拿到路径也加载不了。
            请注册一个可用版本并重新「设为生产」。
          </p>
        </template>
        <p v-else class="muted" style="font-size:12.5px">
          该数据集还没有生产版本 —— 在下方任选一个版本「设为生产」。
        </p>
      </div>

      <div class="card" style="margin-bottom:16px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;gap:12px">
          <h3 style="margin:0">{{ selectedDs }} 的版本（{{ versions.length }}）</h3>
          <button class="btn sm" :disabled="pickedCount !== 2 || busy === 'compare'" @click="doCompare">
            {{ busy === 'compare' ? '对比中…' : `对比勾选的两个版本（${pickedCount}/2）` }}
          </button>
        </div>

        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr>
                <th style="width:34px">选</th>
                <th>版本</th>
                <th>mAP@50</th>
                <th>mAP@50-95</th>
                <th>状态</th>
                <th>标签</th>
                <th>创建时间</th>
                <th style="width:260px">操作</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="v in versions" :key="v.version_id">
                <tr>
                  <td>
                    <input type="checkbox" style="width:auto"
                           :checked="picked.includes(v.version_id)" @change="togglePick(v)" />
                  </td>
                  <td>
                    <div class="mono" :title="v.version_id">{{ shortId(v.version_id) }}</div>
                    <div class="hint truncate" :title="v.model_path">{{ modeOf(v.model_path) }}</div>
                    <!-- 记录在、权重没了：训练产物被滚动清理后 copy_model=false 的版本
                         就是这个状态，不标出来调用方会拿着死路径去加载 -->
                    <div
                      v-if="v.weights_missing"
                      class="hint danger"
                      title="训练产物被清理后注册记录仍保留，但权重文件已不在磁盘上"
                    >
                      权重已丢失
                    </div>
                  </td>
                  <td class="mono">{{ fmt4(v.metrics?.mAP50) }}</td>
                  <td class="mono">{{ fmt4(v.metrics?.mAP50_95) }}</td>
                  <td><span class="badge" :class="toneOf(v.status)">{{ v.status }}</span></td>
                  <td>
                    <template v-if="v.tags?.length">
                      <span v-for="t in v.tags" :key="t" class="badge idle" style="margin:1px 2px 1px 0">{{ t }}</span>
                    </template>
                    <span v-else class="muted">—</span>
                  </td>
                  <td class="mono">{{ fmtTime(v.created_at) }}</td>
                  <td>
                    <div style="display:flex;gap:6px;flex-wrap:wrap">
                      <button class="btn sm"
                              :disabled="busy === v.version_id || v.status === 'production' || v.weights_missing"
                              :title="v.weights_missing ? '权重文件已丢失，设为生产只会得到一个加载不了的路径' : ''"
                              @click="act(v, 'promote', '设为生产')">设为生产</button>
                      <button class="btn sm" :disabled="busy === v.version_id || v.status === 'archived'"
                              @click="act(v, 'status', '归档', { status: 'archived' })">归档</button>
                      <button class="btn sm" :disabled="busy === v.version_id"
                              @click="tagEdit = tagEdit === v.version_id ? '' : v.version_id; tagDraft = ''">标签</button>
                      <template v-if="confirmDel === v.version_id">
                        <button class="btn sm danger" :disabled="busy === v.version_id" @click="doDelete(v)">
                          确认删除
                        </button>
                        <button class="btn sm" @click="confirmDel = ''">取消</button>
                      </template>
                      <button v-else class="btn sm danger" :disabled="busy === v.version_id || v.status === 'production'"
                              :title="v.status === 'production' ? '生产版本不能删除，请先归档或另指定生产版本' : ''"
                              @click="confirmDel = v.version_id">删除</button>
                    </div>
                  </td>
                </tr>
                <!-- 标签是「只增」的：去重由后端做，这里只负责提交 -->
                <tr v-if="tagEdit === v.version_id">
                  <td colspan="8" style="background:rgba(255,255,255,.02)">
                    <div style="display:flex;gap:8px;align-items:center">
                      <input v-model="tagDraft" style="max-width:340px" placeholder="追加标签，逗号分隔（已有的会自动去重）"
                             @keyup.enter="submitTags(v)" />
                      <button class="btn sm primary" :disabled="busy === v.version_id" @click="submitTags(v)">添加</button>
                      <span class="hint">标签只增不减，用于给自己留线索。</span>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="cmp" class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <h3 style="margin:0">版本对比</h3>
          <button class="btn sm" @click="cmp = null">收起</button>
        </div>
        <p class="hint" style="margin-bottom:10px">
          差值 = 后者 − 前者。mAP 越高越好，因此正数是变好。
        </p>
        <table class="tbl">
          <thead>
            <tr>
              <th>指标</th>
              <th>{{ shortId(cmp.version1) }}</th>
              <th>{{ shortId(cmp.version2) }}</th>
              <th>差值</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(d, k) in cmp.metrics_diff" :key="k">
              <td>{{ k }}</td>
              <td class="mono">{{ fmt4(d.v1) }}</td>
              <td class="mono">{{ fmt4(d.v2) }}</td>
              <td class="mono" :style="{ color: d.diff >= 0 ? 'var(--green)' : 'var(--red)' }">
                {{ d.diff >= 0 ? '+' : '' }}{{ fmt4(d.diff) }}
              </td>
            </tr>
            <tr v-if="!Object.keys(cmp.metrics_diff || {}).length">
              <td colspan="4" class="muted">两个版本都没有记录指标，无法对比。</td>
            </tr>
          </tbody>
        </table>
        <template v-if="Object.keys(cmp.params_diff || {}).length">
          <h3 style="margin:16px 0 10px">训练参数差异</h3>
          <table class="tbl">
            <thead><tr><th>参数</th><th>{{ shortId(cmp.version1) }}</th><th>{{ shortId(cmp.version2) }}</th></tr></thead>
            <tbody>
              <tr v-for="(p, k) in cmp.params_diff" :key="k">
                <td>{{ k }}</td>
                <td class="mono">{{ p.v1 }}</td>
                <td class="mono">{{ p.v2 }}</td>
              </tr>
            </tbody>
          </table>
        </template>
      </div>
    </template>

    <div v-else-if="!loading && !loadError" class="card">
      <EmptyState glyph="◈" title="注册表里还没有任何版本"
                  hint="训练完成会自动注册一个版本；也可以用上方「注册新版本」把已有的 run 补进来，再进行晋升 / 回滚。" />
    </div>
  </div>
</template>
