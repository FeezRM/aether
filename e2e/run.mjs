// End-to-end walk through the main Acrobat-parity tools using real mouse/keyboard input.
// Usage: node run.mjs  (with the API and UI running; see README)
import { execFileSync } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import puppeteer from 'puppeteer-core'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
const DIR = mkdtempSync(join(tmpdir(), 'localpdf-e2e-')) + '/'
const SAMPLE = DIR + 'contract.pdf'
const OUT = DIR + 'saved-e2e.pdf'
const BASE = process.env.LOCALPDF_URL ?? 'http://127.0.0.1:5173/'
const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
execFileSync(join(ROOT, 'backend/.venv/bin/python'), [join(ROOT, 'e2e/make_sample.py'), SAMPLE])
console.log('artifacts in', DIR)
const results = []
const check = (name, ok, extra = '') => { results.push([ok ? 'PASS' : 'FAIL', name, extra]); console.log(ok ? 'PASS' : 'FAIL', name, extra) }

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true, defaultViewport: { width: 1440, height: 900 },
})
const page = await browser.newPage()
const errors = []
page.on('pageerror', (e) => errors.push(String(e)))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
page.on('dialog', (d) => d.accept())
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const shot = (name) => page.screenshot({ path: `${DIR}shot-${name}.png` })

async function clickText(selector, text) {
  const handles = await page.$$(selector)
  for (const h of handles) {
    const t = await h.evaluate((e) => e.textContent.trim())
    if (t === text || t.startsWith(text)) { await h.click(); return }
  }
  throw new Error(`No ${selector} with text ${text}`)
}
async function fillPrompt(values) {
  await page.waitForSelector('.modal')
  const inputs = await page.$$('.modal input:not([type=checkbox]), .modal textarea')
  for (let i = 0; i < values.length && i < inputs.length; i++) {
    if (values[i] === null) continue
    await inputs[i].click({ clickCount: 3 })
    await inputs[i].type(values[i])
  }
  await page.click('.modal button[type=submit]')
  await sleep(900)
}
async function pageBox(i) {
  return page.$eval(`.page[data-page="${i}"]`, (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height } })
}
async function scrollToPage(i) {
  await page.$eval(`.page[data-page="${i}"]`, (e) => e.scrollIntoView({ block: 'start' }))
  await sleep(500)
}
async function reveal(i, fy) {
  const b = await pageBox(i)
  const y = b.y + b.h * fy
  if (y < 120 || y > 820) {
    await page.$eval('.viewer', (v, d) => v.scrollBy(0, d), y - 450)
    await sleep(400)
  }
}
async function drag(i, fx0, fy0, fx1, fy1) {
  await reveal(i, (fy0 + fy1) / 2)
  const b = await pageBox(i)
  await page.mouse.move(b.x + b.w * fx0, b.y + b.h * fy0)
  await page.mouse.down()
  await page.mouse.move(b.x + b.w * (fx0 + fx1) / 2, b.y + b.h * (fy0 + fy1) / 2, { steps: 5 })
  await page.mouse.move(b.x + b.w * fx1, b.y + b.h * fy1, { steps: 5 })
  await page.mouse.up()
  await sleep(400)
}
async function clickPage(i, fx, fy) {
  await reveal(i, fy)
  const b = await pageBox(i)
  await page.mouse.click(b.x + b.w * fx, b.y + b.h * fy)
  await sleep(400)
}
const api = (path, init) => page.evaluate(async (p, i) => (await fetch(p, i)).json(), path, init)
let docId
const info = () => api(`/api/documents/${docId}`)
const pageText = async (i) => (await api(`/api/documents/${docId}/pages/${i}`)).blocks.map((b) => b.text).join('\n')
async function openGroup(label) {
  if (await page.$('.tools-panel button.link')) await page.click('.tools-panel button.link')
  await clickText('.tool-card .tool-name', label)
  await sleep(300)
}
async function useTool(label) {
  const active = await page.$eval('.tool-buttons', (e) => e.querySelector('button.active')?.textContent ?? '').catch(() => '')
  if (active !== label) await clickText('.tool-buttons button', label)
  await sleep(300)
}

