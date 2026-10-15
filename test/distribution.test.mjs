import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const stem = 'youtube-copiar-transcripcion';
const source = readFileSync(join(root, `${stem}.user.js`), 'utf8');
const header = source.match(/^\/\/ ==UserScript==\r?\n[\s\S]*?^\/\/ ==\/UserScript==\r?\n/m)?.[0];
const value = key => header?.match(new RegExp(`^// @${key}\\s+(.+)$`, 'm'))?.[1].trim();
const base = 'https://raw.githubusercontent.com/alexx-ftw/youtube-transcript-copier/main/';

test('preserves the installed script identity', () => {
  assert.ok(source.startsWith('// ==UserScript==\n'));
  assert.equal(value('name'), 'YouTube - Copiar transcripción completa');
  assert.equal(value('namespace'), 'eros.youtube.transcript');
});
test('uses stable public update and download endpoints', () => {
  assert.equal(value('updateURL'), `${base}${stem}.meta.js`);
  assert.equal(value('downloadURL'), `${base}${stem}.user.js`);
});
test('metadata and displayed version agree', () => {
  assert.match(value('version'), /^\d+\.\d+\.\d+$/);
  assert.equal(source.match(/const VERSION = '([^']+)'/)[1], value('version'));
});
test('metadata-only file is an exact header copy', () => {
  assert.equal(readFileSync(join(root, `${stem}.meta.js`), 'utf8'), header);
});
test('TXT distribution is byte-identical to the installable script', () => {
  assert.equal(readFileSync(join(root, `${stem}.txt`), 'utf8'), source);
});
test('adds no runtime permissions for updating', () => {
  assert.deepEqual([...header.matchAll(/^\/\/ @grant\s+(.+)$/gm)].map(m => m[1].trim()).sort(),
    ['GM.setClipboard', 'GM_setClipboard', 'unsafeWindow'].sort());
  assert.deepEqual([...header.matchAll(/^\/\/ @match\s+(.+)$/gm)].map(m => m[1].trim()).sort(),
    ['https://www.youtube.com/*', 'https://youtube.com/*'].sort());
});
