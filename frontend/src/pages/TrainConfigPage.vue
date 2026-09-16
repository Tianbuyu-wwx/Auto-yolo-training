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

const canSubmit = computed(() => !busy.value && !!cfg.value.dataset_name && !resumeBlocked.value)

const PRESETS = {
  快速验证: { epochs: 50, batch: 16, imgsz: 416, patience: 10, lr0: 0.002 },
  标准训练: { epochs: 150, batch: 16, imgsz: 640, patience: 30, lr0: 0.001 },
  精细调优: { epochs: 300, batch: 8, imgsz: 640, patience: 50, lr0: 0.0005 },
}
const preset = ref('标准训练')

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

const NUMBER_FIELDS = [
  { key: 'epochs', label: '训练轮数', group: 'basic', step: 10 },
  { key: 'imgsz', label: '输入尺寸', group: 'basic', step: 32 },
  { key: 'workers', label: '数据线程', group: 'basic', step: 1 },
  { key: 'lr0', label: '学习率 lr0', group: 'optim', step: 0.0001 },
  { key: 'lrf', label: '最终lr因子', group: 'optim', step: 0.001 },
  { key: 'warmup_epochs', label: '预热轮数', group: 'optim', step: 0.5 },
  { key: 'patience', label: '早停耐心', group: 'optim', step: 5 },
  { key: 'weight_decay', label: '权重衰减', group: 'optim', step: 0.0001 },
  { key: 'dropout', label: 'Dropout', group: 'reg', step: 0.05 },
  { key: 'label_smoothing', label: '标签平滑', group: 'reg', step: 0.01 },
  { key: 'freeze', label: '冻结层数', group: 'reg', step: 1 },
  { key: 'box', label: 'Box权重', group: 'loss', step: 0.5 },
  { key: 'cls', label: 'Cls权重', group: 'loss', step: 0.1 },
  { key: 'dfl', label: 'DFL权重', group: 'loss', step: 0.1 },
  { key: 'close_mosaic', label: '关Mosaic轮数', group: 'aug', step: 1 },
  { key: 'mosaic', label: 'Mosaic', group: 'aug', step: 0.1 },
  { key: 'mixup', label: 'Mixup', group: 'aug', step: 0.1 },
  { key: 'degrees', label: '旋转°', group: 'aug', step: 1 },
  { key: 'scale', label: '缩放', group: 'aug', step: 0.1 },
  { key: 'translate', label: '平移', group: 'aug', step: 0.05 },
  { key: 'shear', label: '剪切°', group: 'aug', step: 1 },
  { key: 'perspective', label: '透视', group: 'aug', step: 0.0005 },
  { key: 'flipud', label: '上下翻转', group: 'aug', step: 0.1 },
  { key: 'hsv_h', label: 'HSV-H', group: 'aug', step: 0.005 },
  { key: 'hsv_s', label: 'HSV-S', group: 'aug', step: 0.1 },
  { key: 'hsv_v', label: 'HSV-V', group: 'aug', step: 0.1 },
  { key: 'copy_paste', label: 'Copy-Paste', group: 'aug', step: 0.05 },
]
const GROUP_TITLES = {
  basic: '基础', optim: '优化器 / 学习率', reg: '正则化',
  loss: '损失权重', aug: '数据增强',
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
          <p v-if="loadError" class="state-msg error">
            选项加载失败：{{ loadError }}
            <div class="retry"><button class="btn sm" @click="loadOptions">重试</button></div>
          </p>
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

        <div class="card">
          <h3>执行</h3>
          <div style="display:flex;flex-direction:column;gap:10px">
            <button class="btn primary" :disabled="!canSubmit" @click="startNow">
              {{ busy ? '提交中…' : (resumeOn ? '▶ 从断点继续训练' : '▶ 立即开始训练') }}
            </button>
            <button class="btn" :disabled="!canSubmit" @click="enqueue">
              {{ busy ? '提交中…' : '▦ 加入队列' }}
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
        <div class="card">
          <h3>基础</h3>
          <div class="grid c4">
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
            <label v-for="f in NUMBER_FIELDS.filter(f => f.group === 'basic')" :key="f.key" class="field">
              {{ f.label }}
              <input type="number" v-model.number="cfg[f.key]" :step="f.step" />
            </label>
            <label class="field">缓存 Cache
              <select v-model="cfg.cache">
                <option value="disk">disk</option><option value="ram">ram</option><option value="None">None</option>
              </select>
            </label>
            <label class="field">优化器
              <select v-model="cfg.optimizer">
                <option v-for="o in ['AdamW','SGD','Adam','NAdam','RAdam','RMSProp']" :key="o" :value="o">{{ o }}</option>
              </select>
            </label>
            <label style="justify-content:flex-end" class="field">
              矩形训练
              <span class="check-row">
                <label style="display:flex;gap:5px;align-items:center;cursor:pointer">
                  <input type="checkbox" v-model="cfg.rect" style="width:auto" /> rect
                </label>
                <label style="display:flex;gap:5px;align-items:center;cursor:pointer">
                  <input type="checkbox" v-model="cfg.cos_lr" style="width:auto" /> cosine lr
                </label>
                <label style="display:flex;gap:5px;align-items:center;cursor:pointer">
                  <input type="checkbox" v-model="cfg.deterministic" style="width:auto" /> deterministic
                </label>
              </span>
            </label>
          </div>
        </div>

        <details v-for="g in ['optim', 'reg', 'loss', 'aug']" :key="g" class="card" :open="g === 'optim'">
          <summary style="cursor:pointer;font-size:13px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em">
            {{ GROUP_TITLES[g] }}
          </summary>
          <div class="grid c4" style="margin-top:14px">
            <label v-for="f in NUMBER_FIELDS.filter(f => f.group === g)" :key="f.key" class="field">
              {{ f.label }}
              <input type="number" v-model.number="cfg[f.key]" :step="f.step" />
            </label>
          </div>
        </details>
        </template>
      </div>
    </div>
  </div>
</template>
