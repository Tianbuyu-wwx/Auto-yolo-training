<script setup>
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="card" style="max-width:520px">
    <h3>页面不存在</h3>
    <p class="hint" style="margin-bottom:14px">
      没有匹配 <code class="mono">{{ route.fullPath }}</code> 的路由。
    </p>
    <router-link class="btn" to="/">返回总览</router-link>
  </div>
</template>
