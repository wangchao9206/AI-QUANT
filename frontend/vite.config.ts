import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        timeout: 1000,
        proxyTimeout: 1000,
      },
      '/actuator': {
        target: 'http://localhost:8080',
        timeout: 1000,
        proxyTimeout: 1000,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    css: true,
  },
})