try {
  await page.goto(BASE, { waitUntil: 'networkidle0' })
  await clickText('button', 'Open from a file path')
  await fillPrompt([SAMPLE])
  await page.waitForSelector('.page[data-page="0"] .canvas-host canvas', { timeout: 10000 })
  await page.waitForSelector('.page[data-page="0"] .textLayer span')
  docId = (await api('/api/documents')).at(-1).id
  check('open + render page with text layer', true)
  await shot('01-open')

  // Edit text in place (paragraph).
  await openGroup('Edit PDF')
  await page.waitForSelector('.page[data-page="0"] .text-line')
  const blocks = await page.$$('.page[data-page="0"] .text-line')
  await blocks[1].click()
  await page.waitForSelector('.inline-editor')
  await page.$eval('.inline-editor', (t) => t.select()) // headless macOS ignores Cmd+A
  await page.keyboard.type('This Agreement is made between Contoso Ltd ("Client") and Northwind Labs ("Provider"), effective immediately, and replaces all earlier drafts.')
  await page.keyboard.press('Enter')
  await sleep(1500)
  let t0 = await pageText(0)
  check('edit paragraph text', t0.includes('Contoso Ltd') && t0.includes('replaces all earlier drafts') && t0.split('entered into between Acme').length === 2 && t0.includes('1. Services'), t0.split('\n')[1])
  await shot('02-edit-text')

  // Add a new text block.
  await useTool('Add text')
  await drag(0, 0.55, 0.9, 0.9, 0.95)
  await fillPrompt(['Reviewed by Legal'])
  check('add text', (await pageText(0)).includes('Reviewed by Legal'))

  // Comments: highlight by real mouse selection, sticky note, rectangle, freehand.
  await openGroup('Comment')
  await useTool('Highlight')
  await page.$$eval('.page[data-page="0"] .textLayer span', (spans) =>
    spans.find((x) => x.textContent.includes('Fees and Payment')).scrollIntoView({ block: 'center' }))
  await sleep(600)
  const spanBox = await page.$$eval('.page[data-page="0"] .textLayer span', (spans) => {
    const s = spans.find((x) => x.textContent.includes('Fees and Payment'))
    const r = s.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }
  })
  await page.mouse.move(spanBox.x + 1, spanBox.y + spanBox.h / 2)
  await page.mouse.down()
  await page.mouse.move(spanBox.x + spanBox.w - 1, spanBox.y + spanBox.h / 2, { steps: 8 })
  await page.mouse.up()
  await sleep(1200)
  {
    const line = (await api(`/api/documents/${docId}/pages/0`)).lines.find((l) => l.text.includes('Fees and Payment'))
    const hl = (await info()).annotations.find((a) => a.type === 'Highlight')
    const overlap = hl && hl.rect[0] >= line.rect[0] - 4 && hl.rect[2] <= line.rect[2] + 4 &&
      hl.rect[1] < line.rect[3] && hl.rect[3] > line.rect[1]
    check('highlight lands on the selected words', Boolean(overlap), JSON.stringify({ hl: hl?.rect, line: line.rect }))
  }
  await useTool('Sticky note')
  await clickPage(0, 0.85, 0.3)
  await fillPrompt(['Check the payment terms'])
  await useTool('Rectangle')
  await drag(0, 0.1, 0.5, 0.4, 0.58)
  await useTool('Draw')
  await drag(0, 0.6, 0.6, 0.8, 0.65)
  await sleep(1200)
  let types = (await info()).annotations.map((a) => a.type)
  check('comments: highlight, note, rectangle, ink (one per gesture)', ['Highlight', 'Text', 'Square', 'Ink'].every((t) => types.includes(t)) && types.filter((t) => t === 'Ink').length === 1, types.join(','))
  await shot('03-comments')

  // Select a comment and reply through the popover.
  await page.keyboard.press('Escape') // back to select mode
  await sleep(300)
  await page.$eval('.annot-hit', (e) => e.scrollIntoView({ block: 'center' }))
  await page.click('.annot-hit')
  await page.waitForSelector('.annot-popover')
  await page.type('.annot-popover input:not([type=color])', 'Agreed')
  await clickText('.annot-popover button', 'Reply')
  await sleep(1000)
  check('reply to comment', (await info()).annotations.some((a) => a.reply_to && a.contents === 'Agreed'))

  // Redact SSN + email by pattern, then apply.
  await openGroup('Redact')
  await page.$$eval('label.check', (ls) => ls.filter((l) => /Social Security|Email addresses/.test(l.textContent)).forEach((l) => l.querySelector('input').click()))
  await clickText('button', 'Find and mark')
  await sleep(1200)
  await clickText('button', 'Apply redactions permanently')
  await sleep(1500)
  const fullText = (await page.evaluate(async (id) => (await fetch(`/api/documents/${id}/export/txt`)).text(), docId))
  check('redaction removes SSN and email only', !fullText.includes('123-45-6789') && !fullText.includes('legal@acme.example') && fullText.includes('dential Information secret'))
  await shot('04-redacted')

  // Forms: detect fields from "____" lines, then fill one in place.
  await openGroup('Prepare Form')
  await clickText('button', 'Auto-detect form fields')
  await sleep(1200)
  const fields = (await info()).fields
  check('auto-detect form fields', fields.length >= 2, fields.map((f) => f.name).join(','))
  await useTool('Fill form')
  await scrollToPage(fields[0].page)
  const input = await page.waitForSelector('.field-input')
  await input.click()
  await input.type('Jane Doe')
  await page.mouse.click(5, 300) // blur commits
  await sleep(1200)
  check('fill field in place', (await info()).fields.some((f) => f.value === 'Jane Doe'))

  // Fill & Sign: typed signature placed by dragging.
  await openGroup('Fill & Sign')
  await clickText('button', 'Type signature')
  await fillPrompt(['Jane Doe'])
  await scrollToPage(1)
  await drag(1, 0.55, 0.85, 0.9, 0.92)
  await sleep(800)
  check('typed signature placed', (await pageText(1)).includes('Jane Doe'))

  // Watermark + page numbers.
  await openGroup('Watermark & Header')
  await clickText('button', 'Add text watermark')
  await sleep(1000)
  await clickText('button', 'Add header & footer')
  await sleep(1000)
  const txt2 = await page.evaluate(async (id) => (await fetch(`/api/documents/${id}/export/txt`)).text(), docId)
  check('watermark and footer', txt2.includes('CONFIDENTIAL') && txt2.includes('Page 2 of 2'))

  // Organize: rotate page 2 from the grid, then insert a blank page.
  await openGroup('Organize Pages')
  await page.waitForSelector('.grid-item')
  const items = await page.$$('.grid-item')
  await items[1].click()
  await clickText('.btn-grid button', '⟳ Rotate right')
  await sleep(800)
  await clickText('.btn-grid button', 'Insert blank after')
  await sleep(800)
  const inf = await info()
  check('rotate + insert blank page', inf.pages[1].rotation === 90 && inf.page_count === 3)
  await shot('05-organize')

  // Undo the blank page.
  await page.keyboard.down('Meta'); await page.keyboard.press('KeyZ'); await page.keyboard.up('Meta')
  await sleep(800)
  check('undo (Cmd+Z)', (await info()).page_count === 2)

  // Search.
  await openGroup('Edit PDF')
  await page.click('.search input')
  await page.type('.search input', 'Termination')
  await page.keyboard.press('Enter')
  await sleep(800)
  check('search highlights hits', (await page.$$('.search-hit')).length > 0)

  // Local assistant: only when a model has been downloaded (see docs/AI.md).
  if (!(await api('/api/ai/models')).active) {
    console.log('SKIP assistant (no model downloaded)')
  } else {
    await openGroup('Ask AI')
    await page.type('.chat-input textarea', 'What is this document about?')
    await page.keyboard.press('Enter')
    await page.waitForSelector('.chat-msg.assistant:not([data-pending])', { timeout: 180_000 })
    const answer = await page.$eval('.chat-msg.assistant', (e) => e.textContent ?? '')
    check('assistant answers locally', answer.trim().length > 0 && !(await page.$('.chat-error')), answer.slice(0, 80))
    await shot('06-assistant')
  }

  // Save As to disk.
  await page.click('.topbar button:nth-of-type(3)')
  await fillPrompt([OUT])
  const saved = await info()
  check('save as to path', saved.source_path?.endsWith('saved-e2e.pdf') && !saved.dirty, saved.source_path)
  await shot('06-final')
} catch (e) {
  check('scenario crashed', false, String(e.stack ?? e))
  await shot('crash')
} finally {
  check('no console errors', errors.length === 0, errors.slice(0, 5).join(' | '))
  await browser.close()
  const failed = results.filter((r) => r[0] === 'FAIL').length
  console.log(`\n${results.length - failed}/${results.length} passed`)
  process.exit(failed ? 1 : 0)
}
