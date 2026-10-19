import { useEffect, useRef, useState } from 'react'
import { useEditor } from '../editor'
import { pdfjs, toPdfPoint, toPdfRect, toViewBox, type PageViewport } from '../pdf'
import type { Gesture, PageInfo, Point } from '../types'
import { AnnotPopover } from './AnnotPopover'

/** Pages currently mounted, so selections and scrolling can find them. */
export const pageRegistry = new Map<number, { el: HTMLElement; viewport: PageViewport | null }>()

interface Props {
  info: PageInfo
  version: number
}

export function PageView({ info, version }: Props) {
  const ed = useEditor()
  const { pdf, zoom } = ed
  const index = info.index
  const boxRef = useRef<HTMLDivElement>(null)
  const canvasHost = useRef<HTMLDivElement>(null)
  const textHost = useRef<HTMLDivElement>(null)
  // The first pages render immediately; the rest when scrolled near.
  const [visible, setVisible] = useState(index < 3)
  const [viewport, setViewport] = useState<PageViewport | null>(null)

  useEffect(() => {
    const el = boxRef.current!
    pageRegistry.set(index, { el, viewport: null })
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { rootMargin: '600px 0px' })
    io.observe(el)
    return () => {
      io.disconnect()
      pageRegistry.delete(index)
    }
  }, [index])

  useEffect(() => {
    // The rendered document can briefly lag behind a page-count change.
    if (!visible || !pdf || index >= pdf.numPages) return
    let cancelled = false
    let task: ReturnType<pdfjs.PDFPageProxy['render']> | null = null
    let textLayer: pdfjs.TextLayer | null = null
    ;(async () => {
      const page = await pdf.getPage(index + 1)
      if (cancelled) return
      const vp = page.getViewport({ scale: zoom })
      const ratio = window.devicePixelRatio || 1
      const canvas = document.createElement('canvas')
      canvas.width = Math.floor(vp.width * ratio)
      canvas.height = Math.floor(vp.height * ratio)
      canvas.style.width = `${vp.width}px`
      canvas.style.height = `${vp.height}px`
      const ctx = canvas.getContext('2d')!
      task = page.render({
        canvasContext: ctx, canvas, viewport: vp,
        transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined,
        annotationMode: pdfjs.AnnotationMode.ENABLE,
      })
      try {
        await task.promise
      } catch (e) {
        if (e instanceof pdfjs.RenderingCancelledException) return
        throw e
      }
      if (cancelled) return
      canvasHost.current?.replaceChildren(canvas)
      setViewport(vp)
      pageRegistry.set(index, { el: boxRef.current!, viewport: vp })
      const host = textHost.current!
      host.replaceChildren()
      textLayer = new pdfjs.TextLayer({ textContentSource: page.streamTextContent(), container: host, viewport: vp })
      await textLayer.render()
    })().catch((e) => console.error('render failed', e))
    return () => {
      cancelled = true
      task?.cancel()
      textLayer?.cancel()
    }
  }, [visible, pdf, index, zoom, version])

  const rotated = info.rotation % 180 !== 0
  const w = viewport?.width ?? (rotated ? info.height : info.width) * zoom
  const h = viewport?.height ?? (rotated ? info.width : info.height) * zoom
  const tool = ed.tool
  const annots = ed.info?.annotations.filter((a) => a.page === index && a.reply_to === null) ?? []
  const hits = ed.hits.filter((x) => x.page === index)
  const selected = annots.find((a) => a.xref === ed.selectedAnnot)

  return (
    <div
      ref={boxRef}
      className={`page ${ed.page === index ? 'current' : ''}`}
      data-page={index}
      style={{
        width: w, height: h,
        ['--total-scale-factor' as string]: zoom,
        ['--scale-round-x' as string]: '1px',
        ['--scale-round-y' as string]: '1px',
      }}
    >
      <div ref={canvasHost} className="canvas-host" />
      <div ref={textHost} className="textLayer" />
      {viewport && (
        <>
          {hits.map((hit, i) => (
            <div key={i} className="search-hit" style={toViewBox(viewport, hit.rect)} />
          ))}
          {!tool &&
            annots.map((a) => (
              <div
                key={a.xref}
                className={`annot-hit ${a.xref === ed.selectedAnnot ? 'selected' : ''}`}
                style={toViewBox(viewport, a.rect)}
                title={`${a.type}${a.contents ? ': ' + a.contents : ''}`}
                onClick={(e) => {
                  e.stopPropagation()
                  ed.setSelectedAnnot(a.xref)
                }}
              />
            ))}
          {!tool && selected && <AnnotPopover annot={selected} viewport={viewport} />}
          {tool?.Layer && <tool.Layer page={index} viewport={viewport} />}
          {tool && tool.gesture !== 'none' && tool.gesture !== 'text' && (
            <GestureLayer page={index} viewport={viewport} />
          )}
        </>
      )}
      <div className="page-label">{info.label}</div>
    </div>
  )
}

