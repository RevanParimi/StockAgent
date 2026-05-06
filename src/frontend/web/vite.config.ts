import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // All API calls proxy to the FastAPI backend
      '/api':       { target: 'http://localhost:8000', changeOrigin: true, rewrite: p => p.replace(/^\/api/, '') },
      '/ui':        { target: 'http://localhost:8000', changeOrigin: true },
      '/analyse':   { target: 'http://localhost:8000', changeOrigin: true },
      '/history':   { target: 'http://localhost:8000', changeOrigin: true },
      '/health':    { target: 'http://localhost:8000', changeOrigin: true },
      // WebSocket proxy
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../../prototypes/dist',  // output relative to project root for deployment
    emptyOutDir: true,
  },
})
