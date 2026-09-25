import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // the name the team uses on their machines (a hosts entry pointing at
    // 127.0.0.1); Vite refuses requests for host names it was not told about
    allowedHosts: ['dgtest.dgpays.com'],
    // the API runs on 8010 because something else already owns 8000
    proxy: {
      '/api': { target: 'http://127.0.0.1:8010', changeOrigin: true },
    },
  },
})
