// El inventario sellado es verificable desde un clon independiente de Sound.
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';
const result = spawnSync(process.execPath, [resolve(import.meta.dirname, '../src-tauri/vendor/nb-shared/verify.mjs')], { stdio: 'inherit' });
process.exit(result.status ?? 1);
