import * as pdfjs from 'pdfjs-dist'
import type { PageViewport, PDFDocumentProxy } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import type { Point, Rect } from './types'

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

export { pdfjs }
export type { PageViewport, PDFDocumentProxy }

export async function loadPdf(url: string): Promise<PDFDocumentProxy> {
  return pdfjs.getDocument({ url, enableXfa: false }).promise
}

/** Viewport (CSS px, top-left origin) -> PDF user space. */
export function toPdfPoint(vp: PageViewport, x: number, y: number): Point {
  const [px, py] = vp.convertToPdfPoint(x, y)
  return [round(px), round(py)]
}

export function toPdfRect(vp: PageViewport, x0: number, y0: number, x1: number, y1: number): Rect {
  const a = toPdfPoint(vp, x0, y0)
  const b = toPdfPoint(vp, x1, y1)
  return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])]
}

/** PDF rect -> CSS box {left, top, width, height} in viewport pixels. */
export function toViewBox(vp: PageViewport, r: Rect) {
  const [x0, y0] = vp.convertToViewportPoint(r[0], r[1])
  const [x1, y1] = vp.convertToViewportPoint(r[2], r[3])
  return {
    left: Math.min(x0, x1), top: Math.min(y0, y1),
    width: Math.abs(x1 - x0), height: Math.abs(y1 - y0),
  }
}

const round = (v: number) => Math.round(v * 100) / 100
