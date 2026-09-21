// Regenerates the two dashboard screenshots the SIH deck uses:
//   docs/ui_national.png  - the national view at the first test window
//   docs/ui_district.png  - the same window with the top watchlist district open
// Rendered at 1920x1080 CSS pixels with a 2x pixel ratio (3840x2160), the size the deck expects.
// Needs the API (port 8000) and the dev server (port 5173) running; it resets the demo clock first.
//   node scripts/deck_screenshots.mjs [outdir]        FRAUDLENS_URL overrides the dev-server address
import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const OUT = process.argv[2] || path.resolve(HERE, '../../docs')
const BASE = process.env.FRAUDLENS_URL || 'http://127.0.0.1:5173/'
mkdirSync(OUT, { recursive: true })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

await fetch(new URL('api/simulate/reset', BASE), { method: 'POST' })      // first test window, empty alert feed

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || '/usr/bin/google-chrome', headless: 'new',
  args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars'],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 2 },
})
const page = await browser.newPage()
await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 60000 })
await page.waitForSelector('.leaflet-container canvas', { timeout: 30000 })
await sleep(2500)

await page.screenshot({ path: path.join(OUT, 'ui_national.png') })
console.log('wrote ui_national.png')

const top = await page.evaluate(() => {
  const row = document.querySelector('.watch-item'); const name = row?.querySelector('.n')?.textContent.trim()
  row?.click(); return name })
await sleep(2500)
await page.mouse.move(1000, 1075)                      // park the pointer off the map so no tooltip is drawn
await page.screenshot({ path: path.join(OUT, 'ui_district.png') })
console.log(`wrote ui_district.png (${top} open)`)
await browser.close()
