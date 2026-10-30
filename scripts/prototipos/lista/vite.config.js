import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

// Banco de medida de F0.4.7, compilado aparte de la aplicación.
export default defineConfig({
  root: import.meta.dirname,
  plugins: [svelte()],
  build: { outDir: 'dist', emptyOutDir: true }
});
