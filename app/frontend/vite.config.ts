import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],

  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },

  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/watcher/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },

  base: '/app/',

  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },

})
