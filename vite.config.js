import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

const host = process.env.TAURI_DEV_HOST;

export default defineConfig({
  plugins: [
    // NB Sound es una aplicación de página única dentro del webview de Tauri: no
    // hay servidor ni renderizado en servidor, así que el adaptador es el
    // estático (ADR-001). SvelteKit 3 ya no lee `svelte.config.js`.
    sveltekit({
      preprocess: vitePreprocess(),
      adapter: adapter({
        pages: 'build',
        assets: 'build',
        fallback: 'index.html',
        precompress: false,
        strict: true
      }),
      alias: {
        $lib: 'src/lib',
        $core: 'src/lib/core',
        $ui: 'src/lib/ui'
      },
      compilerOptions: {
        runes: true
      }
    })
  ],
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
