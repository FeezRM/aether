import { useEffect, useRef } from 'react'
import { useEditor } from '../editor'
import { toPdfRect } from '../pdf'
import type { Rect } from '../types'
import { PageView, pageRegistry } from './PageView'

export function Viewer() {
  const ed = useEditor()
  const scroller = useRef<HTMLDivElement>(null)
  const edRef = useRef(ed)
  edRef.current = ed
  const info = ed.info!

  // Track the page nearest the top of the viewport as the current page.
  useEffect(() => {
    const el = scroller.current!
    let raf = 0
    const onScroll = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        const top = el.getBoundingClientRect().top + el.clientHeight * 0.3
        let best = 0
        for (const [i, { el: pe }] of pageRegistry) {
          if (pe.getBoundingClientRect().top <= top) best = Math.max(best, i)
        }
        if (best !== edRef.current.page) edRef.current.setPage(best)
      })
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  // Text-selection tools (highlight, redact text, ...) act when the mouse is released.
  const tool = ed.tool
  useEffect(() => {
    if (tool?.gesture !== 'text') return
    const onUp = () => {
      const ed = edRef.current
      const sel = window.getSelection()
      if (!sel || sel.isCollapsed) return
      const text = sel.toString()
      const byPage = new Map<number, Rect[]>()
      for (let r = 0; r < sel.rangeCount; r++) {
        for (const cr of Array.from(sel.getRangeAt(r).getClientRects())) {
          if (cr.width < 1 || cr.height < 1) continue
          const cx = cr.left + cr.width / 2, cy = cr.top + cr.height / 2
          for (const [i, { el, viewport }] of pageRegistry) {
            const b = el.getBoundingClientRect()
            if (viewport && cx >= b.left && cx <= b.right && cy >= b.top && cy <= b.bottom) {
              const rect = toPdfRect(viewport, cr.left - b.left, cr.top - b.top, cr.right - b.left, cr.bottom - b.top)
              byPage.set(i, [...(byPage.get(i) ?? []), rect])
              break
            }
          }
        }
      }
      sel.removeAllRanges()
      for (const [page, rects] of byPage) {
        Promise.resolve(tool.onGesture?.({ kind: 'text', page, rects: mergeLines(rects), text }, ed)).catch((e) =>
          ed.notify(String(e.message ?? e), 'error'),
        )
      }
    }
    document.addEventListener('mouseup', onUp)
    return () => document.removeEventListener('mouseup', onUp)
  }, [tool])

  return (
    <div
      ref={scroller}
      className={`viewer ${ed.tool?.gesture === 'text' ? 'text-tool' : ''}`}
      onClick={() => ed.setSelectedAnnot(null)}
    >
      {info.pages.map((p) => (
        <PageView key={p.index} info={p} version={info.version} />
      ))}
    </div>
  )
}

/** Join selection fragments that sit on the same line into one rectangle each. */
function mergeLines(rects: Rect[]): Rect[] {
  const sorted = [...rects].sort((a, b) => b[1] - a[1] || a[0] - b[0])
  const out: Rect[] = []
  for (const r of sorted) {
    const last = out[out.length - 1]
    const sameLine = last && Math.abs(last[1] - r[1]) < 3 && Math.abs(last[3] - r[3]) < 3 && r[0] - last[2] < 6
    if (sameLine) {
      out[out.length - 1] = [Math.min(last[0], r[0]), Math.min(last[1], r[1]), Math.max(last[2], r[2]), Math.max(last[3], r[3])]
    } else out.push(r)
  }
  return out
}
