import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

const host = process.env.TAURI_DEV_HOST;

export default defineConfig({
  plugins: [sveltekit()],
  clearScreen: false,
  server: {
    // Los componentes se transforman al arrancar para que el CSS virtual de cada
    // uno no se pida antes que su JS; es la carrera que NB Books midió con el
    // webview de Tauri (ver su vite.config.js).
    warmup: { clientFiles: ['./src/**/*.svelte'] },
    // Tauri espera un puerto fijo y falla si no está libre.
    port: 1430,
    strictPort: true,
    host: host || false,
    hmr: host ? { protocol: 'ws', host, port: 1431 } : undefined,
    watch: {
      // El árbol de Rust lo vigila Cargo, y la V1 congelada no es código de la V2.
      ignored: ['**/src-tauri/**', '**/build/**', '**/legado/**']
    }
  },
  test: {
    include: ['src/**/*.{test,spec}.{js,ts}', 'scripts/**/*.test.mjs'],
    environment: 'node'
  }
});
