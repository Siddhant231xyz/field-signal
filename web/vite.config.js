import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: './',
  server: {
    // The engine stays in Python. The dev server only proxies to it.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
