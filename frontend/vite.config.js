import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发期：前端 5173 → 后端 8080（python -m src.api.admin）
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
})