function GestureLayer({ page, viewport }: { page: number; viewport: PageViewport }) {
  const ed = useEditor()
  const tool = ed.tool!
  const ref = useRef<HTMLDivElement>(null)
  const [band, setBand] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null)
  const [strokes, setStrokesState] = useState<Point[][]>([])
  const strokesRef = useRef<Point[][]>([])
  const setStrokes = (next: Point[][]) => {
    strokesRef.current = next
    setStrokesState(next)
  }
  const [poly, setPoly] = useState<Point[]>([])
  const inkTimer = useRef<number | undefined>(undefined)
  const drawing = useRef(false)

  const local = (e: React.PointerEvent | React.MouseEvent): Point => {
    const r = ref.current!.getBoundingClientRect()
    return [e.clientX - r.left, e.clientY - r.top]
  }

  const fire = (g: Gesture) => {
    Promise.resolve(tool.onGesture?.(g, ed)).catch((err) => ed.notify(String(err.message ?? err), 'error'))
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setPoly([])
        setBand(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const onDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return
    const [x, y] = local(e)
    ref.current!.setPointerCapture(e.pointerId)
    drawing.current = true
    if (tool.gesture === 'drag' || tool.gesture === 'click') setBand({ x0: x, y0: y, x1: x, y1: y })
    if (tool.gesture === 'ink') {
      window.clearTimeout(inkTimer.current)
      setStrokes([...strokesRef.current, [[x, y]]])
    }
  }

  const onMove = (e: React.PointerEvent) => {
    if (!drawing.current) return
    const [x, y] = local(e)
    if (band) setBand({ ...band, x1: x, y1: y })
    if (tool.gesture === 'ink') {
      const copy = strokesRef.current.slice()
      copy[copy.length - 1] = [...copy[copy.length - 1], [x, y]]
      setStrokes(copy)
    }
  }

  const onUp = (e: React.PointerEvent) => {
    if (!drawing.current) return
    drawing.current = false
    const [x, y] = local(e)
    if (tool.gesture === 'click') {
      setBand(null)
      fire({ kind: 'click', page, point: toPdfPoint(viewport, x, y) })
    } else if (tool.gesture === 'drag' && band) {
      setBand(null)
      let { x0, y0 } = band
      let x1 = x, y1 = y
      if (Math.abs(x1 - x0) < 4 && Math.abs(y1 - y0) < 4) {
        // A plain click makes a default-sized box.
        x1 = x0 + 180 * ed.zoom
        y1 = y0 + 40 * ed.zoom
      }
      fire({
        kind: 'drag', page, rect: toPdfRect(viewport, x0, y0, x1, y1),
        start: toPdfPoint(viewport, x0, y0), end: toPdfPoint(viewport, x1, y1),
      })
    } else if (tool.gesture === 'ink') {
      window.clearTimeout(inkTimer.current)
      inkTimer.current = window.setTimeout(() => {
        const pdfStrokes = strokesRef.current
          .filter((st) => st.length > 1)
          .map((st) => st.map(([sx, sy]) => toPdfPoint(viewport, sx, sy)))
        setStrokes([])
        if (pdfStrokes.length) fire({ kind: 'ink', page, strokes: pdfStrokes })
      }, 700)
    }
  }

  const onClick = (e: React.MouseEvent) => {
    if (tool.gesture !== 'poly') return
    setPoly((p) => [...p, local(e)])
  }

  const onDouble = (e: React.MouseEvent) => {
    if (tool.gesture !== 'poly') return
    e.preventDefault()
    const pts = [...poly]
    setPoly([])
    if (pts.length >= 2) fire({ kind: 'poly', page, points: pts.map(([px, py]) => toPdfPoint(viewport, px, py)) })
  }

  return (
    <div
      ref={ref}
      className="gesture-layer"
      style={{ cursor: tool.cursor ?? 'crosshair' }}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onClick={onClick}
      onDoubleClick={onDouble}
    >
      <svg width="100%" height="100%">
        {band && tool.gesture === 'drag' && (
          <rect
            x={Math.min(band.x0, band.x1)} y={Math.min(band.y0, band.y1)}
            width={Math.abs(band.x1 - band.x0)} height={Math.abs(band.y1 - band.y0)}
            className="band"
          />
        )}
        {strokes.map((s, i) => (
          <polyline key={i} points={s.map((p) => p.join(',')).join(' ')} className="ink-preview" />
        ))}
        {poly.length > 0 && <polyline points={poly.map((p) => p.join(',')).join(' ')} className="poly-preview" />}
      </svg>
    </div>
  )
}
