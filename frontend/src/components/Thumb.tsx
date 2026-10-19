import { useEffect, useRef, useState } from 'react'
import { useEditor } from '../editor'
import { pdfjs } from '../pdf'

/** A lazily rendered page thumbnail of the given width. */
export function Thumb({ index, width }: { index: number; width: number }) {
  const ed = useEditor()
  const host = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(index < 6)
  const info = ed.info!.pages[index]
  const rotated = info.rotation % 180 !== 0
  const aspect = rotated ? info.width / info.height : info.height / info.width

  useEffect(() => {
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { rootMargin: '300px' })
    io.observe(host.current!)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    if (!visible || !ed.pdf || index >= ed.pdf.numPages) return
    let cancelled = false
    let task: pdfjs.RenderTask | null = null
    ed.pdf.getPage(index + 1).then(async (page) => {
      if (cancelled) return
      const base = page.getViewport({ scale: 1 })
      const vp = page.getViewport({ scale: (width / base.width) * (window.devicePixelRatio || 1) })
      const canvas = document.createElement('canvas')
      canvas.width = vp.width
      canvas.height = vp.height
      canvas.style.width = `${width}px`
      task = page.render({ canvasContext: canvas.getContext('2d')!, canvas, viewport: vp })
      try {
        await task.promise
        if (!cancelled) host.current?.replaceChildren(canvas)
      } catch {
        /* cancelled */
      }
    })
    return () => {
      cancelled = true
      task?.cancel()
    }
  }, [visible, ed.pdf, index, width, ed.info?.version])

  return <div ref={host} className="thumb" style={{ width, height: width * aspect }} />
}
