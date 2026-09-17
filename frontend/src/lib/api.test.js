/**
 * REST 封装与训练状态 WebSocket。
 *
 * 这里是唯一打桩 `fetch` 的地方：页面级用例走 test/support.js 的假 api 模块，
 * 而错误转文案、content-type 分支、WS 自动重连这些细节只能在这一层验证。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api, errMsg, trainingSocket } from './api.js'

function fakeResponse(body, { status = 200, contentType = 'application/json', statusText = 'OK' } = {}) {
  return {
    ok: status < 400,
    status,
    statusText,
    headers: { get: () => contentType },
    json: async () => body,
  }
}

describe('request() 对响应的处理', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async () => fakeResponse({ ok: true }))
  })

  it('GET 把 JSON 解出来', async () => {
    await expect(api.get('/api/health')).resolves.toEqual({ ok: true })
    expect(fetch).toHaveBeenCalledWith('/api/health', {})
  })

  it('content-type 不是 json 时返回原始响应（下载类端点要拿去 blob）', async () => {
    global.fetch = vi.fn(async () => fakeResponse('x', { contentType: 'image/png' }))
    const resp = await api.get('/api/datasets/ds/preview/img.png')
    expect(resp.headers.get()).toBe('image/png')
  })

  it('错误体是 JSON detail 时，错误消息就用 detail', async () => {
    global.fetch = vi.fn(async () => fakeResponse({ detail: '数据集已存在' }, { status: 409 }))
    await expect(api.get('/api/datasets/x')).rejects.toThrow('数据集已存在')
  })

  it('错误带上 status，界面才能区分「服务离线」与「请求被拒」', async () => {
    global.fetch = vi.fn(async () => fakeResponse({ detail: 'bad' }, { status: 400 }))
    await api.get('/api/x').catch((e) => {
      expect(e.status).toBe(400)
    })
  })

  it('非 JSON 错误体回落 statusText', async () => {
    global.fetch = vi.fn(async () => fakeResponse(null, {
      status: 502, statusText: 'Bad Gateway', contentType: 'text/html',
    }))
    await expect(api.get('/api/x')).rejects.toThrow('Bad Gateway')
  })

  it('post 带 JSON body 与 content-type', async () => {
    await api.post('/api/trainings/start', { epochs: 2 })
    const [, opts] = fetch.mock.calls[0]
    expect(opts.method).toBe('POST')
    expect(opts.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(opts.body)).toEqual({ epochs: 2 })
  })

  it('post 不带 body 时不设 content-type（后端按无参处理）', async () => {
    await api.post('/api/trainings/stop')
    const [, opts] = fetch.mock.calls[0]
    expect(opts.headers).toEqual({})
    expect(opts.body).toBeUndefined()
  })

  it('postForm 交给浏览器自己定 multipart 边界', async () => {
    const form = new FormData()
    await api.postForm('/api/datasets/upload', form)
    const [, opts] = fetch.mock.calls[0]
    expect(opts.body).toBe(form)
    expect(opts.headers).toBeUndefined()   // 设了 content-type 反而会吃掉 boundary
  })

  it('del 走 DELETE', async () => {
    await api.del('/api/recycle/x')
    expect(fetch.mock.calls[0][1].method).toBe('DELETE')
  })

  it('errMsg 兜住非 Error 输入', () => {
    expect(errMsg(new Error('boom'))).toBe('boom')
    expect(errMsg(null)).toBe('null')
  })
})

class FakeWebSocket {
  static instances = []
  constructor(url) {
    this.url = url
    this.sent = []
    FakeWebSocket.instances.push(this)
  }
  close() { this.onclose && this.onclose() }
}

describe('trainingSocket()', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    global.WebSocket = FakeWebSocket
    vi.useFakeTimers()
  })
  afterEach(() => vi.useRealTimers())

  it('连到 /ws/training，且不带任何凭据参数（本项目无认证层）', () => {
    trainingSocket(() => {}, () => {})
    const ws = FakeWebSocket.instances[0]
    expect(ws.url).toBe('ws://localhost:3000/ws/training')
  })

  it('onopen/onmessage/onclose 分别驱动状态与消息回调', () => {
    const onMessage = vi.fn()
    const onState = vi.fn()
    trainingSocket(onMessage, onState)
    const ws = FakeWebSocket.instances[0]

    ws.onopen()
    ws.onmessage({ data: JSON.stringify({ type: 'training', status: { current_epoch: 3 } }) })
    ws.onclose()

    expect(onState.mock.calls.map((c) => c[0])).toEqual(['connected', 'disconnected'])
    expect(onMessage).toHaveBeenCalledWith({ type: 'training', status: { current_epoch: 3 } })
  })

  it('坏帧不让回调炸掉（解析失败即忽略）', () => {
    const onMessage = vi.fn()
    trainingSocket(onMessage, () => {})
    const ws = FakeWebSocket.instances[0]
    expect(() => ws.onmessage({ data: '{ oops' })).not.toThrow()
    expect(onMessage).not.toHaveBeenCalled()
  })

  it('断开后 2 秒自动重连', () => {
    trainingSocket(() => {}, () => {})
    FakeWebSocket.instances[0].onclose()
    expect(FakeWebSocket.instances).toHaveLength(1)

    vi.advanceTimersByTime(2000)

    expect(FakeWebSocket.instances).toHaveLength(2)
  })

  it('调用返回的关闭函数后不再重连', () => {
    const close = trainingSocket(() => {}, () => {})
    close()
    vi.advanceTimersByTime(10000)
    expect(FakeWebSocket.instances).toHaveLength(1)
  })
})
