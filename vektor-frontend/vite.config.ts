import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Все запросы фронта идут на /api/... — dev-сервер проксирует их на FastAPI.
    // CORS не нужен: для браузера всё выглядит как один origin.
    proxy: {
      '/api': {
        // 127.0.0.1, не localhost: на этой машине localhost иногда резолвится
        // в IPv6 (::1), а бэкенд слушает только IPv4 — прокси падал 502.
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
