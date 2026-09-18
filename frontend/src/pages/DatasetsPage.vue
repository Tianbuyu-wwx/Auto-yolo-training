<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, errMsg } from '../lib/api.js'
import { useSort } from '../lib/table.js'
import Drawer from '../components/Drawer.vue'
import EmptyState from '../components/EmptyState.vue'
import ImageLightbox from '../components/ImageLightbox.vue'
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

/** 表头排序：名称 / 图像 / 标注 / 状态（按可训练性）。问题列不排 —— 它是自由文本。 */
const { sorted: sortedStatuses, sortKey, toggle: toggleSort, indicator: sortInd, ariaSort } =
  useSort(visibleStatuses, { initial: 'name' })

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
/** 抽屉里要按名字查告警（表格里是整行传进来，抽屉只有名字） */
const issuesFor = (name) => statuses.value.find((x) => x.name === name)?.issues || []
const issueCountFor = (name) => issuesFor(name).length

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

/** 详情抽屉：点行打开；关闭后保留选中（转换/删除仍作用于它） */
const drawerOpen = ref(false)
const lightbox = ref(-1)

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
    drawerOpen.value = true
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
            <label style="display:flex;gap:8px;align-items:center;font-size:12px;color:var(--text-muted)">
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
          <label style="display:flex;gap:8px;align-items:center;font-size:12px;color:var(--text-muted);margin-bottom:10px">
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
            <span class="hint" style="margin:0">点任意一行查看详情与样本</span>
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
            <table class="tbl fixed">
              <!-- 固定列宽：数据变化（筛选/加载完成）时列不再跟着内容重排 -->
              <colgroup>
                <col style="width:20%" /><col style="width:11%" /><col style="width:9%" />
                <col style="width:9%" /><col style="width:15%" /><col style="width:36%" />
              </colgroup>
              <thead>
                <tr>
                  <th class="sortable" :class="{ sorted: sortKey === 'name' }" :aria-sort="ariaSort('name')" @click="toggleSort('name')">名称<span class="ind">{{ sortInd('name') }}</span></th>
                  <th>格式</th>
                  <th class="sortable" :class="{ sorted: sortKey === 'image_count' }" :aria-sort="ariaSort('image_count')" @click="toggleSort('image_count')">图像<span class="ind">{{ sortInd('image_count') }}</span></th>
                  <th class="sortable" :class="{ sorted: sortKey === 'label_count' }" :aria-sort="ariaSort('label_count')" @click="toggleSort('label_count')">标注<span class="ind">{{ sortInd('label_count') }}</span></th>
                  <th class="sortable" :class="{ sorted: sortKey === 'is_trainable' }" :aria-sort="ariaSort('is_trainable')" @click="toggleSort('is_trainable')">状态<span class="ind">{{ sortInd('is_trainable') }}</span></th>
                  <th>问题</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in sortedStatuses" :key="s.name" style="cursor:pointer" @click="selectDataset(s.name)">
                  <td :title="s.name"><code class="row-link" :style="s.name === selected ? 'color:var(--blue)' : ''">{{ s.name }}</code></td>
                  <td>{{ s.format }}</td>
                  <td class="mono">{{ s.image_count }}</td>
                  <td class="mono">{{ s.label_count }}</td>
                  <td><span class="badge" :class="badge(s).cls">{{ badge(s).text }}</span></td>
                  <!-- 告警不截断：后端早就在返回 issues，只是模板从未渲染它。
                       data 数据集 image=371 / label=296（val 集 75/75 张无标注），
                       旧界面 6 行全绿「就绪」，用户会拿坏数据训练并相信产出的 mAP。 -->
                  <td class="issue-cell wrap">
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

        <!-- 详情抽屉：把"当前选中"从页面流里提出来（原先挂在列表下方，会推走回收站） -->
        <Drawer v-if="drawerOpen && selected" :title="selected"
                :subtitle="info ? `${info.format || ''} · ${info.splits ? Object.keys(info.splits).length : 0} 个划分` : '读取详情中…'"
                @close="drawerOpen = false">
          <div v-if="!info" style="display:flex;flex-direction:column;gap:10px">
            <Skeleton variant="row" :count="4" />
          </div>
          <template v-else>
            <!-- 事实条：先给结论，再给明细 -->
            <div class="exec-summary" style="margin-bottom:14px">
              <span class="mono">{{ info.image_count ?? '—' }} 图</span>
              <span class="sep">·</span><span class="mono">{{ info.label_count ?? '—' }} 标注</span>
              <span class="sep">·</span><span class="mono">{{ info.format || '未知格式' }}</span>
              <span class="sep">·</span>
              <span v-if="issueCountFor(selected)" class="badge warn">{{ issueCountFor(selected) }} 项告警</span>
              <span v-else class="badge ok">无告警</span>
            </div>

            <p v-if="issuesFor(selected).length" class="hint" style="color:var(--amber);margin:0 0 14px">
              {{ issuesFor(selected).join('；') }}
            </p>

            <h4 class="drawer-h">划分明细</h4>
            <table class="tbl" style="margin-bottom:16px">
              <thead><tr><th>划分</th><th>图像</th><th>标注</th><th>缺失</th></tr></thead>
              <tbody>
                <tr v-for="(sp, split) in info.splits" :key="split">
                  <td>{{ split }}</td>
                  <td class="mono">{{ sp.images }}</td>
                  <td class="mono">{{ sp.labels }}</td>
                  <td class="mono" :style="sp.labels < sp.images ? 'color:var(--amber)' : ''">
                    {{ sp.labels < sp.images ? sp.images - sp.labels : '—' }}
                  </td>
                </tr>
              </tbody>
            </table>

            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
              <h4 class="drawer-h" style="margin:0">样本预览</h4>
              <label style="display:flex;gap:6px;align-items:center;font-size:12px;color:var(--text-muted)">
                <input type="checkbox" v-model="showBoxes" style="width:auto" @change="loadPreviews" />
                显示标注框
              </label>
            </div>
            <div class="gallery" v-if="previews.length">
              <button v-for="(p, i) in previews" :key="p" class="thumb" type="button"
                      :aria-label="`放大查看样本 ${i + 1}`" @click="lightbox = i">
                <img :src="p" alt="样本" loading="lazy" />
              </button>
            </div>
            <p v-else class="muted" style="font-size:12px">无预览图像（该数据集没有可读的图片或尚未转换）</p>

            <div style="margin-top:16px;display:flex;gap:10px;align-items:center">
              <button class="btn primary" :disabled="validating || !selected" @click="onValidate">
                {{ validating ? '校验中…' : '校验数据集' }}
              </button>
              <span class="hint" style="margin:0">校验会逐张检查图片与标注配对</span>
            </div>
            <pre v-if="validateMsg" class="data-block"
                 :style="{ marginTop: '10px', color: validateOk ? 'var(--text)' : 'var(--red)' }">{{ validateMsg }}</pre>
          </template>
        </Drawer>

        <ImageLightbox v-if="lightbox >= 0 && previews.length"
                       :images="previews" :index="lightbox" @close="lightbox = -1" />

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
          <p v-else class="muted" style="font-size:12px">
            回收站是空的。删除的数据集会出现在这里，可随时恢复。
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
