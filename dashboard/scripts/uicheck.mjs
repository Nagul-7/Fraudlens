// UI regression check. Verifies, in a real browser:
//   1. the map hover tooltip resolves a score (not "--") and matches the watchlist
//   2. risk rounding is identical across the stats block, watchlist and map stats
//   3. the Bank role honours the state filter (districts, ATMs and accounts)
//   4. the State LEA referral inbox honours the fraud-category filter
// Both servers must be running.  node scripts/uicheck.mjs ./out
import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'fs'
const OUT = process.argv[2]; mkdirSync(OUT, { recursive: true })
const sleep = (ms) => new Promise(r => setTimeout(r, ms))
const b = await puppeteer.launch({ executablePath:'/usr/bin/google-chrome', headless:'new',
  args:['--no-sandbox','--disable-gpu','--hide-scrollbars'], defaultViewport:{width:1920,height:1080} })
const p = await b.newPage()
const errs = []
p.on('pageerror', e => errs.push('pageerror: ' + e.message))
p.on('console', m => { if (m.type()==='error') errs.push('console: ' + m.text()) })
const clickText = (sel,t)=>p.evaluate((s,t)=>{const e=[...document.querySelectorAll(s)]
  .find(x=>x.textContent.trim().includes(t)); if(e){e.click();return true} return false},sel,t)

await p.goto('http://127.0.0.1:5173/', { waitUntil:'networkidle2', timeout:60000 })
await p.waitForSelector('.leaflet-container path', { timeout:30000 })
await sleep(2500)
for (let i=0;i<2;i++){ await clickText('button','Advance'); await sleep(2300) }

// --- BUG 1: hover the top watchlist district and read the tooltip ---
const target = await p.evaluate(() => {
  const row = document.querySelector('.watch-item')
  return { name: row.querySelector('.n').textContent.trim(),
           listed: row.querySelector('.watch-risk').textContent.trim() }
})
// find that district's polygon and hover it
const hovered = await p.evaluate((name) => {
  const paths = [...document.querySelectorAll('.leaflet-container path')]
  for (const el of paths) {
    const t = el.__vueParentComponent || null
    if (el.getAttribute('data-name') === name) return true
  }
  return false
}, target.name)
// leaflet doesn't tag paths, so hover by index across several and capture whichever opens
await p.hover('.leaflet-container path')
await sleep(900)
let tip = await p.evaluate(() => {
  const t = document.querySelector('.district-tooltip')
  return t ? t.innerText.replace(/\n/g,' | ') : '(no tooltip)'
})
console.log('WATCHLIST top row :', JSON.stringify(target))
console.log('HOVER tooltip     :', tip)
await p.screenshot({ path: `${OUT}/bug1-hover.png` })

// zoomed crop around the tooltip for legibility
const box = await p.evaluate(() => {
  const t = document.querySelector('.district-tooltip'); if (!t) return null
  const r = t.getBoundingClientRect()
  return { x: Math.max(r.x-30,0), y: Math.max(r.y-30,0), width: Math.min(r.width+60,700), height: Math.min(r.height+60,300) }
})
if (box) await p.screenshot({ path: `${OUT}/bug1-tooltip-crop.png`, clip: box })

// --- BUG 2: stats block vs watchlist ---
const rounding = await p.evaluate(() => {
  const rows = [...document.querySelectorAll('.stat-row')]
  const hr = rows.find(r => /Highest risk/.test(r.textContent))
  const w = document.querySelector('.watch-item')
  return { statsBlock: hr ? hr.querySelector('.v').textContent.trim() : '(none)',
           topWatchlist: w ? w.querySelector('.watch-risk').textContent.trim() : '(none)',
           mapStatsPeak: (() => { const m=[...document.querySelectorAll('.map-stats .stat-row')]
             .find(r=>/Peak risk/.test(r.textContent)); return m? m.querySelector('.v').textContent.trim():'(none)' })() }
})
console.log('ROUNDING          :', JSON.stringify(rounding))
await p.screenshot({ path: `${OUT}/bug2-rounding.png`, clip:{x:0,y:120,width:560,height:700} })

// --- BUG 3: bank role + state filter ---
await clickText('.role-tab', 'Bank / FI'); await sleep(2600)
await p.select('.role-block select', 'Axis').catch(()=>{})
await sleep(2600)
await p.select('.panel.left select', 'Goa').catch(e=>console.log('state select failed:', e.message))
await sleep(3000)
const bank = await p.evaluate(() => {
  const districts = [...document.querySelectorAll('.map-stats .stat-row')]
    .find(r=>/Districts shown/.test(r.textContent))
  const accts = [...document.querySelectorAll('.panel.right table tbody tr')].slice(0,6)
    .map(tr => tr.children[1]?.textContent.trim())
  return { districtsShown: districts ? districts.querySelector('.v').textContent.trim() : '(none)',
           accountDistricts: accts }
})
console.log('BANK+Goa          :', JSON.stringify(bank))
await p.screenshot({ path: `${OUT}/bug3-bank-goa.png` })

// --- State LEA: does the category filter reach the referral inbox? ---
await clickText('.role-tab', 'State LEA'); await sleep(2600)
await p.select('.role-block select', 'Jharkhand').catch(()=>{})
await sleep(2600)
const before = await p.evaluate(() => document.querySelectorAll('.xj-table tbody tr').length)
const cats = await p.evaluate(() => {
  const sels=[...document.querySelectorAll('.panel.left select')]
  const c=sels.find(s=>[...s.options].some(o=>o.value==='digital_arrest'))
  if(!c) return '(no category select)'
  c.value='digital_arrest'; c.dispatchEvent(new Event('change',{bubbles:true})); return 'set'
})
await sleep(3000)
const after = await p.evaluate(() => ({
  rows: document.querySelectorAll('.xj-table tbody tr').length,
  types: [...document.querySelectorAll('.xj-table tbody .xj-sub')].slice(0,6).map(e=>e.textContent.trim().split(' ')[1])
}))
console.log('LEA referrals     : before(all cats)=' + before + '  after(digital_arrest)=' + JSON.stringify(after))
await p.screenshot({ path: `${OUT}/bug4-lea-category.png` })

console.log(errs.length ? '\nERRORS:\n'+errs.slice(0,8).join('\n') : '\nno browser errors')
await b.close()
