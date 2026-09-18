<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, errMsg } from '../lib/api.js'
import { toastErr, toastOk } from '../lib/toast.js'

const router = useRouter()
const datasets = ref([])
const excluded = ref([])      // 扫描到但缺 data.yaml、因而无法选入训练的数据集
const models = ref([])
const checkpoints = ref([])   // 可续训断点（含数据集与进度，来自 checkpoint_details）
const task = ref('detect')
const busy = ref(false)
const loading = ref(true)
const loadError = ref('')

// 续训状态
const resumeOn = ref(false)
const resumePath = ref('')

const currentCkpt = computed(() => checkpoints.value.find(c => c.path === resumePath.value) || null)

// 续训时数据集必须与断点一致：管线在 resume 模式下仍以**当前** dataset_name 传 data=，
// 接错数据集不会报错，只会在别的数据上接着练。能从 args.yaml 反推时就把选择锁死。
const resumeDataset = computed(() =>
  (resumeOn.value && resumePath.value ? currentCkpt.value?.dataset || '' : ''))
const datasetLocked = computed(() => !!resumeDataset.value)
// datasets 即「可训练」集合：后端 list_datasets() 以 data.yaml 存在为判定，
// 与 is_trainable 同源（见 dataset_service.get_all_statuses 的口径说明）。
// 所以"不在 datasets 里"就等于"这个断点现在接不上"。
const resumeDatasetBad = computed(() =>
  !!resumeDataset.value && !datasets.value.includes(resumeDataset.value))

// 能反推出数据集却不能训练（缺 data.yaml）→ 必须挡住，否则会拿错数据起训
const resumeBlocked = computed(() => resumeOn.value
  && (!resumePath.value || resumeDatasetBad.value))

const canSubmit = computed(() => !busy.value && !!cfg.value.dataset_name
  && !resumeBlocked.value && errorCount.value === 0)

const PRESETS = {
  快速验证: { epochs: 50, batch: 16, imgsz: 416, patience: 10, lr0: 0.002 },
  标准训练: { epochs: 150, batch: 16, imgsz: 640, patience: 30, lr0: 0.001 },
  精细调优: { epochs: 300, batch: 8, imgsz: 640, patience: 50, lr0: 0.0005 },
}
const preset = ref('标准训练')
/** 高级组的展开状态。默认收起，但收起时显示取值摘要（见 groupDigest） */
const openGroups = ref({ reg: false, loss: false, aug: false })

// 表单配置（字段名与后端 StartTrainingRequest 严格对齐）
const cfg = ref({
  task: 'detect', model: 'yolov8s.pt', epochs: 150, imgsz: 640, batch: 16,
  device: '', workers: 8, lr0: 0.001, optimizer: 'AdamW', cos_lr: true, lrf: 0.01,
  warmup_epochs: 3.0, patience: 30, cache: 'disk', rect: true, deterministic: false,
  freeze: 0, dropout: 0.0, label_smoothing: 0.0, weight_decay: 0.0005,
  box: 7.5, cls: 0.5, dfl: 1.5, copy_paste: 0.0, close_mosaic: 10,
  mosaic: 1.0, mixup: 0.0, degrees: 0.0, scale: 0.5, translate: 0.1,
  shear: 0.0, perspective: 0.0, flipud: 0.0, hsv_h: 0.015, hsv_s: 0.7, hsv_v: 0.4,
  skip_validation: false, download_missing: true,
})

/**
 * 数值字段规格。**单位、范围、说明都写在这里**：模板只负责渲染，校验
 * （validateField）也读同一份 —— 否则「提示写 1–2000、校验允许 0」这类
 * 两层口径迟早对不上。
 *
 * 单位不是装饰：`训练轮数 150` 与 `训练轮数 150 轮`、`输入尺寸 640` 与
 * `640 px`，后者才让人一眼知道这一项是什么量纲；学习率这类没有单位的，
 * 就用范围提示（1e-6 ~ 1）代替。
 */
