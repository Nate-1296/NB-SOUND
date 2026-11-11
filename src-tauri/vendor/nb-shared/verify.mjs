import { createHash } from 'node:crypto';
import { lstat, readdir, readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const manifestName = 'nb-shared.manifest.json';

export function digest(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

export function inventoryId(files) {
  return digest(JSON.stringify(Object.entries(files).sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)));
}

export async function inventory(directory, prefix = '') {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (!prefix && (entry.name === 'target' || entry.name === 'Cargo.lock')) continue;
    const name = prefix + entry.name;
    if (!entry.name.match(/^[a-zA-Z0-9_.-]+$/) || entry.name === '.' || entry.name === '..') {
      throw new Error('INVALID_BUNDLE_PATH');
    }
    if (entry.isSymbolicLink()) throw new Error('BUNDLE_SYMLINK_REJECTED');
    if (entry.isDirectory()) files.push(...await inventory(resolve(directory, entry.name), name + '/'));
    else if (entry.isFile()) files.push(name);
    else throw new Error('INVALID_BUNDLE_ENTRY');
    if (files.length > 128) throw new Error('BUNDLE_FILE_LIMIT');
  }
  return files.sort();
}

export async function verifyBundle(directory) {
  const root = resolve(directory);
  if (!(await lstat(root)).isDirectory()) throw new Error('INVALID_BUNDLE_DIRECTORY');
  const actualFiles = await inventory(root);
  const manifestBytes = await readFile(resolve(root, manifestName));
  if (manifestBytes.length > 128 * 1024) throw new Error('MANIFEST_TOO_LARGE');
  const manifest = JSON.parse(manifestBytes.toString('utf8'));
  if (manifest.format !== 1 || manifest.source !== 'nb-launcher-workspace' ||
      manifest.license !== 'Apache-2.0' || !manifest.files || Array.isArray(manifest.files) ||
      typeof manifest.files !== 'object') throw new Error('INVALID_BUNDLE_MANIFEST');
  const expectedFiles = Object.keys(manifest.files).sort();
  if (JSON.stringify(actualFiles) !== JSON.stringify([...expectedFiles, manifestName].sort())) {
    throw new Error('BUNDLE_INVENTORY_MISMATCH');
  }
  for (const file of expectedFiles) {
    const expected = manifest.files[file];
    if (typeof expected !== 'string' || !/^[a-f0-9]{64}$/.test(expected)) throw new Error('INVALID_BUNDLE_HASH');
    // La enumeración anterior valida nombres y rechaza symlinks antes de resolver rutas.
    const bytes = await readFile(resolve(root, file));
    if (bytes.length > 2 * 1024 * 1024) throw new Error('BUNDLE_FILE_TOO_LARGE');
    if (digest(bytes) !== expected) throw new Error('BUNDLE_HASH_MISMATCH');
  }
  if (manifest.bundle_id !== inventoryId(manifest.files)) throw new Error('BUNDLE_ID_MISMATCH');
  return manifest;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    await verifyBundle(process.argv[2] ?? dirname(fileURLToPath(import.meta.url)));
    console.log('Bibliotecas compartidas: inventario y hashes correctos.');
  } catch (error) {
    console.error(error instanceof Error ? error.message : 'BUNDLE_VERIFY_ERROR');
    process.exitCode = 1;
  }
}
