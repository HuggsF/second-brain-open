import { defineConfig } from 'vitest/config';
import tailwindcss from '@tailwindcss/vite';

// O BFF serve /dashboard/* com CSP restrita: sem script/estilo inline, sem fonte, sem sourcemap.
export default defineConfig({
  plugins: [tailwindcss()],
  base: './',
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': 'http://127.0.0.1:8848',
      '/v1': 'http://127.0.0.1:8848',
    },
  },
  build: {
    outDir: '../dashboard/jev',
    emptyOutDir: true,
    sourcemap: false,
    modulePreload: { polyfill: false },
    assetsInlineLimit: 0,
    // lucide-react traz a diretiva "use client" (RSC), sem sentido num SPA: ignorada de proposito.
    rolldownOptions: {
      onwarn(warning, defaultHandler) {
        if (warning.code === 'MODULE_LEVEL_DIRECTIVE') return;
        defaultHandler(warning);
      },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{js,jsx}'],
    setupFiles: ['./src/test-setup.js'],
  },
});
