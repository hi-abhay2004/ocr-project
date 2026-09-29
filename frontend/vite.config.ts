import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': new URL('./src', import.meta.url).pathname },
  },
  server: {
    port: 5173,
    // FRONTEND_PLAN §9 Phase A.2 — proxying /api removes CORS from dev entirely.
    // /media is proxied too: annotation crops are Django-served files and the
    // overlay <img> must resolve them same-origin.
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/media': { target: 'http://localhost:8000', changeOrigin: true },
    },
    // Vite blocks requests whose Host header it doesn't recognise (DNS
    // rebinding protection) — needed only while tunneling this dev server
    // through something like Pinggy/ngrok, which forwards the public
    // hostname as-is. Fine for a temporary local demo; not meant to stay
    // true for a real deployment.
    allowedHosts: true,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/tests/setup.ts'],
    css: false,
    exclude: ['**/node_modules/**', '**/dist/**', '**/e2e/**'],
  },
})
