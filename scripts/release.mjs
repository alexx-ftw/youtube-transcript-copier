#!/usr/bin/env node
// Keep one source of truth: the .user.js file. This command never pushes changes.
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { Script } from 'node:vm';

const root = fileURLToPath(new URL('../', import.meta.url));
const stem = 'youtube-copiar-transcripcion';
const sourcePath = join(root, `${stem}.user.js`);
const versionPattern = /^(0|[1-9]\d{0,7})\.(0|[1-9]\d{0,7})\.(0|[1-9]\d{0,7})$/;
const base = 'https://raw.githubusercontent.com/alexx-ftw/youtube-transcript-copier/main/';

try {
  const args = process.argv.slice(2);
  const mode = args[0] || '--sync';
  if (args.length > 1 || !['--check', '--sync'].includes(mode) && !versionPattern.test(mode)) {
    throw new Error('Uso: node scripts/release.mjs [--check | --sync | X.Y.Z]');
  }
  let source = readFileSync(sourcePath, 'utf8');
  const current = source.match(/^\/\/ @version\s+(\S+)$/m)?.[1];
  if (!versionPattern.test(current || '')) throw new Error('Falta una versión X.Y.Z válida.');
  const runtime = source.match(/  const VERSION = '([^']+)';/g) || [];
  if (runtime.length !== 1) throw new Error('Debe existir una única constante VERSION.');
  if (versionPattern.test(mode)) {
    const oldParts = current.split('.').map(Number);
    const newParts = mode.split('.').map(Number);
    const difference = newParts.map((part, i) => part - oldParts[i]).find(part => part !== 0) || 0;
    if (difference <= 0) throw new Error(`La nueva versión debe ser mayor que ${current}.`);
    source = source.replace(/^\/\/ @version\s+\S+$/m, `// @version      ${mode}`)
      .replace(runtime[0], `  const VERSION = '${mode}';`);
  }
  const header = source.match(/^\/\/ ==UserScript==\n[\s\S]*?^\/\/ ==\/UserScript==\n/m)?.[0];
  if (!header || !source.startsWith(header)) throw new Error('Cabecera inválida. Usa UTF-8 sin BOM y saltos LF.');
  const get = key => header.match(new RegExp(`^// @${key}\\s+(.+)$`, 'm'))?.[1].trim();
  if (get('version') !== source.match(/const VERSION = '([^']+)'/)[1]) throw new Error('VERSION y @version no coinciden.');
  if (get('name') !== 'YouTube - Copiar transcripción completa' || get('namespace') !== 'eros.youtube.transcript') {
    throw new Error('No cambies la identidad del userscript instalado.');
  }
  if (get('updateURL') !== `${base}${stem}.meta.js` || get('downloadURL') !== `${base}${stem}.user.js`) {
    throw new Error('Las URL de actualización deben apuntar a los archivos estables de main.');
  }
  new Script(source, { filename: `${stem}.user.js` });
  const outputs = [[sourcePath, source], [join(root, `${stem}.meta.js`), header], [join(root, `${stem}.txt`), source]];
  if (mode === '--check') {
    for (const [path, expected] of outputs) {
      if (readFileSync(path, 'utf8') !== expected) throw new Error(`Archivo desincronizado: ${path}. Ejecuta npm run sync.`);
    }
    console.log(`Distribución v${get('version')} verificada.`);
  } else {
    for (const [path, content] of outputs) writeFileSync(path, content, 'utf8');
    console.log(`Distribución v${get('version')} generada. Ejecuta npm test antes de publicar.`);
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
