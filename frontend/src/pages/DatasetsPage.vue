<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, errMsg } from '../lib/api.js'
import EmptyState from '../components/EmptyState.vue'
import Skeleton from '../components/Skeleton.vue'
import { toastErr, toastOk } from '../lib/toast.js'

const datasets = ref([])        // 可训练（存在 data.yaml）——训练配置页的下拉就是它
const statuses = ref([])        // 磁盘上全部数据集目录（扫描级）
const selected = ref('')
const info = ref(null)
const previews = ref([])
const showBoxes = ref(false)

const loading = ref(true)
const loadError = ref('')

const validating = ref(false)
const validateMsg = ref('')
const validateOk = ref(true)

// 上传
const zipFile = ref(null)
const uploadName = ref('')
const overwrite = ref(false)
const uploading = ref(false)

// 转换
const deleteOriginal = ref(false)
const converting = ref(false)

// 删除 / 回收站
const confirmDel = ref('')      // 两段式确认：值为待删的数据集名
const busy = ref('')
const recycleItems = ref([])

const query = ref('')
/** 筛选后的视图列表。计数与表格都读它，避免「表头写 6 行、表格画 3 行」。 */
const visibleStatuses = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? statuses.value.filter(s => String(s.name).toLowerCase().includes(q)) : statuses.value
})

const pendingList = computed(() => statuses.value.filter(s => s.needs_conversion).map(s => s.name))
const notTrainable = computed(() => statuses.value.filter(s => !s.is_trainable).map(s => s.name))
const issueCount = computed(() => statuses.value.filter(s => s.issues?.length).length)

/**
 * 状态徽标必须按 is_trainable 判定，不能按 is_ready。
 *
 * is_ready 是扫描级（labels 目录存在且有标注文件），is_trainable 是训练级
 * （存在 data.yaml）。实测 _smoke_test / cabel-damage-mini 有完整标注但缺
 * data.yaml —— 旧代码把它们标成绿色「就绪」，用户转到训练配置页却在数据集
 * 下拉里找不到它们，没有任何解释。
 */
/**
 * 状态徽标。**必须与「问题」列一致**：`data` 数据集 val 集 75/75 张无标注，
 * is_trainable 却是 true —— 旧逻辑照样给出绿色「可训练」，与同行的黄色告警
 * 直接矛盾（用户会以为那只是提示，实际上训练会带着无标注的验证集跑）。
 */
function badge(s) {
  const issues = s.issues?.length || 0
  if (s.is_trainable) {
    return issues
      ? { cls: 'warn', text: `可训练 · ${issues} 项告警` }
      : { cls: 'ok', text: '可训练' }
  }
  if (s.is_ready) return { cls: 'warn', text: '缺 data.yaml' }
  if (s.needs_conversion) return { cls: 'warn', text: '需转换' }
  return { cls: 'err', text: '不可训练' }
}

async function refresh(selectAfter) {
  loading.value = true
  loadError.value = ''
  try {
    const data = await api.get('/api/datasets')
    datasets.value = data.datasets
    statuses.value = data.statuses
    if (selectAfter && datasets.value.includes(selectAfter)) selectDataset(selectAfter)
    else if (selected.value && !datasets.value.includes(selected.value)) {
      selected.value = ''; info.value = null; previews.value = []
    }
  } catch (e) {
    // 关键：失败不能退化成空态。否则接口挂了会显示「暂无数据集，请上传 ZIP」，
    // 与真的没有数据集完全同形，把用户引向错误的排查方向。
    loadError.value = errMsg(e)
    datasets.value = []; statuses.value = []
  } finally {
    loading.value = false
  }
}

async function selectDataset(name) {
  selected.value = name
  info.value = null; previews.value = []
  if (!name) return
  await loadInfo()
}

async function loadInfo() {
  try {
    info.value = await api.get(`/api/datasets/${encodeURIComponent(selected.value)}`)
    await loadPreviews()
  } catch (e) { validateMsg.value = errMsg(e); validateOk.value = false }
}

