import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Todas las llamadas del frontend a /api/* van al backend FastAPI.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
