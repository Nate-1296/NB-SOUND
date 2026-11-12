// El presupuesto de F1.3.1 no se mide junto a los ensayos intensivos de DSP.
// No se amplía el límite ni se reintenta una medición que falla.
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

const cwd = resolve(import.meta.dirname, '../src-tauri');
const prueba = 'db::busqueda::tests::cien_mil_pistas_se_buscan_en_menos_de_30_ms';
const base = ['test', '--locked', '--all-features', '--lib', prueba, '--', '--ignored', '--exact'];
const inventario = spawnSync('cargo', [...base, '--list'], { cwd, encoding: 'utf8' });
if (inventario.error || inventario.status !== 0 || !inventario.stdout.includes(`${prueba}: test`)) {
  console.error('No se pudo comprobar la presencia de la prueba de rendimiento.');
  if (inventario.stderr) process.stderr.write(inventario.stderr);
  process.exit(1);
}
const resultado = spawnSync('cargo', [...base, '--test-threads=1'], { cwd, stdio: 'inherit' });
if (resultado.error || resultado.status !== 0) process.exit(resultado.status ?? 1);