async function loadPreviews() {
  try {
    const data = await api.get(
      `/api/datasets/${encodeURIComponent(selected.value)}/preview?boxes=${showBoxes.value}`)
    previews.value = data.images
  } catch { previews.value = [] }
}

async function onUpload() {
  if (!zipFile.value) { toastErr('请先选择 ZIP 文件'); return }
  uploading.value = true
  const form = new FormData()
  form.append('file', zipFile.value)
  form.append('name', uploadName.value)
  form.append('overwrite', overwrite.value)
  try {
    const result = await api.postForm('/api/datasets/upload', form)
    toastOk(result.message)
    zipFile.value = null
    await refresh(result.dataset_name)
  } catch (e) {
    const text = errMsg(e)
    toastErr(text.includes('已存在') ? `${text}（可勾选「覆盖同名数据集」后重试）` : text)
  } finally {
    uploading.value = false
  }
}

async function onValidate() {
  validating.value = true
  try {
    const r = await api.post(`/api/datasets/${encodeURIComponent(selected.value)}/validate`)
    validateOk.value = r.is_valid
    validateMsg.value = r.message
    if (!r.is_valid) toastErr(`${selected.value} 校验未通过，详见下方报告`)
  } catch (e) {
    validateOk.value = false; validateMsg.value = errMsg(e); toastErr(errMsg(e))
  } finally {
    validating.value = false
  }
}

async function onConvert() {
  converting.value = true
  try {
    const r = await api.post(
      `/api/datasets/${encodeURIComponent(selected.value)}/convert?delete_original=${deleteOriginal.value}`)
    toastOk(r.message)
    await refresh(r.converted_name)
  } catch (e) { toastErr(errMsg(e)) } finally { converting.value = false }
}

async function loadRecycle() {
  try { recycleItems.value = (await api.get('/api/recycle')).items }
  catch { recycleItems.value = [] }   // 回收站读不到不影响主列表
}

async function onDelete() {
  busy.value = 'delete'
  try {
    const r = await api.del(`/api/datasets/${encodeURIComponent(selected.value)}`)
    toastOk(r.message)
    confirmDel.value = ''
    selected.value = ''; info.value = null; previews.value = []
    await refresh()
    await loadRecycle()
  } catch (e) {
    toastErr(errMsg(e))
  } finally {
    busy.value = ''
  }
}

async function onRestore(item) {
  busy.value = item.recycled_name
  try {
    const r = await api.post(`/api/recycle/${encodeURIComponent(item.recycled_name)}/restore`)
    toastOk(r.message)
    await refresh(r.restored_to ? item.original_name : '')
    await loadRecycle()
  } catch (e) {
    toastErr(errMsg(e))
  } finally {
    busy.value = ''
  }
}

onMounted(() => { refresh(); loadRecycle() })
</script>

