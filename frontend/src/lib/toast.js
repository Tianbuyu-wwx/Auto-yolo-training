/**
 * 全局操作反馈。
 *
 * 为什么需要它：此前各页面的操作结果都落在页面内的 <p class="ok-text"> 上，
 * 位置跟着触发按钮走。实测「立即开始训练」的反馈渲染在左侧列底部——在 1400px
 * 高的页面里位于首屏之外，用户点击后看不到任何回应，于是会重复点击。
 *
 * 用模块级 ref 而不是 provide/inject：反馈生产者（各个页面）与宿主
 * （App.vue 里的 ToastHost）之间没有任何组件层级的必然关系，注入链反而更绕。
 */
import { ref } from 'vue'

export const toasts = ref([])
let seq = 0

export function pushToast(message, tone = 'info', ttl = 4000) {
  const text = String(message ?? '').trim()
  if (!text) return null
  const id = ++seq
  toasts.value.push({ id, text, tone })
  // 错误留久一点：它通常带可操作的细节（如「已存在，请勾选覆盖」）
  const ttlMs = ttl > 0 ? (tone === 'error' ? Math.max(ttl, 7000) : ttl) : 0
  if (ttlMs > 0) setTimeout(() => dismissToast(id), ttlMs)
  return id
}

export function dismissToast(id) {
  const i = toasts.value.findIndex((t) => t.id === id)
  if (i >= 0) toasts.value.splice(i, 1)
}

export const toastOk = (msg) => pushToast(msg, 'success')
export const toastErr = (msg) => pushToast(msg, 'error')
