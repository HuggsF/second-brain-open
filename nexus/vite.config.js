import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [tailwindcss()],
  base: './',
  server: { host: '127.0.0.1' },
  preview: { host: '127.0.0.1' }
});
