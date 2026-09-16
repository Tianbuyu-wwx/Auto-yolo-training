/**
 * 图表配色。与 tokens.css 的表面阶梯同源。
 *
 * 为什么单独成文件：原先这套色值在 TrainMonitorPage 的两个 option 里各写一遍
 * （共 6 处），任意一处改动都会让两张图不一致。
 *
 * 为什么数值和旧版不同：旧值（axis #343a4f / split #1a1d28 / 文字 #8b90a0）
 * 是按 #14161f 的卡片底调的 —— 卡片变深到 #0b0d13 之后，坐标轴相对底色偏亮，
 * 无数据时会先跳出来一副"空框"。改为层级更弱的白系，让数据线成为唯一主角。
 * 画布（canvas）拿不到 CSS 变量，只能在这里写死一份，改 tokens 时需一并核对。
 */
export const CHART = {
  /** 标题 / 轴标签：对应 --text-muted */
  label: '#8a90a3',
  /** 轴线：比 --border 稍强，否则在纯黑底上看不见 */
  axis: 'rgba(255, 255, 255, .13)',
  /** 分隔线：最弱的一档，只提供读数参考 */
  split: 'rgba(255, 255, 255, .05)',
  grid: { left: 48, right: 16, top: 30, bottom: 28 },
  /** 单序列线色（与 --blue / --green 一致） */
  line: { blue: '#3b82f6', green: '#22c55e' },
  /** 面积填充：线色的低透明度版本 */
  area: { blue: 'rgba(59,130,246,.13)', green: 'rgba(34,197,94,.11)' },
}

/** 生成两图共用的坐标轴配置（x 轴为 epoch，y 轴可选上限） */
export function axisPair({ yMax } = {}) {
  const base = { type: 'value', axisLine: { lineStyle: { color: CHART.axis } }, axisLabel: { color: CHART.label }, splitLine: { lineStyle: { color: CHART.split } } }
  return {
    xAxis: { ...base, name: 'epoch' },
    yAxis: yMax === undefined ? { ...base } : { ...base, max: yMax },
  }
}
