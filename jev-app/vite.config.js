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
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.js'],
  },
});
