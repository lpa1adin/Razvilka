import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  // Режим разработки: API берём у запущенного docker compose (контейнер web проксирует /api).
  server: { proxy: { '/api': 'http://127.0.0.1:8660' } },
})
