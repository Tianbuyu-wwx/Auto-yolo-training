<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, errMsg } from '../lib/api.js'

const router = useRouter()
const datasets = ref([])
const models = ref([])
const task = ref('detect')
const busy = ref(false)
const msg = ref('')
const msgOk = ref(true)

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
  busy.value = true; msg.value = ''
  try {
    await api.postForm('/api/models/download', (() => {
      const f = new FormData(); f.append('filename', cfg.value.model); return f
    })())
    msgOk.value = true; msg.value = `✅ ${cfg.value.model} 已下载`
    const data = await api.get('/api/models')
    models.value = data.models
  } catch (e) { msgOk.value = false; msg.value = errMsg(e) }
  busy.value = false
}

function payload() {
  return { ...cfg.value, dataset_name: cfg.value.dataset_name }
}

async function startNow() {
  busy.value = true; msg.value = ''
  try {
    await api.post('/api/trainings/start', payload())
    router.push('/train/monitor')
  } catch (e) { msgOk.value = false; msg.value = errMsg(e) }
  busy.value = false
}

async function enqueue() {
  busy.value = true; msg.value = ''
  try {
    const r = await api.post('/api/queue/enqueue', payload())
    msgOk.value = true
    msg.value = `✅ 已加入队列（任务 #${r.task_id}）`
  } catch (e) { msgOk.value = false; msg.value = errMsg(e) }
  busy.value = false
}

onMounted(async () => {
  const [ds, m] = await Promise.all([api.get('/api/datasets'), api.get('/api/models')])
  datasets.value = ds.datasets
  models.value = m.models
})
</script>

<template>
  <div>
    <h1 class="page-title">训练配置</h1>

    <div style="display:grid;grid-template-columns:300px 1fr;gap:16px;align-items:start">
      <!-- 左列：数据集/任务/模型/预设 -->
      <div style="display:flex;flex-direction:column;gap:16px">
        <div class="card">
          <h3>数据集</h3>
          <select v-model="cfg.dataset_name">
            <option value="" disabled>— 选择数据集 —</option>
            <option v-for="d in datasets" :key="d" :value="d">{{ d }}</option>
          </select>
        </div>

        <div class="card">
          <h3>任务与模型</h3>
          <label class="field" style="margin-bottom:10px">任务类型
            <select v-model="task" @change="onTaskChange">
              <option value="detect">detect · 目标检测</option>
              <option value="segment">segment · 实例分割</option>
              <option value="pose">pose · 姿态估计</option>
              <option value="classify">classify · 图像分类</option>
            </select>
          </label>
          <label class="field" style="margin-bottom:10px">预训练模型
            <select v-model="cfg.model">
              <option v-for="m in taskModels" :key="m.filename" :value="m.filename">
                {{ m.local ? '✅ ' : '' }}{{ m.filename }}（{{ m.family }} {{ m.size }}）
              </option>
            </select>
          </label>
          <button class="btn sm" :disabled="busy" @click="downloadModel" v-if="remoteModels.some(m => m.filename === cfg.model)">
            ⬇️ 下载选中模型
          </button>
        </div>

        <div class="card">
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
            <button class="btn primary" :disabled="busy || !cfg.dataset_name" @click="startNow">▶ 立即开始训练</button>
            <button class="btn" :disabled="busy || !cfg.dataset_name" @click="enqueue">▦ 加入队列</button>
            <label style="display:flex;gap:8px;align-items:center;font-size:12.5px;color:var(--text-muted)">
              <input type="checkbox" v-model="cfg.skip_validation" style="width:auto" />
              跳过数据校验（数据已确认正常时）
            </label>
          </div>
          <p v-if="msg" :class="msgOk ? 'ok-text' : 'error-text'">{{ msg }}</p>
        </div>
      </div>

      <!-- 右列：参数组 -->
      <div style="display:flex;flex-direction:column;gap:16px">
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
              <span style="display:flex;gap:14px">
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
      </div>
    </div>
  </div>
</template>
