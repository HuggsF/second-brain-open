import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ mode }) => ({
  plugins: [tailwindcss()],
  base: './',
  server: { host: '127.0.0.1' },
  preview: { host: '127.0.0.1' },
  // Allow process.env to override VITE_ vars (useful for test isolation)
  define:
    process.env.VITE_RENDER_MODE
      ? { 'import.meta.env.VITE_RENDER_MODE': JSON.stringify(process.env.VITE_RENDER_MODE) }
      : {},
}));
