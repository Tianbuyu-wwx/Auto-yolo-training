<script setup>
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: Number, default: 260 },
})
const el = ref(null)
let chart = null

function resize() { chart && chart.resize() }

onMounted(() => {
  chart = echarts.init(el.value)
  chart.setOption({
    animation: false,
    textStyle: { fontFamily: 'JetBrains Mono, Consolas, monospace', fontSize: 11 },
    ...props.option,
  })
  window.addEventListener('resize', resize)
})
watch(() => props.option, (o) => chart && chart.setOption(o), { deep: true })
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart && chart.dispose()
})
</script>

<template>
  <div ref="el" :style="{ height: height + 'px', width: '100%' }"></div>
</template>
