import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// Dev server on :3000. API and FastAPI docs are proxied to the backend
// (default http://localhost:8000, override with VITE_PROXY_TARGET).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const target = env.VITE_PROXY_TARGET || 'http://localhost:8000';

  const proxy = { target, changeOrigin: true };

  return {
    plugins: [react()],
    server: {
      port: 3000,
      strictPort: true,
      proxy: {
        '/api': proxy,
        '/docs': proxy,
        '/openapi.json': proxy,
      },
    },
    preview: {
      port: 3000,
      proxy: {
        '/api': proxy,
        '/docs': proxy,
        '/openapi.json': proxy,
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
      chunkSizeWarningLimit: 900,
    },
  };
});
