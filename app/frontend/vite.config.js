import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    open: false,
    proxy: {
      '/embed': 'http://localhost:8000',
      '/search': 'http://localhost:8000',
      '/add': 'http://localhost:8000',
      '/upload': 'http://localhost:8000',
      '/user': 'http://localhost:8000',
      '/files': 'http://localhost:8000',
      '/emails': 'http://localhost:8000',
      '/api': 'http://localhost:8000',
      '/session/init': 'http://localhost:8000',
      '^/session/.*/embed/.*': 'http://localhost:8000',
      '/context': 'http://localhost:8000',
      '/logout': 'http://localhost:8000'
    }
  }
})
