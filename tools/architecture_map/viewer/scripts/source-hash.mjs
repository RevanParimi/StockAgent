// A fingerprint of what the built page is made from, written into it, so a test can tell
// that the committed page was built from the committed source. The model is not part of
// it: it changes with the code, and the page shows which commit it was read at.
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

const TOP = ['.npmrc', 'index.html', 'package-lock.json', 'package.json', 'vite.config.mjs'];
const FOLDERS = ['scripts', 'src'];

export function viewerFiles(viewerDir) {
  const found = [...TOP];
  const walk = (relative) => {
    for (const entry of readdirSync(path.join(viewerDir, relative), { withFileTypes: true })) {
      const child = `${relative}/${entry.name}`;
      if (entry.isDirectory()) walk(child);
      else found.push(child);
    }
  };
  FOLDERS.forEach(walk);
  return found.sort();
}

export function sourceHash(viewerDir) {
  const hash = createHash('sha256');
  for (const file of viewerFiles(viewerDir)) {
    const text = readFileSync(path.join(viewerDir, file), 'utf8').replace(/\r\n/g, '\n');
    hash.update(`${file}\0${text}\0`);
  }
  return `sha256:${hash.digest('hex')}`;
}
