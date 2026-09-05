// Drives the dashboard in a real browser and captures the demo states.
// Usage: node scripts/screenshot.mjs [outdir]
// Requires the API (port 8000) and vite dev server (port 5173) to be running.
import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'fs'

const OUT = process.argv[2] || './shots'
const URL = process.env.FRAUDLENS_URL || 'http://127.0.0.1:5173/'
mkdirSync(OUT, { recursive: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await puppeteer.launch({
  executablePath: '/usr/bin/google-chrome',
  headless: 'new',
  args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=1'],
  defaultViewport: { width: 1920, height: 1080 },
})
const page = await browser.newPage()
const errors = []
page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`) })
page.on('requestfailed', (r) => errors.push(`request failed: ${r.url()}`))

await page.goto(URL, { waitUntil: 'networkidle2', timeout: 60000 })
await page.waitForSelector('.leaflet-container path', { timeout: 30000 })
await sleep(1200)
await page.screenshot({ path: `${OUT}/01-initial.png` })
console.log('01-initial.png')

// Advance the clock a few windows so the self-grading panel has real numbers.
for (let i = 0; i < 3; i++) {
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find((x) => x.textContent.includes('Advance'))
    b && b.click()
  })
  await sleep(2200)
}
await page.screenshot({ path: `${OUT}/02-advanced.png` })
console.log('02-advanced.png')

// Open the top-ranked district from the watchlist.
await page.evaluate(() => document.querySelector('.watch-item')?.click())
await sleep(2500)
await page.screenshot({ path: `${OUT}/03-district.png` })
console.log('03-district.png')

// Scroll the drill-down panel to show chains and recent events.
await page.evaluate(() => { const p = document.querySelector('.panel.right'); if (p) p.scrollTop = 900 })
await sleep(700)
await page.screenshot({ path: `${OUT}/04-district-scrolled.png` })
console.log('04-district-scrolled.png')

if (errors.length) {
  console.log('\nBROWSER ERRORS:')
  errors.slice(0, 12).forEach((e) => console.log('  ' + e))
} else {
  console.log('\nno browser errors')
}
await browser.close()
