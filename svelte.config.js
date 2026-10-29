import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/**
 * NB Sound es una aplicación de página única dentro del webview de Tauri: no hay
 * servidor ni renderizado en servidor, así que el adaptador es el estático.
 * Ver docs/adr/decisions/ADR-001-pila-tecnologica.md
 * @type {import('@sveltejs/kit').Config}
 */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      fallback: 'index.html',
      precompress: false,
      strict: true
    }),
    alias: {
      $core: 'src/lib/core',
      $ui: 'src/lib/ui'
    }
  },
  compilerOptions: {
    runes: true
  }
};

export default config;