<template>
  <div>
    <div class="split-2 side-340">
      <!-- 左侧：上传 / 转换 -->
      <div style="display:flex;flex-direction:column;gap:16px">
        <div class="card">
          <h3>上传数据集 (ZIP)</h3>
          <div style="display:flex;flex-direction:column;gap:10px">
            <input type="file" accept=".zip" @change="e => zipFile = e.target.files[0] || null" />
            <label class="field">数据集名称（留空使用文件名）
              <input v-model="uploadName" placeholder="my-dataset" />
            </label>
            <label style="display:flex;gap:8px;align-items:center;font-size:12.5px;color:var(--text-muted)">
              <input type="checkbox" v-model="overwrite" style="width:auto" />
              覆盖同名数据集（不勾选时同名将拒绝上传）
            </label>
            <button class="btn primary" :disabled="uploading" @click="onUpload">
              {{ uploading ? '上传中…' : '上传并解压' }}
            </button>
          </div>
        </div>

        <div class="card">
          <h3>格式转换（分类 → YOLO）</h3>
          <p v-if="pendingList.length" class="hint" style="color:var(--amber);margin-bottom:10px">
            待转换：{{ pendingList.join('、') }}
          </p>
          <p v-else class="hint" style="margin-bottom:10px">所有数据集均已具备 YOLO 结构</p>
          <label style="display:flex;gap:8px;align-items:center;font-size:12.5px;color:var(--text-muted);margin-bottom:10px">
            <input type="checkbox" v-model="deleteOriginal" style="width:auto" />
            转换后删除原始数据集（默认保留）
          </label>
          <button class="btn" :disabled="!selected || converting" @click="onConvert">
            {{ converting ? '转换中…' : '转换当前数据集' }}
          </button>
          <p class="hint" style="margin-top:8px">先在上方列表选中一个数据集</p>
        </div>

        <!-- 危险区：不可逆操作不该和上传/转换穿同一件衣服 -->
        <div class="card zone-danger">
          <h3>删除数据集</h3>
          <p class="hint" style="margin-bottom:10px">
            当前选中：<code>{{ selected || '（未选择）' }}</code>
          </p>
          <p class="hint" style="margin-bottom:12px">
            删除是移入回收目录 <code>dataset/.recycle/</code>，不是直接抹掉 ——
            删错了可以在右侧回收站里恢复。
          </p>
          <template v-if="confirmDel && confirmDel === selected">
            <div style="display:flex;gap:10px;align-items:center">
              <button class="btn danger" :disabled="busy === 'delete'" @click="onDelete">
                {{ busy === 'delete' ? '删除中…' : `确认删除「${selected}」` }}
              </button>
              <button class="btn" @click="confirmDel = ''">取消</button>
            </div>
          </template>
          <button v-else class="btn danger" :disabled="!selected || busy === 'delete'"
                  @click="confirmDel = selected">
            删除当前数据集
          </button>
          <p class="hint" style="margin-top:8px">训练进行中不允许删除。</p>
        </div>
      </div>

      <!-- 右侧：列表 + 详情 -->
      <div style="display:flex;flex-direction:column;gap:16px">
        <div class="card">
          <!-- 计数取 statuses（表格渲染的就是它，磁盘上全部目录）。
               datasets 只含可训练项（需有 data.yaml），两者口径不同：
               原用 datasets.length 导致表头写 4 而表格渲染 6 行。 -->
          <h3>数据集列表（{{ visibleStatuses.length }}<template v-if="query"> / {{ statuses.length }}</template>）</h3>

          <!-- 工具条：表格一多就得能筛。原先 6 个目录全铺开、没有任何入口，
               十来个数据集时只能靠肉眼扫「问题」列。 -->
          <div class="toolbar">
            <input v-model="query" type="search" placeholder="按名称筛选…" />
            <div class="spacer"></div>
            <span class="count">{{ visibleStatuses.length }} / {{ statuses.length }} 个目录</span>
          </div>

          <p v-if="!loading && !loadError && statuses.length" class="hint" style="margin:-6px 0 12px">
            共扫描 {{ statuses.length }} 个目录，其中 <strong>{{ datasets.length }}</strong> 个可训练
            <template v-if="notTrainable.length">，{{ notTrainable.length }} 个缺 data.yaml（不可选入训练）</template>
          </p>

          <div v-if="loading" style="padding:4px 0"><Skeleton variant="row" :count="5" /></div>

          <div v-else-if="loadError" class="state-msg error">
            数据集列表加载失败：{{ loadError }}
            <div class="retry"><button class="btn sm" @click="refresh()">重试</button></div>
          </div>

          <EmptyState v-else-if="!statuses.length" glyph="▤" title="还没有数据集"
                      hint="上传一个 ZIP（YOLO / 分类 / Roboflow 三种结构都能识别），或在项目根跑 make smoke 用内置烟雾数据跑通链路。" />

          <div v-else class="table-wrap">
            <table class="tbl">
              <thead>
                <tr><th>名称</th><th>格式</th><th>图像</th><th>标注</th><th>状态</th><th>问题</th></tr>
              </thead>
              <tbody>
                <tr v-for="s in visibleStatuses" :key="s.name" style="cursor:pointer" @click="selectDataset(s.name)">
                  <td><code :style="s.name === selected ? 'color:var(--blue)' : ''">{{ s.name }}</code></td>
                  <td>{{ s.format }}</td>
                  <td class="mono">{{ s.image_count }}</td>
                  <td class="mono">{{ s.label_count }}</td>
                  <td><span class="badge" :class="badge(s).cls">{{ badge(s).text }}</span></td>
                  <!-- 告警不截断：后端早就在返回 issues，只是模板从未渲染它。
                       data 数据集 image=371 / label=296（val 集 75/75 张无标注），
                       旧界面 6 行全绿「就绪」，用户会拿坏数据训练并相信产出的 mAP。 -->
                  <td class="issue-cell">
                    <span v-if="!s.issues || !s.issues.length" class="muted">—</span>
                    <span v-else class="issue-text">{{ s.issues.join('；') }}</span>
                  </td>
                </tr>
                <tr v-if="!visibleStatuses.length"><td colspan="6" class="muted">没有名称匹配「{{ query }}」的数据集</td></tr>
              </tbody>
            </table>
          </div>

          <!-- 列表之外的单条提示：告警只在一行里可见容易被略过 -->
          <p v-if="!loading && !loadError && issueCount" class="hint" style="color:var(--amber);margin-top:10px">
            {{ issueCount }} 个数据集的标注完整性存在问题，训练前请先核对「问题」列。
          </p>
        </div>

        <div class="card" v-if="info">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <h3 style="margin:0">{{ info.name }}</h3>
            <label style="display:flex;gap:6px;align-items:center;font-size:12.5px;color:var(--text-muted)">
              <input type="checkbox" v-model="showBoxes" style="width:auto" @change="loadPreviews" />
              预览显示标注框
            </label>
          </div>
          <table class="tbl" style="max-width:420px;margin-bottom:16px">
            <thead><tr><th>划分</th><th>图像</th><th>标注</th></tr></thead>
            <tbody>
              <tr v-for="(s, split) in info.splits" :key="split">
                <td>{{ split }}</td><td class="mono">{{ s.images }}</td><td class="mono">{{ s.labels }}</td>
              </tr>
            </tbody>
          </table>

          <h3>样本预览</h3>
          <div class="gallery" v-if="previews.length">
            <img v-for="p in previews" :key="p" :src="p" alt="样本" loading="lazy" />
          </div>
          <p v-else class="muted" style="font-size:12.5px">无预览图像</p>

          <div style="margin-top:16px;display:flex;gap:10px;align-items:center">
            <button class="btn primary" :disabled="validating || !selected" @click="onValidate">
              {{ validating ? '校验中…' : '校验数据集' }}
            </button>
          </div>
          <pre v-if="validateMsg" class="data-block"
               :style="{ marginTop: '10px', color: validateOk ? 'var(--text)' : 'var(--red)' }">{{ validateMsg }}</pre>
        </div>

        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <h3 style="margin:0">回收站（{{ recycleItems.length }}）</h3>
            <button class="btn sm" @click="loadRecycle">刷新</button>
          </div>
          <div v-if="recycleItems.length" class="table-wrap">
            <table class="tbl">
              <thead><tr><th>原名称</th><th>大小</th><th>删除时间</th><th style="width:80px"></th></tr></thead>
              <tbody>
                <tr v-for="it in recycleItems" :key="it.recycled_name">
                  <td><code>{{ it.original_name }}</code></td>
                  <td class="mono">{{ it.size_mb }} MB</td>
                  <td class="mono">{{ it.recycled_at }}</td>
                  <td>
                    <button class="btn sm" :disabled="busy === it.recycled_name" @click="onRestore(it)">
                      {{ busy === it.recycled_name ? '恢复中…' : '恢复' }}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="muted" style="font-size:12.5px">
            回收站是空的。删除的数据集会出现在这里，可随时恢复。
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
