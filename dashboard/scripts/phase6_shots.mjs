// Drives the Phase 6 flows: alert generation, all three roles, dispatch,
// and the printable report. Both servers must be running.
import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'fs'
const OUT = process.argv[2] || './shots6'
mkdirSync(OUT, { recursive: true })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await puppeteer.launch({
  executablePath: '/usr/bin/google-chrome', headless: 'new',
  args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars'],
  defaultViewport: { width: 1920, height: 1080 },
})
const page = await browser.newPage()
const errors = []
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()) })

const clickText = (sel, text) => page.evaluate((s, t) => {
  const el = [...document.querySelectorAll(s)].find((x) => x.textContent.trim().includes(t))
  if (el) { el.click(); return true } return false
}, sel, text)

await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle2', timeout: 60000 })
await page.waitForSelector('.leaflet-container path', { timeout: 30000 })
await sleep(1200)

// generate alerts
for (let i = 0; i < 3; i++) { await clickText('button', 'Advance'); await sleep(2300) }

// 1. I4C with the feed open
await clickText('button', 'Alerts'); await sleep(1400)
await page.screenshot({ path: `${OUT}/01-i4c-feed.png` }); console.log('01-i4c-feed')

// 2. dispatch an SMS -> toast shows the real message
await clickText('.feed-actions .btn', 'SMS'); await sleep(1600)
await page.screenshot({ path: `${OUT}/02-dispatch-sms.png` }); console.log('02-dispatch-sms')

// 3. intelligence report - pick an alert that has money in flight, so the
//    chains table is populated rather than empty
await page.evaluate(() => {
  const items = [...document.querySelectorAll('.feed-item')]
  const rich = items.find((el) => !/Rs 0 in flight/.test(el.textContent))
  const btn = [...(rich || items[0]).querySelectorAll('.btn')]
    .find((b) => b.textContent.trim() === 'Report')
  btn && btn.click()
})
await sleep(1800)
await page.screenshot({ path: `${OUT}/03-report.png` }); console.log('03-report')
await page.evaluate(() => { const s = document.querySelector('.report-overlay'); if (s) s.scrollTop = 780 })
await sleep(600)
await page.screenshot({ path: `${OUT}/04-report-lower.png` }); console.log('04-report-lower')
await clickText('.report-toolbar .btn', 'Close'); await sleep(900)

// 4. State LEA + cross-jurisdiction inbox
await clickText('.role-tab', 'State LEA'); await sleep(2600)
await page.select('.role-block select', 'Jharkhand').catch(() => {})
await sleep(2600)
await page.screenshot({ path: `${OUT}/05-state-lea.png` }); console.log('05-state-lea')

// 5. Bank role (the drawer auto-closes on a role switch)
await clickText('.role-tab', 'Bank'); await sleep(3000)
await page.screenshot({ path: `${OUT}/06-bank.png` }); console.log('06-bank')
await clickText('button', 'Alerts'); await sleep(1200)
await page.screenshot({ path: `${OUT}/07-bank-feed-restricted.png` }); console.log('07-bank-feed-restricted')

console.log(errors.length ? '\nERRORS:\n' + errors.slice(0, 10).join('\n') : '\nno browser errors')
await browser.close()
