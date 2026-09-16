<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
// 按需引入。此前是 `import * as echarts from 'echarts'`，把整包拉进产物：
// 实测 echarts.min.js 1,034,102 B 占 JS 产物 1,167,852 B 的 88.5%，
// 而这里只用到 line 一种图表 + grid/tooltip 两个组件。
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
// 只注册实际用到的组件：本项目的 option 里没有 tooltip 配置，注册它纯属浪费
import { GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, GridComponent, CanvasRenderer])

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: Number, default: 260 },
  /** 无数据点时的占位文案。父组件可换成更有行动指向的说法 */
  emptyText: { type: String, default: '暂无数据' },
})

/**
 * 是否没有任何数据点。没有它的时候，未开训的监控页会渲染出一副画好坐标系
 * 的空框 —— 读者无法判断这是"还没有数据"还是"图表坏了"。
 */
const isEmpty = computed(() => {
  const series = props.option?.series || []
  return series.length === 0 || series.every((s) => !s.data || s.data.length === 0)
})

const el = ref(null)
let chart = null
let ro = null
let lastKey = null

// 画布文字拿不到 CSS 变量，只能写死一份。必须与 tokens.css 的 --sans 同一
// 回退链 —— 图表标题来自后端 metric_labels（可能含中文），原先写死的
// 'JetBrains Mono' 在本机从未安装，且是纯拉丁字体，中文会逐字回退到宋体。
const CHART_FONT = '"Segoe UI", "Microsoft YaHei", "PingFang SC", system-ui, sans-serif'

/**
 * 数据指纹：只关心"画出来的东西变没变"。
 *
 * 父组件（TrainMonitorPage）每秒收到一帧 WS 并整体替换 status，其 computed
 * 每次都造出一个新对象，所以原先的 `watch(option, { deep: true })` 会**每秒
 * 重绘一次**，即使没有新 epoch。指纹只取各 series 的点数与末点值 + 标题，
 * 无变化直接跳过 setOption。
 */
function fingerprint(o) {
  if (!o) return ''
  const series = (o.series || []).map((s) => {
    const d = s.data || []
    return `${d.length}@${d.length ? JSON.stringify(d[d.length - 1]) : ''}`
  }).join('|')
  return `${o.title?.text ?? ''}::${series}`
}

function resize() { chart && chart.resize() }

onMounted(() => {
  chart = echarts.init(el.value)
  chart.setOption({
    animation: false,
    textStyle: { fontFamily: CHART_FONT, fontSize: 11 },
    ...props.option,
  })
  lastKey = fingerprint(props.option)
  // window.resize 感知不到容器自身尺寸变化（侧栏折叠、卡片换列、分栏变宽）
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(resize)
    ro.observe(el.value)
  }
  window.addEventListener('resize', resize)
})

watch(
  () => fingerprint(props.option),
  (key) => {
    if (key === lastKey || !chart) return
    lastKey = key
    chart.setOption(props.option)
  },
)

onBeforeUnmount(() => {
  ro && ro.disconnect()
  window.removeEventListener('resize', resize)
  chart && chart.dispose()
  chart = null
})
</script>

<template>
  <!-- 占位层盖在画布之上而不是替换画布：echarts 实例一旦被 display:none
       会在恢复时量到 0 尺寸而需要重排，用不透明覆盖层则完全不动尺寸。 -->
  <div class="chart-box" :style="{ height: height + 'px' }">
    <div ref="el" class="chart-canvas"></div>
    <p v-if="isEmpty" class="chart-empty">{{ emptyText }}</p>
  </div>
</template>