const NUMBER_FIELDS = [
  { key: 'epochs', label: '训练轮数', group: 'basic', step: 10, unit: '轮', min: 1, max: 5000, hint: '快速验证 50，正式训练 150–300' },
  { key: 'imgsz', label: '输入尺寸', group: 'basic', step: 32, unit: 'px', min: 32, max: 2048, multiple: 32, hint: '必须是 32 的倍数（YOLO 的下采样步长）' },
  { key: 'workers', label: '数据线程', group: 'basic', step: 1, unit: '个', min: 0, max: 64, hint: 'Windows 上给 0–8 更稳' },
  { key: 'lr0', label: '初始学习率', group: 'optim', step: 0.0001, min: 1e-6, max: 1, hint: '太大不收敛、太小跑不完；1e-3 起步' },
  { key: 'lrf', label: '最终学习率因子', group: 'optim', step: 0.001, min: 0, max: 1, hint: '末轮 lr = lr0 × 该因子' },
  { key: 'warmup_epochs', label: '预热轮数', group: 'optim', step: 0.5, unit: '轮', min: 0, max: 100 },
  { key: 'patience', label: '早停耐心', group: 'optim', step: 5, unit: '轮', min: 0, max: 2000, hint: '连续这么多轮无提升就停；0 = 不早停' },
  { key: 'weight_decay', label: '权重衰减', group: 'optim', step: 0.0001, min: 0, max: 1 },
  { key: 'dropout', label: 'Dropout', group: 'reg', step: 0.05, min: 0, max: 0.9, hint: '仅在分类任务生效' },
  { key: 'label_smoothing', label: '标签平滑', group: 'reg', step: 0.01, min: 0, max: 0.5 },
  { key: 'freeze', label: '冻结层数', group: 'reg', step: 1, unit: '层', min: 0, max: 24, hint: '冻结主干前 N 层，小数据可防过拟合' },
  { key: 'box', label: 'Box 权重', group: 'loss', step: 0.5, min: 0, max: 100 },
  { key: 'cls', label: '分类权重', group: 'loss', step: 0.1, min: 0, max: 100 },
  { key: 'dfl', label: 'DFL 权重', group: 'loss', step: 0.1, min: 0, max: 100 },
  { key: 'close_mosaic', label: '最后关 Mosaic', group: 'aug', step: 1, unit: '轮', min: 0, max: 100, hint: '末尾若干轮关掉 Mosaic，收敛更稳' },
  { key: 'mosaic', label: 'Mosaic 概率', group: 'aug', step: 0.1, min: 0, max: 1 },
  { key: 'mixup', label: 'Mixup 概率', group: 'aug', step: 0.1, min: 0, max: 1 },
  { key: 'degrees', label: '旋转范围', group: 'aug', step: 1, unit: '°', min: 0, max: 180 },
  { key: 'scale', label: '缩放幅度', group: 'aug', step: 0.1, min: 0, max: 1 },
  { key: 'translate', label: '平移幅度', group: 'aug', step: 0.05, min: 0, max: 1 },
  { key: 'shear', label: '剪切范围', group: 'aug', step: 1, unit: '°', min: 0, max: 90 },
  { key: 'perspective', label: '透视幅度', group: 'aug', step: 0.0005, min: 0, max: 0.001 },
  { key: 'flipud', label: '上下翻转概率', group: 'aug', step: 0.1, min: 0, max: 1, hint: '目标有明确上下方向时保持 0' },
  { key: 'hsv_h', label: '色相扰动', group: 'aug', step: 0.005, min: 0, max: 1 },
  { key: 'hsv_s', label: '饱和度扰动', group: 'aug', step: 0.1, min: 0, max: 1 },
  { key: 'hsv_v', label: '明度扰动', group: 'aug', step: 0.1, min: 0, max: 1 },
  { key: 'copy_paste', label: 'Copy-Paste', group: 'aug', step: 0.05, min: 0, max: 1, hint: '仅分割任务生效' },
]

/** 分组标题 + 一句话说明（说明回答"这一组影响什么"，而不是复读标题） */
const GROUPS = {
  basic: { title: '训练规模', desc: '一次跑多久、喂多大的图、用多少线程' },
  optim: { title: '优化器与学习率', desc: '影响收敛速度与稳定性' },
  reg: { title: '正则化', desc: '抑制过拟合' },
  loss: { title: '损失权重', desc: '调整定位 / 分类 / DFL 三者的相对权重' },
  aug: { title: '数据增强', desc: '每一种都是概率或幅度，设为 0 即关闭' },
}
/** 默认展开基础两组；其余收起但显示当前取值摘要（收起 ≠ 看不见） */
const ADVANCED_GROUPS = ['reg', 'loss', 'aug']

const fieldsOf = (g) => NUMBER_FIELDS.filter(f => f.group === g)

