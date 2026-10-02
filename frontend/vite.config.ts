import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // 开发时把 /api 开头的请求转发给后端，前端代码里直接写 fetch('/api/...')
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
