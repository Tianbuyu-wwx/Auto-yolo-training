<script setup>
import { onMounted, ref } from 'vue'
import { api, errMsg } from '../lib/api.js'

const datasets = ref([])
const statuses = ref([])
const selected = ref('')
const info = ref(null)
const previews = ref([])
const showBoxes = ref(false)
const validating = ref(false)
const validateMsg = ref('')
const validateOk = ref(true)

// 上传
const zipFile = ref(null)
const uploadName = ref('')
const overwrite = ref(false)
const uploadMsg = ref('')
const uploadOk = ref(true)

// 转换
const pendingList = ref([])
const deleteOriginal = ref(false)
const convertMsg = ref('')
const convertOk = ref(true)

async function refresh(selectAfter) {
  const data = await api.get('/api/datasets')
  datasets.value = data.datasets
  statuses.value = data.statuses
  pendingList.value = data.statuses.filter(s => s.needs_conversion).map(s => s.name)
  if (selectAfter && datasets.value.includes(selectAfter)) selectDataset(selectAfter)
  else if (selected.value && !datasets.value.includes(selected.value)) {
    selected.value = ''; info.value = null; previews.value = []
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
  uploadMsg.value = ''
  if (!zipFile.value) { uploadMsg.value = '请选择 ZIP 文件'; uploadOk.value = false; return }
  const form = new FormData()
  form.append('file', zipFile.value)
  form.append('name', uploadName.value)
  form.append('overwrite', overwrite.value)
  try {
    const result = await api.postForm('/api/datasets/upload', form)
    uploadOk.value = true
    uploadMsg.value = `✅ ${result.message}`
    zipFile.value = null
    await refresh(result.dataset_name)
  } catch (e) {
    uploadOk.value = false
    uploadMsg.value = errMsg(e)
    if (String(uploadMsg.value).includes('已存在')) uploadMsg.value += '（可勾选「覆盖同名数据集」）'
  }
}

async function onValidate() {
  validating.value = true
  try {
    const r = await api.post(`/api/datasets/${encodeURIComponent(selected.value)}/validate`)
    validateOk.value = r.is_valid
    validateMsg.value = r.message
  } catch (e) { validateOk.value = false; validateMsg.value = errMsg(e) }
  validating.value = false
}

async function onConvert() {
  convertMsg.value = ''
  try {
    const r = await api.post(
      `/api/datasets/${encodeURIComponent(selected.value)}/convert?delete_original=${deleteOriginal.value}`)
    convertOk.value = true
    convertMsg.value = r.message
    await refresh(r.converted_name)
  } catch (e) { convertOk.value = false; convertMsg.value = errMsg(e) }
}

onMounted(() => refresh())
</script>

<template>
  <div>
    <h1 class="page-title">数据集管理</h1>

    <div style="display:grid;grid-template-columns:340px 1fr;gap:16px;align-items:start">
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
            <button class="btn primary" @click="onUpload">上传并解压</button>
            <p v-if="uploadMsg" :class="uploadOk ? 'ok-text' : 'error-text'">{{ uploadMsg }}</p>
          </div>
        </div>

        <div class="card">
          <h3>格式转换（分类 → YOLO）</h3>
          <p v-if="pendingList.length" class="mono" style="font-size:12px;color:var(--amber);margin-bottom:10px">
            待转换：{{ pendingList.join('、') }}
          </p>
          <p v-else class="muted" style="font-size:12.5px;margin-bottom:10px">✅ 所有数据集均为 YOLO 格式</p>
          <label style="display:flex;gap:8px;align-items:center;font-size:12.5px;color:var(--text-muted);margin-bottom:10px">
            <input type="checkbox" v-model="deleteOriginal" style="width:auto" />
            转换后删除原始数据集（默认保留）
          </label>
          <button class="btn" :disabled="!selected" @click="onConvert">转换当前数据集</button>
          <p v-if="convertMsg" :class="convertOk ? 'ok-text' : 'error-text'">{{ convertMsg }}</p>
        </div>
      </div>

      <!-- 右侧：列表 + 详情 -->
      <div style="display:flex;flex-direction:column;gap:16px">
        <div class="card">
          <h3>数据集列表（{{ datasets.length }}）</h3>
          <table class="tbl">
            <thead><tr><th>名称</th><th>格式</th><th>图像</th><th>状态</th></tr></thead>
            <tbody>
              <tr v-for="s in statuses" :key="s.name" style="cursor:pointer" @click="selectDataset(s.name)">
                <td><code :style="s.name === selected ? 'color:var(--blue)' : ''">{{ s.name }}</code></td>
                <td>{{ s.format }}</td>
                <td class="mono">{{ s.image_count }}</td>
                <td>
                  <span class="badge" :class="s.is_ready ? 'ok' : 'warn'">{{ s.is_ready ? '就绪' : '需处理' }}</span>
                </td>
              </tr>
              <tr v-if="!statuses.length"><td colspan="4" class="muted">暂无数据集，请上传 ZIP</td></tr>
            </tbody>
          </table>
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
          <pre v-if="validateMsg" class="mono" style="margin-top:10px;font-size:12px;white-space:pre-wrap;color:var(--text)">{{ validateMsg }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>
