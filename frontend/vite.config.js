import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiTarget = process.env.ST_API_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: Number(process.env.ST_UI_PORT ?? 5173),
    strictPort: true,
    proxy: {
      '/api': apiTarget,
      '/mcp': apiTarget,
    },
  },
});