/** 单字段校验：范围 / 整除 —— 与渲染用的是同一份规格 */
function validateField(f) {
  const v = cfg.value[f.key]
  if (v === '' || v === null || v === undefined) return '必填'
  if (typeof v !== 'number' || Number.isNaN(v)) return '必须是数字'
  if (f.min !== undefined && v < f.min) return `不能小于 ${f.min}`
  if (f.max !== undefined && v > f.max) return `不能大于 ${f.max}`
  if (f.multiple && v % f.multiple !== 0) return `必须是 ${f.multiple} 的倍数`
  return ''
}

const fieldErrors = computed(() => {
  const out = {}
  for (const f of NUMBER_FIELDS) {
    const msg = validateField(f)
    if (msg) out[f.key] = msg
  }
  // 跨字段：预热轮数不该超过总轮数（否则整段训练都在 warmup）
  if (!out.warmup_epochs && Number(cfg.value.warmup_epochs) > Number(cfg.value.epochs)) {
    out.warmup_epochs = '不能超过训练轮数'
  }
  return out
})
const errorCount = computed(() => Object.keys(fieldErrors.value).length)

/** 收起状态下显示这一组当前的取值（"dropout 0 · 权重衰减 5e-4 · …"） */
function groupDigest(g) {
  return fieldsOf(g)
    .slice(0, 4)
    .map(f => `${f.label.replace(/\s.*$/, '')} ${fmtNum(cfg.value[f.key])}`)
    .join(' · ')
}
function focusFirstError() {
  const key = Object.keys(fieldErrors.value)[0]
  const el = document.querySelector(`[data-field="${key}"]`)
  if (!el) return
  if (typeof el.scrollIntoView === 'function') el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.focus({ preventScroll: true })
}
function fmtNum(v) {
  if (typeof v !== 'number') return v
  if (v === 0) return '0'
  return Math.abs(v) < 0.01 ? v.toExponential(0).replace('e-', 'e-') : String(v)
}

const localModels = computed(() => models.value.filter(m => m.local))
const remoteModels = computed(() => models.value.filter(m => !m.local))
const taskModels = computed(() =>
  (task.value === 'detect' ? [...localModels.value, ...remoteModels.value]
    : models.value.filter(m => m.task === task.value)))

function applyPreset() {
  Object.assign(cfg.value, PRESETS[preset.value] || {})
}

function onTaskChange() {
  cfg.value.task = task.value
  const first = taskModels.value[0]
  if (first) cfg.value.model = first.filename
}

async function downloadModel() {
  busy.value = true
  try {
    await api.postForm('/api/models/download', (() => {
      const f = new FormData(); f.append('filename', cfg.value.model); return f
    })())
    toastOk(`${cfg.value.model} 已下载`)
    const data = await api.get('/api/models')
    models.value = data.models
  } catch (e) { toastErr(errMsg(e)) } finally { busy.value = false }
}

function payload() {
  const body = { ...cfg.value, dataset_name: cfg.value.dataset_name }
  if (resumeOn.value && resumePath.value) {
    // 两处都要指向同一个 ckpt：管线从 cfg.model 解析模型路径（YOLO(model_path)），
    // 而 resume 标志来自 cfg.resume_from。只传 resume_from 会静默失效 ——
    // 不报错，但会拿原来的预训练模型重新起训，等于白等。
    body.model = resumePath.value
    body.resume_from = resumePath.value
    if (resumeDataset.value) body.dataset_name = resumeDataset.value
  }
  return body
}

async function startNow() {
  busy.value = true
  try {
    await api.post('/api/trainings/start', payload())
    router.push('/train/monitor')
  } catch (e) { toastErr(errMsg(e)) } finally { busy.value = false }
}

async function enqueue() {
  busy.value = true
  try {
    const r = await api.post('/api/queue/enqueue', payload())
    toastOk(`已加入队列（任务 #${r.task_id}）`)
  } catch (e) { toastErr(errMsg(e)) } finally { busy.value = false }
}

async function loadOptions() {
  loading.value = true
  loadError.value = ''
  try {
    const [ds, m] = await Promise.all([api.get('/api/datasets'), api.get('/api/models')])
    datasets.value = ds.datasets
    excluded.value = ds.statuses.filter(s => !s.is_trainable).map(s => s.name)
    models.value = m.models
  } catch (e) {
    // 失败必须与"没有数据集可用"区分开，否则用户会跑去检查数据集而不是网络
    loadError.value = errMsg(e)
    datasets.value = []; excluded.value = []; models.value = []
  } finally {
    loading.value = false
  }
  // 断点列表单独取且失败不致命：没有断点只是"不能续训"，
  // 不该让整页退化成"选项加载失败"。
  try {
    const runs = await api.get('/api/trainings/runs')
    checkpoints.value = runs.checkpoint_details || []
  } catch { checkpoints.value = [] }
}

