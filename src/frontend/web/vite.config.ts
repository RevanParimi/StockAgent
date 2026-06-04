import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon-32x32.png', 'apple-touch-icon.png'],
      manifest: {
        name: 'StockAgent — AI Stock Analysis',
        short_name: 'StockAgent',
        description: 'AI-powered stock analysis for Indian markets.',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#0b0f1a',
        theme_color: '#0b0f1a',
        icons: [
          { src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: '/pwa-maskable-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // SPA: serve index.html for client-side routes...
        navigateFallback: '/index.html',
        // ...but never for backend/API/doc paths (these must reach FastAPI).
        navigateFallbackDenylist: [
          /^\/api/, /^\/ui/, /^\/analyse/, /^\/history/, /^\/health/,
          /^\/tickers/, /^\/scheduler/, /^\/prompts/, /^\/analytics/,
          /^\/docs/, /^\/redoc/, /^\/openapi\.json/, /^\/ws/, /^\/\.well-known/,
        ],
        cleanupOutdatedCaches: true,
      },
    }),
  ],
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
    outDir: 'dist',
    emptyOutDir: true,
  },
})
