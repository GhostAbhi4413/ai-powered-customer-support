import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'DEV_')
  return { plugins: [react(), tailwindcss()], server: { proxy: {
    '/api': { target: env.DEV_API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: true, rewrite: path => path.replace(/^\/api/, '') }
  } } }
})
