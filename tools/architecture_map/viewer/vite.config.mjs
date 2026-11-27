import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { viteSingleFile } from 'vite-plugin-singlefile';
import { sourceHash } from './scripts/source-hash.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const MODEL = path.resolve(here, '../../../docs/architecture-map/model.json');

/** The model goes into the page as data (a page opened from disk cannot fetch a file). */
const embedModel = () => ({
  name: 'embed-architecture-model',
  transformIndexHtml() {
    const model = JSON.parse(readFileSync(MODEL, 'utf8'));
    // `<` only occurs inside JSON strings, where < reads the same and cannot end the tag
    const text = JSON.stringify(model).replace(/</g, '\\u003c');
    return [
      { tag: 'meta', attrs: { name: 'viewer-source', content: sourceHash(here) }, injectTo: 'head' },
      { tag: 'script', attrs: { type: 'application/json', id: 'model' }, children: text,
        injectTo: 'body-prepend' },
    ];
  },
});

export default defineConfig({
  root: here,
  plugins: [react(), embedModel(), viteSingleFile({ removeViteModuleLoader: true })],
  build: {
    outDir: path.join(here, 'dist'),
    emptyOutDir: true,
    target: 'es2022',
    modulePreload: false,
    reportCompressedSize: false,
    chunkSizeWarningLimit: 6000,
  },
  logLevel: 'warn',
});
