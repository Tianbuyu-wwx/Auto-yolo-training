/**
 * 指标口径：**哪个方向才是变好**。
 *
 * 之前注册表的版本对比把所有差值的正负都当成"越高越好"上色 —— 于是
 * `val/loss +0.12` 会被染成绿色（实际上更差了），而阅读者会照着颜色下结论。
 * 指标方向是领域知识，必须显式写在一处，而不是散在模板的表达式里。
 */

/** 越低越好的指标（损失、错误率、耗时、显存…） */
const LOWER_IS_BETTER = /(^|[^a-z])(loss|err(or)?|mae|mse|rmse|fpr|fnr|latency|time|dur(ation)?|mem(ory)?)([^a-z]|$)/i

/** 该指标是不是"越大越好"。未知指标默认越大越好（检测/分类的主指标都如此）。 */
export function higherIsBetter(name) {
  return !LOWER_IS_BETTER.test(String(name))
}

/**
 * 比较两个版本的同一指标。
 * @returns {{diff:number|null, winner:'v1'|'v2'|'same'|null, higherIsBetter:boolean}}
 */
export function compareMetric(name, v1, v2) {
  const higher = higherIsBetter(name)
  if (typeof v1 !== 'number' || typeof v2 !== 'number') {
    return { diff: null, winner: null, higherIsBetter: higher }
  }
  const diff = v2 - v1
  // 容差 1e-9：浮点回环会造成 1e-17 级的"差异"，标成提升/下降都是噪音
  if (Math.abs(diff) < 1e-9) return { diff: 0, winner: 'same', higherIsBetter: higher }
  const v2Better = diff > 0 === higher
  return { diff, winner: v2Better ? 'v2' : 'v1', higherIsBetter: higher }
}

/** 差值文本：带符号、去掉浮点尾巴 */
export function fmtDiff(diff, digits = 4) {
  if (diff == null) return '—'
  if (Math.abs(diff) < 1e-9) return '±0'
  return `${diff > 0 ? '+' : ''}${diff.toFixed(digits)}`
}
