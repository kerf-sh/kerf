import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Custom env file resolution: .env (local default), .env.dev, .env.main.
// Run: `npm run dev` (local), `npm run dev:dev` (dev), `npm run build` (main).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiUrl = env.VITE_API_URL || 'http://localhost:8090'

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        '/api': { target: apiUrl, changeOrigin: true },
        '/auth': { target: apiUrl, changeOrigin: true },
      },
    },
    optimizeDeps: {
      include: ['three', '@jscad/modeling'],
    },
  }
})
