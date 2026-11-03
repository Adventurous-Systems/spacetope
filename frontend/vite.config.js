import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5273,
    proxy: {
      // 127.0.0.1, not localhost: Node >=17 resolves localhost to ::1 first,
      // while uvicorn binds IPv4 only — the proxy then 500s on every /api call.
      '/api': { target: 'http://127.0.0.1:8100', changeOrigin: true },
      '/static': { target: 'http://127.0.0.1:8100', changeOrigin: true },
    },
  },
});
