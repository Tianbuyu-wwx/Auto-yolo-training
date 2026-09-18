/**
 * 浮层（抽屉 / 放大遮罩）的共享契约：Esc 归最上层、滚动锁引用计数。
 *
 * 为什么需要它：抽屉里点开图片放大后，两层都在监听 window 的 keydown ——
 * 一个 Esc 会把两层一起关掉（用户想关的是最上面那层）；同理，两层都往
 * body 上加 `no-scroll` 又各自删除，先关的那层会把还在开放的那层的滚动锁
 * 一起放掉（背景又能滚了）。
 *
 * 规则：Esc 只派发给最后压栈的那一层；滚动锁按计数增删，归零才真正解锁。
 */
const escStack = []

/** 注册一个"最上层才生效"的 Esc 处理器，返回注销函数 */
export function onEscape(handler) {
  const entry = { handler }
  escStack.push(entry)

  const listener = (e) => {
    if (e.key !== 'Escape') return
    if (escStack[escStack.length - 1] === entry) handler()
  }
  window.addEventListener('keydown', listener)

  return () => {
    window.removeEventListener('keydown', listener)
    const i = escStack.indexOf(entry)
    if (i >= 0) escStack.splice(i, 1)
  }
}

let scrollLocks = 0

/** 锁背景滚动（可重入）。返回解锁函数。 */
export function lockScroll() {
  scrollLocks += 1
  document.body.classList.add('no-scroll')
  let released = false
  return () => {
    if (released) return          // 防重复调用把计数减穿
    released = true
    scrollLocks = Math.max(0, scrollLocks - 1)
    if (scrollLocks === 0) document.body.classList.remove('no-scroll')
  }
}

/** 仅供测试断言用：当前持锁层数 */
export const _scrollLocks = () => scrollLocks
