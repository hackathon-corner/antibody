import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev: proxy /api to the evidence API (uvicorn on :8000). Prod: same-origin or VITE_API_BASE.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': process.env.ANTIBODY_API ?? 'http://localhost:8000' },
  },
})
