// npm run build: docs/architecture-map/index.html, one self-contained file.
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'vite';

const viewer = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const target = path.resolve(viewer, '../../../docs/architecture-map/index.html');

await build({ configFile: path.join(viewer, 'vite.config.mjs') });

const dist = path.join(viewer, 'dist');
const written = readdirSync(dist, { recursive: true });
if (written.length !== 1 || written[0] !== 'index.html') {
  throw new Error(`the page must be one self-contained file; the build wrote: ${written.join(', ')}`);
}
// the repository keeps LF line endings
const html = readFileSync(path.join(dist, 'index.html'), 'utf8').replace(/\r\n/g, '\n');
writeFileSync(target, html);
console.log(`wrote ${path.relative(path.resolve(viewer, '../../..'), target)}: `
  + `${(Buffer.byteLength(html) / 1024 / 1024).toFixed(2)} MB`);
