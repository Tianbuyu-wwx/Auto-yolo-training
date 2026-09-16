/** 后端 API 封装：REST + WebSocket */

async function request(path, opts = {}) {
  const resp = await fetch(path, opts)
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const body = await resp.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch { /* 非 JSON 错误体 */ }
    throw new Error(detail)
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
    ws = new WebSocket(`${proto}://${location.host}/ws/training`)
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
