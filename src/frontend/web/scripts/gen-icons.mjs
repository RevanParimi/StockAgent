/**
 * Generates PWA icons from an inline SVG monogram.
 * Placeholder branding — swap the SVG for a real logo later and re-run:
 *   node scripts/gen-icons.mjs
 */
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import sharp from 'sharp'

const __dirname = dirname(fileURLToPath(import.meta.url))
const PUBLIC = resolve(__dirname, '..', 'public')
mkdirSync(PUBLIC, { recursive: true })

// `inset` = fraction of empty padding around the artwork (maskable needs ~20% safe zone)
const svg = (inset = 0) => {
  const pad = Math.round(512 * inset)
  const box = 512 - pad * 2
  return `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0b0f1a"/>
      <stop offset="1" stop-color="#111a2e"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#22d3ee"/>
      <stop offset="1" stop-color="#6366f1"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="96" fill="url(#bg)"/>
  <g transform="translate(${pad},${pad})">
    <g transform="translate(${box * 0.5},${box * 0.46})">
      <text x="0" y="0" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="${box * 0.46}"
            font-weight="800" fill="#e2e8f0" text-anchor="middle" dominant-baseline="central"
            letter-spacing="-6">SA</text>
    </g>
    <polyline points="${box*0.18},${box*0.82} ${box*0.40},${box*0.66} ${box*0.56},${box*0.74} ${box*0.84},${box*0.40}"
              fill="none" stroke="url(#accent)" stroke-width="${box*0.045}"
              stroke-linecap="round" stroke-linejoin="round"/>
    <polygon points="${box*0.84},${box*0.40} ${box*0.84},${box*0.56} ${box*0.70},${box*0.42}"
             fill="url(#accent)"/>
  </g>
</svg>`
}

const jobs = [
  { name: 'pwa-192x192.png',          size: 192, inset: 0 },
  { name: 'pwa-512x512.png',          size: 512, inset: 0 },
  { name: 'pwa-maskable-512x512.png', size: 512, inset: 0.14 },
  { name: 'apple-touch-icon.png',     size: 180, inset: 0.06 },
  { name: 'favicon-32x32.png',        size: 32,  inset: 0 },
]

for (const job of jobs) {
  const out = resolve(PUBLIC, job.name)
  await sharp(Buffer.from(svg(job.inset))).resize(job.size, job.size).png().toFile(out)
  console.log('wrote', job.name)
}
console.log('done — icons in', PUBLIC)
