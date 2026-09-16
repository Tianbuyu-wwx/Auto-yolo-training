import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发期：前端 5173 → 后端 8080（python -m src.api.admin / ayt-web）
// 生产期：vite build 产物由 FastAPI 静态托管，同源无代理问题
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8080', ws: true },
    },
  },
  build: {
    // 分三个 chunk：echarts 与 vue 都不随业务代码变动，独立 chunk 后
    // 改一行业务代码不会让用户重新下载 400KB 的图表库。
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('echarts') || id.includes('zrender')) return 'vendor-echarts'
          return 'vendor'
        },
      },
    },
    // 500KB 是通用默认值，对本项目没有意义：最大的 chunk 是图表库，
    // 它的大小由 echarts 决定而非我们的代码质量。真正的门禁写在 CI 里。
    chunkSizeWarningLimit: 700,
  },
})