/** 勾上续训时自动落到最新断点，避免"开了开关却因没选断点被静默挡住提交" */
function onResumeToggle() {
  if (resumeOn.value && !resumePath.value) {
    resumePath.value = checkpoints.value[0]?.path || ''
  }
}

// 断点决定数据集：能反推出来就同步过去，让用户看到"数据集被断点锁定"
watch(resumePath, (p) => {
  if (!resumeOn.value || !p) return
  const ds = checkpoints.value.find(c => c.path === p)?.dataset
  if (ds) cfg.value.dataset_name = ds
})

onMounted(loadOptions)
</script>

<template>
  <div>
    <div class="split-2 side-300">
      <!-- 左列：数据集/任务/模型/预设 -->
      <div style="display:flex;flex-direction:column;gap:16px">
        <div class="card">
          <h3>数据集</h3>
          <div v-if="loadError" class="state-msg error">
            选项加载失败：{{ loadError }}
            <div class="retry"><button class="btn sm" @click="loadOptions">重试</button></div>
          </div>
          <template v-else>
            <select v-model="cfg.dataset_name" :disabled="loading || datasetLocked">
              <option value="" disabled>{{ loading ? '加载中…' : '— 选择数据集 —' }}</option>
              <option v-for="d in datasets" :key="d" :value="d">{{ d }}</option>
            </select>
            <!-- 续训时数据集由断点决定，锁住而不是仅提示：管线会以这里的值传 data=，
                 选错不报错、只在别的数据上接着练，属于静默错误 -->
            <p v-if="datasetLocked" class="hint" style="margin-top:8px">
              由断点决定（{{ currentCkpt?.run }}），已锁定。
              <button class="link-btn" @click="resumeOn = false">退出续训</button>
            </p>
            <p v-if="resumeDatasetBad" class="hint danger" style="margin-top:8px">
              断点所属数据集 <b>{{ resumeDataset }}</b> 当前不可训练（缺 data.yaml），
              请先到 <router-link to="/datasets">数据集页</router-link> 处理。
            </p>
            <!-- 这里只列出可训练的（存在 data.yaml）。把被排除的也说出来，
                 否则用户在数据集页看到「可训练」的列表与这里对不上账。 -->
            <p v-else-if="!loading && excluded.length" class="hint" style="margin-top:8px">
              另有 {{ excluded.length }} 个数据集不可选（缺 data.yaml）：{{ excluded.join('、') }}
              <router-link to="/datasets">去处理</router-link>
            </p>
            <p v-else-if="!loading && !datasets.length" class="hint" style="margin-top:8px">
              暂无可训练数据集，先去 <router-link to="/datasets">数据集页</router-link> 上传。
            </p>
          </template>
        </div>

        <div class="card">
          <h3>任务与模型</h3>
          <label class="field" style="margin-bottom:10px">任务类型
            <select v-model="task" :disabled="resumeOn" @change="onTaskChange">
              <option value="detect">detect · 目标检测</option>
              <option value="segment">segment · 实例分割</option>
              <option value="pose">pose · 姿态估计</option>
              <option value="classify">classify · 图像分类</option>
            </select>
          </label>
          <label class="field" style="margin-bottom:10px">预训练模型
            <select v-model="cfg.model" :disabled="resumeOn">
              <option v-for="m in taskModels" :key="m.filename" :value="m.filename">
                {{ m.filename }}（{{ m.family }} {{ m.size }}）{{ m.local ? '· 本地' : '· 需下载' }}
              </option>
            </select>
          </label>
          <p v-if="resumeOn" class="hint" style="margin-bottom:10px">
            续训以断点内的模型为准，此处不生效。
          </p>
          <p v-else-if="localModels.length" class="hint" style="margin-bottom:10px">
            标注「本地」的 {{ localModels.length }} 个模型已在本机，可直接开始训练。
          </p>
          <button v-if="!resumeOn && remoteModels.some(m => m.filename === cfg.model)"
                  class="btn sm" :disabled="busy" @click="downloadModel">
            {{ busy ? '处理中…' : '下载选中模型' }}
          </button>
        </div>

        <div class="card">
          <h3>断点续训</h3>
          <label class="row-check">
            <input type="checkbox" v-model="resumeOn" @change="onResumeToggle" />
            从某个断点继续训练
          </label>

          <template v-if="resumeOn">
            <p v-if="!checkpoints.length" class="hint" style="margin-top:12px">
              暂无可用断点。续训需要一次未跑完的训练留下的
              <code class="mono">last.pt</code>（正常跑完的 run 只有 best.pt）。
            </p>
            <template v-else>
              <label class="field" style="margin-top:12px">选择断点
                <select v-model="resumePath">
                  <option v-for="c in checkpoints" :key="c.path" :value="c.path">
                    {{ c.run }} · {{ c.epochs_done }}/{{ c.epochs_planned }} 轮 · {{ c.modified }}
                  </option>
                </select>
              </label>
              <p v-if="currentCkpt" class="hint" style="margin-top:10px">
                数据集 <b>{{ currentCkpt.dataset || '无法判定' }}</b> ·
                已完成 <b>{{ currentCkpt.epochs_done }}</b> 轮 ·
                断点 {{ currentCkpt.size_mb }} MB
              </p>
              <!-- 反推不出去数据集（缺 args.yaml）时不能装作知道：让用户自己确认 -->
              <p v-if="currentCkpt && !currentCkpt.dataset" class="hint danger" style="margin-top:6px">
                该断点缺 <code class="mono">args.yaml</code>，无法反推数据集。
                请自行确认下方选中的数据集与断点一致，否则会在别的数据上接着练。
              </p>
            </template>
          </template>
        </div>

        <div v-if="!resumeOn" class="card">
          <h3>参数预设</h3>
          <div style="display:flex;flex-direction:column;gap:8px">
            <label v-for="(v, name) in PRESETS" :key="name"
                   style="display:flex;gap:8px;align-items:center;font-size:13px;cursor:pointer">
              <input type="radio" :value="name" v-model="preset" @change="applyPreset" style="width:auto" />
              {{ name }}
              <span class="muted mono" style="font-size:11px">{{ v.epochs }}ep / {{ v.imgsz }}px</span>
            </label>
          </div>
        </div>

        <!-- 主操作卡吸顶：长表单滚到下半屏时，「立即开始训练」仍在视野里。
             原先它被埋在左列最底部，改一个超参要滚回来才能提交。 -->
        <div class="card sticky-actions">
          <div class="card-head"><h3>执行</h3></div>

          <!-- 配置摘要：滚到任何位置都能对一眼"我到底要提交什么" -->
          <div class="exec-summary">
            <span :class="cfg.dataset_name ? 'mono' : 'field-error'">{{ cfg.dataset_name || '未选数据集' }}</span>
            <span class="sep">·</span><span class="mono">{{ cfg.model }}</span>
            <span class="sep">·</span><span class="mono">{{ cfg.epochs }} 轮</span>
            <span class="sep">·</span><span class="mono">{{ cfg.imgsz }} px</span>
            <span class="sep">·</span><span class="mono">{{ cfg.device ? `GPU ${cfg.device}` : 'auto 设备' }}</span>
          </div>

          <!-- 校验失败时，按钮不该只是"变灰"——要说出哪一项、为什么 -->
          <p v-if="errorCount" class="field-error" style="margin:0 0 10px">
            {{ errorCount }} 项参数需要修正：{{ Object.values(fieldErrors)[0] }}
            <a href="#" style="margin-left:6px" @click.prevent="focusFirstError">定位</a>
          </p>

          <div style="display:flex;flex-direction:column;gap:10px">
            <button class="btn primary" :disabled="!canSubmit" @click="startNow">
              {{ busy ? '提交中…' : (resumeOn ? '从断点继续训练' : '立即开始训练') }}
            </button>
            <button class="btn" :disabled="!canSubmit" @click="enqueue">
              {{ busy ? '提交中…' : '加入队列' }}
            </button>
            <label v-if="!resumeOn" class="row-check">
              <input type="checkbox" v-model="cfg.skip_validation" />
              跳过数据校验（数据已确认正常时）
            </label>
          </div>
        </div>
      </div>

      <!-- 右列：参数组。续训模式下这些参数一个都不会生效——管线在 resume 时
           只传 {"resume": True, "plots", "verbose"}，其余全部取 checkpoint 内的值。
           所以整列换成"续训将使用什么"，而不是摆一片改不动的输入框。 -->
      <div style="display:flex;flex-direction:column;gap:16px">
        <div v-if="resumeOn" class="card">
          <h3>续训将使用</h3>
          <table class="tbl">
            <tbody>
              <tr><td class="muted">数据集</td><td>{{ resumeDataset || cfg.dataset_name || '—' }}</td></tr>
              <tr><td class="muted">断点</td><td class="mono truncate" :title="resumePath">{{ currentCkpt?.run || '—' }}</td></tr>
              <tr><td class="muted">已完成</td><td class="mono">{{ currentCkpt?.epochs_done ?? '—' }} 轮</td></tr>
              <tr><td class="muted">原本计划</td><td class="mono">{{ currentCkpt?.epochs_planned ?? '—' }} 轮</td></tr>
              <tr><td class="muted">断点时间</td><td class="mono">{{ currentCkpt?.modified || '—' }}</td></tr>
            </tbody>
          </table>
          <p class="hint" style="margin-top:12px">
            续训以 checkpoint 内保存的超参数为准（轮数、学习率、优化器、批次、设备等），
            外部传入的覆盖参数会被忽略，因此常规参数区在续训模式下不显示。
          </p>
          <p class="hint" style="margin-top:8px">
            要改这些参数，请退出续训另起一次训练。
          </p>
        </div>

        <template v-if="!resumeOn">
        <div v-for="(meta, g) in GROUPS" :key="g" class="card">
          <div class="card-head">
            <h3>{{ meta.title }}</h3>
            <button v-if="ADVANCED_GROUPS.includes(g)" class="btn ghost sm" type="button"
                    @click="openGroups[g] = !openGroups[g]">
              {{ openGroups[g] ? '收起' : '展开' }}
            </button>
          </div>
          <p class="group-desc">{{ meta.desc }}</p>

          <!-- 训练规模组额外带三个枚举字段与三个开关（不是数值，单独排） -->
          <div v-if="g === 'basic'" class="grid c3" style="margin-bottom:14px">
            <label class="field">批次大小 Batch
              <select v-model="cfg.batch">
                <option value="-1">-1（AutoBatch 自动）</option>
                <option v-for="b in [2,4,8,16,32,64]" :key="b" :value="b">{{ b }}</option>
              </select>
            </label>
            <label class="field">训练设备
              <select v-model="cfg.device">
                <option value="">auto（自动检测）</option>
                <option value="cpu">cpu</option>
                <option value="0">GPU 0</option>
                <option value="1">GPU 1</option>
                <option value="0,1">GPU 0,1（DDP）</option>
              </select>
            </label>
            <label class="field">缓存 Cache
              <select v-model="cfg.cache">
                <option value="disk">disk（磁盘）</option>
                <option value="ram">ram（内存）</option>
                <option value="None">None（不缓存）</option>
              </select>
            </label>
            <label class="field">优化器
              <select v-model="cfg.optimizer">
                <option v-for="o in ['AdamW','SGD','Adam','NAdam','RAdam','RMSProp']" :key="o" :value="o">{{ o }}</option>
              </select>
            </label>
            <div class="field">
              <span class="label-row"><span>开关</span></span>
              <div class="check-row" style="align-items:center;min-height:34px">
                <label class="row-check"><input type="checkbox" v-model="cfg.rect" /> 矩形训练 rect</label>
                <label class="row-check"><input type="checkbox" v-model="cfg.cos_lr" /> 余弦调度</label>
                <label class="row-check"><input type="checkbox" v-model="cfg.deterministic" /> 确定性</label>
              </div>
            </div>
          </div>

          <div v-if="!ADVANCED_GROUPS.includes(g) || openGroups[g]" class="grid c3">
            <label v-for="f in fieldsOf(g)" :key="f.key" class="field">
              <span class="label-row">
                <span>{{ f.label }}</span>
                <span v-if="f.unit" class="unit">{{ f.unit }}</span>
              </span>
              <input type="number" v-model.number="cfg[f.key]" :step="f.step"
                     :min="f.min" :max="f.max" :data-field="f.key"
                     :class="{ invalid: fieldErrors[f.key] }" />
              <span v-if="fieldErrors[f.key]" class="field-error">{{ fieldErrors[f.key] }}</span>
              <span v-else-if="f.hint" class="sub-hint">{{ f.hint }}</span>
            </label>
          </div>
          <!-- 收起 ≠ 看不见：把这一组当前生效的值压成一行摘要 -->
          <p v-else class="group-digest">{{ groupDigest(g) }}</p>
        </div>
        </template>
      </div>
    </div>
  </div>
</template>
