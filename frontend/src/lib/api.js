/** 后端 API 封装：REST + WebSocket */

/**
 * 管理面 API Key。
 *
 * 后端是「方案 A」：未配置 YOLO_API_KEY 时不校验，配了才要求 `X-API-Key`。
 * 所以这里默认空 —— 本地开发不需要做任何事；部署到局域网时把 key 填进来即可。
 * 存 localStorage 而不是内存：控制台是多页 SPA，刷新后不该再问一次。
 */
const KEY_STORAGE = 'ayt.apiKey'

export function getApiKey() {
  try { return localStorage.getItem(KEY_STORAGE) || '' } catch { return '' }
}

export function setApiKey(value) {
  try {
    if (value) localStorage.setItem(KEY_STORAGE, value)
    else localStorage.removeItem(KEY_STORAGE)
  } catch { /* 隐私模式 / 禁用存储：降级为「本次会话不保存」 */ }
}

async function request(path, opts = {}) {
  const key = getApiKey()
  const headers = { ...(opts.headers || {}) }
  if (key) headers['X-API-Key'] = key

  const resp = await fetch(path, { ...opts, headers })
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const body = await resp.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch { /* 非 JSON 错误体 */ }
    const err = new Error(detail)
    // 带上状态码：401 要让界面能说「是缺密钥」而不是笼统的「API 离线」
    err.status = resp.status
    throw err
  }
  const ct = resp.headers.get('content-type') || ''
  return ct.includes('json') ? resp.json() : resp
}

export const api = {
  get: (p) => request(p),
  post: (p, body) => request(p, {
    method: 'POST',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }),
  del: (p) => request(p, { method: 'DELETE' }),
  postForm: (p, form) => request(p, { method: 'POST', body: form }),
}

/** 训练状态 WebSocket（自动重连） */
export function trainingSocket(onMessage, onState) {
  let ws = null
  let closed = false
  let retryTimer = null

  function connect() {
    if (closed) return
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    // 浏览器不给 WebSocket 设自定义请求头，key 只能走查询参数。
    // 每次重连都重新读一次：用户补填 key 后无需刷新，下一次重试就带上了。
    const key = getApiKey()
    const query = key ? `?api_key=${encodeURIComponent(key)}` : ''
    ws = new WebSocket(`${proto}://${location.host}/ws/training${query}`)
    ws.onmessage = (ev) => {
      try { onMessage(JSON.parse(ev.data)) } catch { /* 忽略坏帧 */ }
    }
    ws.onopen = () => onState && onState('connected')
    ws.onclose = () => {
      onState && onState('disconnected')
      if (!closed) retryTimer = setTimeout(connect, 2000)
    }
    ws.onerror = () => ws.close()
  }
  connect()

  return () => {
    closed = true
    clearTimeout(retryTimer)
    if (ws) ws.close()
  }
}

/** 后端返回的 detail 错误转为可读文案 */
export function errMsg(e) {
  return e && e.message ? e.message : String(e)
}
