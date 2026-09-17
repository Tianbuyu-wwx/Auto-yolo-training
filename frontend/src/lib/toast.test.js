/** 全局反馈条：入队、去重、超时自动消失（错误留更久） */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { dismissToast, pushToast, toastErr, toastOk, toasts } from './toast.js'

describe('toast 队列', () => {
  beforeEach(() => {
    toasts.value = []
    vi.useFakeTimers()
  })
  afterEach(() => vi.useRealTimers())

  it('入队并返回 id', () => {
    const id = pushToast('已保存')
    expect(id).toBeTypeOf('number')
    expect(toasts.value.map((t) => t.text)).toEqual(['已保存'])
  })

  it('空消息不入队（避免渲染一个空气泡）', () => {
    expect(pushToast('   ')).toBeNull()
    expect(toasts.value).toHaveLength(0)
  })

  it('dismissToast 移除指定项，重复移除不报错', () => {
    const id = pushToast('a')
    pushToast('b')
    dismissToast(id)
    dismissToast(id)
    expect(toasts.value.map((t) => t.text)).toEqual(['b'])
  })

  it('成功提示 4 秒后自动消失', () => {
    toastOk('done')
    vi.advanceTimersByTime(3999)
    expect(toasts.value).toHaveLength(1)
    vi.advanceTimersByTime(2)
    expect(toasts.value).toHaveLength(0)
  })

  it('错误至少停留 7 秒 —— 它通常带可操作的细节，一闪而过等于没说', () => {
    toastErr('数据集已存在，请勾选覆盖')
    vi.advanceTimersByTime(5000)
    expect(toasts.value).toHaveLength(1)
    vi.advanceTimersByTime(2100)
    expect(toasts.value).toHaveLength(0)
  })

  it('ttl=0 表示常驻（需要用户确认的场景）', () => {
    pushToast('请手动关闭', 'info', 0)
    vi.advanceTimersByTime(600000)
    expect(toasts.value).toHaveLength(1)
  })
})
