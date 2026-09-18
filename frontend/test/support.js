/**
 * 组件测试的公共脚手架。
 *
 * 两条设计取舍：
 *
 * 1. **假 api 模块**，而不是打桩 fetch。页面真正关心的是「拿到什么数据以后渲染
 *    成什么样」，而不是 HTTP 细节；REST 封装本身在 `src/lib/api.test.js` 里
 *    单独测（那里打桩的才是 fetch）。
 * 2. **端点 → 空数据**的形状写全。这套 EMPTY_PAYLOADS 同时是「后端一无所有时
 *    页面能不能挂载」的契约：新增页面/端点时在这里补一行，smoke 用例自动覆盖。
 */
import { createMemoryHistory, createRouter } from 'vue-router'
import { mount } from '@vue/test-utils'
import { vi } from 'vitest'

/**
 * 后端各端点的空数据形状。
 *
 * 训练状态字段与 `src/gradio_app/models/training_state.py` 的 TrainingState 对齐；
 * runs 载荷里带 `artifacts` 段（ResultStore 的产物快照，见 src/run_store.py）。
 */
export const EMPTY_PAYLOADS = {
  '/api/trainings/status': {
    is_running: false,
    is_stopping: false,
    success: false,
    current_stage: '',
    current_epoch: 0,
    total_epochs: 0,
    current_loss: 0,
    current_map50: 0,
    current_map50_95: 0,
    progress: 0,
    eta_seconds: null,
    artifact_note: '',
    task: 'detect',
    metric_labels: ['mAP@50', 'mAP@50-95'],
  },
  '/api/trainings/runs': {
    runs: [],
    checkpoints: [],
    checkpoint_details: [],
    artifacts: { runs: [], exports: {}, recycle_dir: '', recycled_count: 0, recycled_sample: [] },
  },
  '/api/trainings/compare': { markdown: '' },
  // 形状按后端真实返回：/api/datasets → {datasets, statuses}（src/api/admin.py）
  '/api/datasets': { datasets: [], statuses: [] },
  '/api/models': { models: [] },
  '/api/queue/tasks': { tasks: [] },
  '/api/registry': { datasets: {} },
  '/api/recycle': { items: [] },
}

/**
 * 构造一个可控的假 api 模块（供 `vi.mock('../lib/api.js', ...)` 使用）。
 *
 * 返回的对象会被当作 api 模块：页面拿 `api/errMsg/trainingSocket`，
 * 测试拿 `handlers`（改场景）与 `calls`（断言打了哪些请求）。
 */
export function makeApiModule() {
  const handlers = { ...EMPTY_PAYLOADS }
  const calls = []
  // WebSocket 也做成可控的：页面注册进来，测试手动喂帧
  const sockets = []

  // 取**最长**匹配前缀：否则 /api/datasets/<name> 会被 /api/datasets 抢先命中，
  // 详情类端点永远拿到列表载荷（新增子端点时特别容易踩）
  const pick = (path) => {
    const key = Object.keys(handlers)
      .filter((k) => path.startsWith(k))
      .sort((a, b) => b.length - a.length)[0]
    return key ? handlers[key] : {}
  }
  const record = (method) => vi.fn(async (path, body) => {
    calls.push({ method, path, body })
    return pick(path)
  })

  return {
    api: { get: record('GET'), post: record('POST'), del: record('DELETE'), postForm: record('POSTFORM') },
    handlers,
    calls,
    sockets,
    errMsg: (e) => (e && e.message ? e.message : String(e)),
    trainingSocket: vi.fn((onMessage, onState) => {
      const socket = { onMessage, onState, closed: false }
      sockets.push(socket)
      return () => { socket.closed = true }
    }),
  }
}

/** 挂载页面（带内存路由：页面里用了 router-link / useRoute） */
export async function mountPage(component, { props = {} } = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/:pathMatch(.*)*', component: { template: '<div />' } },
    ],
  })
  await router.push('/')
  await router.isReady()
  return mount(component, { props, global: { plugins: [router] } })
}
