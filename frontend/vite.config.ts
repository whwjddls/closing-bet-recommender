import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    // 프론트가 /api 로 백엔드(8010)를 프록시 → 폰(터널)에서 볼 때 백엔드를 따로
    // 노출하거나 CORS를 열 필요 없이 같은 오리진으로 동작한다. (VITE_API_BASE=/api)
    proxy: {
      '/api': {
        target: 'http://localhost:8010',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
    // cloudflared 임시 터널 도메인 허용(Vite 호스트 차단 우회).
    allowedHosts: ['.trycloudflare.com'],
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
