<script lang="ts">
  import { onMount, untrack, type Snippet } from 'svelte'
  import { api } from '$lib/api'
  import type { Detection, LocalModel } from '$lib/types'
  import { BottomSheet, Button, Field, IconButton, Kbd, Segmented, Select, Slider, Spinner, Toggle, clamp, mobile, toast, tooltip } from '$lib/ui'
  import { Mask, boundary, flood, process, type Rect } from './mask'
  import { smartSelect } from './smart'

  type Fill = 'original' | 'noise' | 'blur'
  type Tool = 'brush' | 'eraser' | 'smart' | 'smartsub' | 'wand' | 'detect'
  export type MaskResult = { maskId: string; denoise: number; maskBlur: number; padding: number; onlyMasked: boolean; fill: Fill }
  type Preview = 'tint' | 'outline' | 'mask' | 'result'
  type Det = Detection & { id: number; rect: Rect; seg: Uint8ClampedArray | null; used: boolean }
  type P = { x: number; y: number; p: number }

  let {
    imageId,
    imageUrl,
    width,
    height,
    onapply,
    oncancel,
    embedded = false,
    settings,
    bar,
    stage,
    onbounds,
  }: {
    imageId: string
    imageUrl: string
    width: number
    height: number
    onapply?: (r: MaskResult) => void
    oncancel?: () => void
    // renders in the page instead of covering the viewport
    embedded?: boolean
    // replaces the built-in denoise / fill section of the panel
    settings?: Snippet
    // extra header controls (left of Apply)
    bar?: Snippet
    // overlay inside the image stage, in image pixels
    stage?: Snippet<[number]>
    // bounding box of the mask (after grow), null when empty
    onbounds?: (r: Rect | null) => void
  } = $props()

  const W = untrack(() => width)
  const H = untrack(() => height)
  const mask = new Mask(W, H)

  let tool = $state<Tool>('brush')
  let size = $state(Math.max(4, Math.round(Math.max(W, H) / 20)))
  let hardness = $state(0.7)
  let pressure = $state(true)
  let tolerance = $state(24)
  let snap = $state(0.6)
  let smartPts = $state<{ x: number; y: number }[]>([])
  let smartSub = $state(false)
  let smartBusy = $state(false)
  let altDown = $state(false)
  let peek = $state(false)
  let help = $state(false)
  let panels = $state(true)
  let hud = $state<{ x: number; y: number } | null>(null)
  let lastPt: { x: number; y: number } | null = null
  let preview = $state<Preview>('tint')
  let opacity = $state(0.55)
  let tint = $state('--tag-copyright')
  let growPx = $state(0)
  let feather = $state(0)

  let denoise = $state(0.6)
  let maskBlur = $state(4)
  let padding = $state(32)
  let onlyMasked = $state(true)
  let fill = $state<Fill>('original')

  let detectors = $state<LocalModel[]>([])
  let detector = $state('')
  let confidence = $state(0.3)
  let detections = $state<Det[]>([])
  let detecting = $state(false)
  let subtract = $state(false)
  let hoverDet = $state<number | null>(null)

  let tx = $state(0)
  let ty = $state(0)
  let scale = $state(1)
  let userView = false
  let spaceDown = $state(false)
  let panning = $state(false)
  let cursor = $state<{ x: number; y: number } | null>(null)
  let hist = $state(0)
  let applying = $state(false)
  let sheet = $state(false)

  let vp: HTMLDivElement
  let ov: HTMLCanvasElement
  let img: HTMLImageElement
  let octx: CanvasRenderingContext2D | null = null
  let buf: ImageData | null = null
  let u32: Uint32Array | null = null
  let full = true
  let stale = true
  let lastProc = 0
  let lastAnt = 0
  let phase = 0
  let edges: Int32Array = new Int32Array(0)
  let edgeBox: Rect | null = null
  let painting = false
  let pixels: Uint8ClampedArray | null = null

  mask.onhistory = () => hist++

  const canUndo = $derived.by(() => (void hist, mask.canUndo))
  const canRedo = $derived.by(() => (void hist, mask.canRedo))
  const brushy = $derived(tool === 'brush' || tool === 'eraser')
  const smarty = $derived(tool === 'smart' || tool === 'smartsub')
  const sized = $derived(brushy || smarty)
  const tints = ['--tag-copyright', '--danger', '--accent']

  const tools: { value: Tool; label: string; icon: string; key: string }[] = [
    { value: 'brush', label: 'Brush', icon: 'brush', key: 'B' },
    { value: 'eraser', label: 'Eraser', icon: 'ink_eraser', key: 'E' },
    { value: 'smart', label: 'Smart brush', icon: 'gesture', key: 'W' },
    { value: 'smartsub', label: 'Smart brush, remove', icon: 'gesture_select', key: 'Alt W' },
    { value: 'wand', label: 'Magic wand', icon: 'auto_fix_high', key: 'Shift W' },
    { value: 'detect', label: 'Detect', icon: 'frame_person', key: 'D' },
  ]
  const shortcuts: [string, string][] = [
    ['[ / ]', 'Brush size'],
    ['Shift [ / ]', 'Hardness'],
    ['Alt right drag', 'Size (sideways), hardness (up/down)'],
    ['Alt', 'Hold to remove / erase'],
    ['Shift click', 'Straight line from last point'],
    ['X', 'Swap add and remove'],
    ['Space drag', 'Pan'],
    ['Ctrl 0 / F', 'Fit'],
    ['Ctrl 1', '100%'],
    ['Ctrl + / -', 'Zoom'],
    ['Ctrl Z / Ctrl Shift Z', 'Undo / redo'],
    ['Ctrl D', 'Clear mask'],
    ['Ctrl A', 'Fill mask'],
    ['Ctrl Shift I', 'Invert mask'],
    ['Q', 'Next mask view'],
    ['H', 'Hold to hide mask'],
    ['Tab', 'Hide panels'],
  ]
  const previews = [
    { value: 'tint' as Preview, label: 'Overlay', icon: 'layers' },
    { value: 'outline' as Preview, label: 'Outline', icon: 'highlight_alt' },
    { value: 'mask' as Preview, label: 'Mask', icon: 'contrast' },
    { value: 'result' as Preview, label: 'Edge', icon: 'blur_on' },
  ]
  const fills = [
    { value: 'original' as Fill, label: 'Original' },
    { value: 'noise' as Fill, label: 'Noise' },
    { value: 'blur' as Fill, label: 'Blur' },
  ]

  function rgb(token: string): number {
    const c = document.createElement('canvas')
    c.width = c.height = 1
    const x = c.getContext('2d')!
    x.fillStyle = getComputedStyle(document.documentElement).getPropertyValue(token).trim() || '#fff'
    x.fillRect(0, 0, 1, 1)
    const [r, g, b] = x.getImageData(0, 0, 1, 1).data
    return (b << 16) | (g << 8) | r
  }

  let tintRGB = 0
  let scrimRGB = 0
  let antA = 0
  let antB = 0

  $effect(() => {
    tintRGB = rgb(tint)
    full = true
  })
  $effect(() => {
    void preview
    full = true
    stale = true
  })
  $effect(() => {
    void growPx, feather, maskBlur
    if (preview === 'result') stale = true
  })
  $effect(() => {
    void scale
    if (preview === 'outline') stale = true
  })

  function renderRect(r: Rect) {
    if (!u32) return
    const d = mask.data
    const a = u32
    if (preview === 'mask') {
      for (let y = r.y0; y < r.y1; y++)
        for (let i = y * W + r.x0, e = y * W + r.x1; i < e; i++) {
          const v = d[i]
          a[i] = 0xff000000 | (v << 16) | (v << 8) | v
        }
    } else {
      const c = tintRGB
      for (let y = r.y0; y < r.y1; y++)
        for (let i = y * W + r.x0, e = y * W + r.x1; i < e; i++) {
          const v = d[i]
          a[i] = v ? ((v << 24) | c) >>> 0 : 0
        }
    }
    octx!.putImageData(buf!, 0, 0, r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0)
  }

  function renderResult() {
    if (!u32) return
    const p = process(mask.data, W, H, growPx, Math.hypot(feather, maskBlur))
    const c = scrimRGB
    for (let i = 0; i < p.length; i++) {
      const v = p[i]
      u32[i] = v === 255 ? 0 : ((Math.round((255 - v) * 0.78) << 24) | c) >>> 0
    }
    octx!.putImageData(buf!, 0, 0)
  }

  function computeEdges() {
    edges = boundary(mask.data, W, H)
    let x0 = W, y0 = H, x1 = 0, y1 = 0
    for (let k = 0; k < edges.length; k++) {
      const i = edges[k]
      const x = i % W
      const y = (i - x) / W
      if (x < x0) x0 = x
      if (x > x1) x1 = x
      if (y < y0) y0 = y
      if (y > y1) y1 = y
    }
    const prev = edgeBox
    edgeBox = edges.length ? { x0, y0, x1: x1 + 1, y1: y1 + 1 } : null
    if (prev) {
      clearRect(prev)
    }
  }

  function clearRect(r: Rect) {
    for (let y = r.y0; y < r.y1; y++) u32!.fill(0, y * W + r.x0, y * W + r.x1)
    octx!.putImageData(buf!, 0, 0, r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0)
  }

  function drawAnts() {
    if (!u32) return
    const t = Math.max(1, Math.round(1.5 / scale))
    const per = Math.max(3, Math.round(5 / scale))
    const b = edgeBox
    if (!b) return
    const r = { x0: Math.max(0, b.x0 - t), y0: Math.max(0, b.y0 - t), x1: Math.min(W, b.x1 + t), y1: Math.min(H, b.y1 + t) }
    for (let y = r.y0; y < r.y1; y++) u32.fill(0, y * W + r.x0, y * W + r.x1)
    const h = t >> 1
    for (let k = 0; k < edges.length; k++) {
      const i = edges[k]
      const x = i % W
      const y = (i - x) / W
      const col = (Math.floor((x + y + phase) / per) & 1) === 0 ? antA : antB
      for (let yy = Math.max(0, y - h); yy < Math.min(H, y - h + t); yy++)
        for (let xx = Math.max(0, x - h); xx < Math.min(W, x - h + t); xx++) u32[yy * W + xx] = col
    }
    octx!.putImageData(buf!, 0, 0, r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0)
  }

  function frame(now: number) {
    if (!octx) return
    if (preview === 'tint' || preview === 'mask') {
      if (full) {
        full = false
        mask.dirty = null
        renderRect({ x0: 0, y0: 0, x1: W, y1: H })
      } else if (mask.dirty) {
        const r = mask.dirty
        mask.dirty = null
        renderRect(r)
      }
    } else if (preview === 'outline') {
      if (full) {
        full = false
        u32!.fill(0)
        octx.putImageData(buf!, 0, 0)
        edgeBox = null
      }
      if (mask.dirty) {
        mask.dirty = null
        stale = true
      }
      if (stale && now - lastProc > (painting ? 90 : 0)) {
        stale = false
        lastProc = now
        computeEdges()
        drawAnts()
      } else if (now - lastAnt > 110) {
        lastAnt = now
        phase = (phase + 1) % 1000
        drawAnts()
      }
    } else {
      if (mask.dirty) {
        mask.dirty = null
        stale = true
      }
      if ((stale || full) && now - lastProc > (painting ? 220 : 40)) {
        stale = full = false
        renderResult()
        lastProc = performance.now()
      }
    }
  }

  function fit() {
    if (!vp) return
    const pad = mobile.current ? 8 : 24
    const cw = vp.clientWidth - pad * 2
    const ch = vp.clientHeight - pad * 2
    const s = Math.max(0.01, Math.min(cw / W, ch / H))
    scale = s
    tx = (vp.clientWidth - W * s) / 2
    ty = (vp.clientHeight - H * s) / 2
    userView = false
  }

  function zoomAt(sx: number, sy: number, ns: number) {
    ns = clamp(ns, 0.02, 40)
    tx = sx - ((sx - tx) * ns) / scale
    ty = sy - ((sy - ty) * ns) / scale
    scale = ns
    userView = true
  }

  function local(e: { clientX: number; clientY: number }) {
    const r = vp.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }
  const toImg = (l: { x: number; y: number }) => ({ x: (l.x - tx) / scale, y: (l.y - ty) / scale })

  onMount(() => {
    octx = ov.getContext('2d', { willReadFrequently: false })
    buf = octx!.createImageData(W, H)
    u32 = new Uint32Array(buf.data.buffer)
    scrimRGB = rgb('--bg')
    antA = (0xff000000 | rgb('--accent-strong')) >>> 0
    antB = (0xff000000 | rgb('--bg')) >>> 0
    let raf = 0
    const loop = (t: number) => {
      frame(t)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    const ro = new ResizeObserver(() => {
      if (!userView) fit()
    })
    ro.observe(vp)
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      const l = local(e)
      const k = e.ctrlKey ? 0.01 : e.deltaMode === 1 ? 0.05 : 0.0018
      zoomAt(l.x, l.y, scale * Math.exp(-e.deltaY * k))
    }
    vp.addEventListener('wheel', wheel, { passive: false })
    api
      .models('detector')
      .then((m) => {
        detectors = m
        detector =
          m.find((d) => d.id.includes('face_yolov8m'))?.id ?? m.find((d) => /face/i.test(d.id))?.id ?? m[0]?.id ?? ''
      })
      .catch(() => {})
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      vp.removeEventListener('wheel', wheel)
    }
  })

  const pointers = new Map<number, { x: number; y: number }>()
  let gesture: 'none' | 'paint' | 'pan' | 'pinch' | 'wait' = 'none'
  let panFrom = { x: 0, y: 0, tx: 0, ty: 0 }
  let pinch = { cx: 0, cy: 0, d: 1, s: 1, tx: 0, ty: 0 }
  let stroke: { pts: P[]; next: number; erase: boolean; pen: boolean } | null = null

  const radiusAt = (p: number) => Math.max(0.5, (size / 2) * (stroke?.pen && pressure ? 0.15 + 0.85 * p : 1))
  const spacing = (r: number) => Math.max(0.6, r * 0.2)

  function stampAt(q: P) {
    mask.stamp(q.x, q.y, radiusAt(q.p), hardness, stroke!.erase)
  }

  function walk(poly: P[]) {
    const s = stroke!
    for (let k = 1; k < poly.length; k++) {
      const a = poly[k - 1]
      const b = poly[k]
      const L = Math.hypot(b.x - a.x, b.y - a.y)
      if (L === 0) continue
      let pos = 0
      let u = s.next
      while (pos + u <= L) {
        pos += u
        const t = pos / L
        const q = { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, p: a.p + (b.p - a.p) * t }
        stampAt(q)
        u = spacing(radiusAt(q.p))
      }
      s.next = u - (L - pos)
    }
  }

  const mid = (a: P, b: P): P => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, p: (a.p + b.p) / 2 })

  function quad(a: P, c: P, b: P): P[] {
    const len = Math.hypot(c.x - a.x, c.y - a.y) + Math.hypot(b.x - c.x, b.y - c.y)
    const n = clamp(Math.ceil(len / 3), 1, 64)
    const out: P[] = []
    for (let i = 0; i <= n; i++) {
      const t = i / n
      const u = 1 - t
      out.push({
        x: u * u * a.x + 2 * u * t * c.x + t * t * b.x,
        y: u * u * a.y + 2 * u * t * c.y + t * t * b.y,
        p: u * u * a.p + 2 * u * t * c.p + t * t * b.p,
      })
    }
    return out
  }

  function addPoint(q: P) {
    const s = stroke!
    const last = s.pts[s.pts.length - 1]
    if (last && Math.hypot(q.x - last.x, q.y - last.y) < 0.5) return
    s.pts.push(q)
    if (s.pts.length === 2) walk([s.pts[0], mid(s.pts[0], s.pts[1])])
    else if (s.pts.length >= 3) {
      const [a, b, c] = s.pts.slice(-3)
      walk(quad(mid(a, b), b, mid(b, c)))
      s.pts.splice(0, s.pts.length - 2)
    }
  }

  function endStroke() {
    const s = stroke
    if (!s) return
    if (s.pts.length >= 2) {
      const [a, b] = s.pts.slice(-2)
      walk([mid(a, b), b])
    }
    stroke = null
    painting = false
    mask.commit()
  }

  function pressureOf(e: PointerEvent) {
    return e.pointerType === 'pen' ? (e.pressure || 0.5) : 1
  }

  function hitDet(x: number, y: number): Det | null {
    let best: Det | null = null
    let area = Infinity
    for (const d of detections) {
      const r = d.rect
      if (x < r.x0 || y < r.y0 || x >= r.x1 || y >= r.y1) continue
      if (d.seg) {
        const v = d.seg[(Math.floor(y) - r.y0) * (r.x1 - r.x0) + (Math.floor(x) - r.x0)]
        if (v < 128) continue
      }
      const a = (r.x1 - r.x0) * (r.y1 - r.y0)
      if (a < area) {
        area = a
        best = d
      }
    }
    return best
  }

  let gesture2: 'none' | 'smart' | 'resize' = 'none'
  let resizeFrom = { x: 0, y: 0, size: 0, hardness: 0 }
  let smartTimer = 0
  let smartLast = 0
  let smartDelay = 90

  function smartRun(final: boolean) {
    if (!img.complete || !smartPts.length) return
    const r = smartSelect(imagePixels(), W, H, smartPts, size / 2, {
      edges: snap,
      res: final ? 512 : 256,
      mask: mask.committed,
      subtract: smartSub,
    })
    mask.revert()
    if (!r) return
    const rw = r.rect.x1 - r.rect.x0
    const al = r.alpha
    mask.combine((x, y) => al[(y - r.rect.y0) * rw + (x - r.rect.x0)], r.rect, smartSub)
  }

  function smartTick() {
    smartTimer = 0
    if (gesture2 !== 'smart') return
    const t0 = performance.now()
    smartRun(false)
    smartLast = performance.now()
    // back off on slow machines so painting stays smooth
    smartDelay = clamp((smartLast - t0) * 2, 60, 400)
  }

  function smartAdd(p: { x: number; y: number }) {
    const last = smartPts[smartPts.length - 1]
    if (last && Math.hypot(p.x - last.x, p.y - last.y) < Math.max(1, size * 0.15)) return
    smartPts.push(p)
    if (!smartTimer) smartTimer = window.setTimeout(smartTick, Math.max(0, smartDelay - (performance.now() - smartLast)))
  }

  function smartStop() {
    clearTimeout(smartTimer)
    smartTimer = 0
    gesture2 = 'none'
    painting = false
  }

  async function smartEnd() {
    smartStop()
    smartBusy = true
    // let the spinner paint before the heavier final pass
    await new Promise((r) => setTimeout(r, 16))
    try {
      smartRun(true)
      mask.commit()
    } finally {
      smartBusy = false
      smartPts = []
    }
  }

  function down(e: PointerEvent) {
    const l = local(e)
    // photoshop style on-canvas resize: alt + right drag (or ctrl + alt + left drag)
    if (sized && e.pointerType !== 'touch' && e.altKey && (e.button === 2 || (e.button === 0 && (e.ctrlKey || e.metaKey)))) {
      e.preventDefault()
      try {
        vp.setPointerCapture(e.pointerId)
      } catch {}
      pointers.set(e.pointerId, l)
      gesture2 = 'resize'
      resizeFrom = { x: l.x, y: l.y, size, hardness }
      hud = { x: l.x, y: l.y }
      return
    }
    if (e.button === 2 || smartBusy) return
    try {
      vp.setPointerCapture(e.pointerId)
    } catch {}
    pointers.set(e.pointerId, l)
    if (e.pointerType === 'touch' && pointers.size === 2) {
      if (gesture === 'paint') {
        stroke = null
        painting = false
        mask.revert()
      }
      if (gesture2 === 'smart') {
        smartStop()
        smartPts = []
        mask.revert()
      }
      const [a, b] = [...pointers.values()]
      pinch = { cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2, d: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)), s: scale, tx, ty }
      gesture = 'pinch'
      return
    }
    if (pointers.size > 1) return
    e.preventDefault()
    if (e.button === 1 || spaceDown) {
      gesture = 'pan'
      panning = true
      panFrom = { x: l.x, y: l.y, tx, ty }
      return
    }
    const p = toImg(l)
    const sub = subtract || e.altKey || e.shiftKey
    if (smarty) {
      gesture = 'wait'
      gesture2 = 'smart'
      painting = true
      smartSub = (tool === 'smartsub') !== e.altKey
      smartPts = []
      smartLast = 0
      smartAdd(p)
      return
    }
    if (brushy) {
      gesture = 'paint'
      painting = true
      stroke = { pts: [], next: 0, erase: (tool === 'eraser') !== e.altKey, pen: e.pointerType === 'pen' }
      const q = { x: p.x, y: p.y, p: pressureOf(e) }
      if (e.shiftKey && lastPt) {
        // straight line from the previous stroke end
        const a = { x: lastPt.x, y: lastPt.y, p: q.p }
        stroke.pts.push(a)
        stampAt(a)
        stroke.next = spacing(radiusAt(a.p))
        walk([a, q])
        stroke.pts = [q]
        return
      }
      stroke.pts.push(q)
      stampAt(q)
      stroke.next = spacing(radiusAt(q.p))
      return
    }
    if (tool === 'wand') {
      wand(p.x, p.y, sub)
      gesture = 'wait'
      return
    }
    const d = hitDet(p.x, p.y)
    if (d) {
      addDet(d, sub)
      gesture = 'wait'
    } else {
      gesture = 'pan'
      panning = true
      panFrom = { x: l.x, y: l.y, tx, ty }
    }
  }

  function move(e: PointerEvent) {
    const l = local(e)
    if (e.pointerType !== 'touch' && gesture2 !== 'resize') cursor = l
    if (!pointers.has(e.pointerId)) return
    pointers.set(e.pointerId, l)
    if (gesture2 === 'resize') {
      const maxSize = Math.min(2048, Math.max(256, Math.round(Math.max(W, H) / 2)))
      size = clamp(Math.round(resizeFrom.size + ((l.x - resizeFrom.x) * 2) / scale), 1, maxSize)
      hardness = clamp(Math.round((resizeFrom.hardness - (l.y - resizeFrom.y) / 200) * 100) / 100, 0, 1)
      return
    }
    if (gesture === 'pinch' && pointers.size >= 2) {
      const [a, b] = [...pointers.values()]
      const cx = (a.x + b.x) / 2
      const cy = (a.y + b.y) / 2
      const d = Math.max(1, Math.hypot(a.x - b.x, a.y - b.y))
      const ns = clamp((pinch.s * d) / pinch.d, 0.02, 40)
      tx = cx - ((pinch.cx - pinch.tx) * ns) / pinch.s
      ty = cy - ((pinch.cy - pinch.ty) * ns) / pinch.s
      scale = ns
      userView = true
    } else if (gesture === 'pan') {
      tx = panFrom.tx + l.x - panFrom.x
      ty = panFrom.ty + l.y - panFrom.y
      userView = true
    } else if (gesture2 === 'smart') {
      smartAdd(toImg(l))
    } else if (gesture === 'paint' && stroke) {
      const evs = e.getCoalescedEvents?.() ?? []
      for (const ev of evs.length ? evs : [e]) {
        const p = toImg(local(ev))
        addPoint({ x: p.x, y: p.y, p: pressureOf(ev) })
      }
    }
  }

  function up(e: PointerEvent) {
    if (!pointers.delete(e.pointerId)) return
    if (gesture2 === 'resize') {
      gesture2 = 'none'
      hud = null
      cursor = local(e)
      return
    }
    if (gesture2 === 'smart') smartEnd()
    if (gesture === 'paint') {
      const last = stroke?.pts[stroke.pts.length - 1]
      if (last) lastPt = { x: last.x, y: last.y }
      endStroke()
    }
    if (gesture === 'pinch') {
      gesture = pointers.size ? 'wait' : 'none'
      return
    }
    if (!pointers.size) {
      gesture = 'none'
      panning = false
    }
  }

  function isTyping(t: EventTarget | null) {
    const el = t as HTMLElement | null
    return !!el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))
  }

  function zoomCenter(f: number) {
    const r = vp.getBoundingClientRect()
    zoomAt(r.width / 2, r.height / 2, f === 0 ? 1 : scale * f)
  }

  function cancelStroke() {
    if (gesture === 'paint') {
      stroke = null
      painting = false
      mask.revert()
      gesture = 'wait'
    } else if (gesture2 === 'smart') {
      smartStop()
      smartPts = []
      mask.revert()
    }
  }

  function keydown(e: KeyboardEvent) {
    if (isTyping(e.target) || applying || !vp?.isConnected) return
    // only one editor handles keys when an embedded one sits under the modal one
    if (embedded && document.querySelector('.inpainter:not(.embedded)')) return
    const mod = e.ctrlKey || e.metaKey
    const k = e.key.toLowerCase()
    if (e.key === 'Alt') {
      e.preventDefault()
      altDown = true
      return
    }
    if (k === ' ') {
      e.preventDefault()
      spaceDown = true
      return
    }
    if (k === 'escape' && (gesture === 'paint' || gesture2 === 'smart')) {
      e.preventDefault()
      e.stopPropagation()
      cancelStroke()
      return
    }
    if (mod && k === 'z') {
      e.preventDefault()
      if (e.shiftKey) mask.redo()
      else mask.undo()
      return
    }
    if (mod && k === 'y') {
      e.preventDefault()
      mask.redo()
      return
    }
    if (mod) {
      if (k === '0') fit()
      else if (k === '1') zoomCenter(0)
      else if (k === '=' || k === '+') zoomCenter(1.25)
      else if (k === '-') zoomCenter(0.8)
      else if (k === 'd') clearAll()
      else if (k === 'a') fillAll()
      else if (k === 'i' && e.shiftKey) invert()
      else return
      e.preventDefault()
      return
    }
    if (k === '[' || k === ']' || k === '{' || k === '}') {
      const bigger = k === ']' || k === '}'
      if (e.shiftKey) hardness = clamp(Math.round((hardness + (bigger ? 0.1 : -0.1)) * 10) / 10, 0, 1)
      else size = clamp(Math.round(size * (bigger ? 1.15 : 1 / 1.15) + (bigger ? 1 : -1)), 1, 2048)
    } else if (k === 'b') tool = 'brush'
    else if (k === 'e') tool = 'eraser'
    else if (k === 'w') tool = e.shiftKey ? 'wand' : e.altKey ? 'smartsub' : 'smart'
    else if (k === 'd') tool = 'detect'
    else if (k === 'x')
      tool = ({ brush: 'eraser', eraser: 'brush', smart: 'smartsub', smartsub: 'smart' } as Partial<Record<Tool, Tool>>)[tool] ?? tool
    else if (k === 'f') fit()
    else if (k === 'i' && e.shiftKey) invert()
    else if (k === 'q') preview = previews[(previews.findIndex((p) => p.value === preview) + 1) % previews.length].value
    else if (k === 'h') peek = true
    else if (k === 'tab') panels = !panels
    else if (k === '?' || (k === '/' && e.shiftKey)) help = !help
    else if (k === 'escape' && help) help = false
    else return
    e.preventDefault()
  }

  function keyup(e: KeyboardEvent) {
    if (e.key === 'Alt') {
      altDown = false
      e.preventDefault()
    }
    if (e.key.toLowerCase() === 'h') peek = false
    if (e.key === ' ') {
      spaceDown = false
      if (!isTyping(e.target)) e.preventDefault()
    }
  }

  function invert() {
    const d = mask.data
    const n = new Uint8ClampedArray(d.length)
    for (let i = 0; i < d.length; i++) n[i] = 255 - d[i]
    mask.replace(n)
  }
  function fillAll() {
    mask.replace(new Uint8ClampedArray(W * H).fill(255))
  }
  function clearAll() {
    if (mask.isEmpty()) return
    mask.replace(new Uint8ClampedArray(W * H))
  }

  function imagePixels(): Uint8ClampedArray {
    if (pixels) return pixels
    const c = document.createElement('canvas')
    c.width = W
    c.height = H
    const x = c.getContext('2d', { willReadFrequently: true })!
    x.drawImage(img, 0, 0, W, H)
    pixels = x.getImageData(0, 0, W, H).data
    return pixels
  }

  function wand(x: number, y: number, sub: boolean) {
    if (!img.complete) return
    const r = flood(imagePixels(), W, H, x, y, tolerance)
    if (!r) return
    const ex = { x0: Math.max(0, r.rect.x0 - 1), y0: Math.max(0, r.rect.y0 - 1), x1: Math.min(W, r.rect.x1 + 1), y1: Math.min(H, r.rect.y1 + 1) }
    const d = r.data
    const soft = (px: number, py: number) => {
      const i = py * W + px
      if (d[i]) return 255
      const n = (px > 0 ? d[i - 1] : 0) + (px < W - 1 ? d[i + 1] : 0) + (py > 0 ? d[i - W] : 0) + (py < H - 1 ? d[i + W] : 0)
      return n ? 128 : 0
    }
    mask.combine(soft, ex, sub)
    mask.commit()
  }

  async function loadSeg(url: string, r: Rect): Promise<Uint8ClampedArray | null> {
    try {
      const im = new Image()
      im.src = url
      await im.decode()
      const c = document.createElement('canvas')
      c.width = r.x1 - r.x0
      c.height = r.y1 - r.y0
      const x = c.getContext('2d', { willReadFrequently: true })!
      x.drawImage(im, -r.x0, -r.y0, W, H)
      const px = x.getImageData(0, 0, c.width, c.height).data
      const out = new Uint8ClampedArray(c.width * c.height)
      for (let i = 0; i < out.length; i++) out[i] = px[i * 4]
      return out
    } catch {
      return null
    }
  }

  async function runDetect() {
    if (!detector || detecting) return
    if (!imageId) return toast.info('Image is still loading')
    detecting = true
    try {
      const res = await api.detect(imageId, detector, confidence)
      const out: Det[] = []
      let id = 0
      for (const d of res) {
        const m = d.maskUrl ? 3 : 0
        const rect = {
          x0: clamp(Math.floor(d.bbox[0]) - m, 0, W),
          y0: clamp(Math.floor(d.bbox[1]) - m, 0, H),
          x1: clamp(Math.ceil(d.bbox[2]) + m, 0, W),
          y1: clamp(Math.ceil(d.bbox[3]) + m, 0, H),
        }
        if (rect.x1 <= rect.x0 || rect.y1 <= rect.y0) continue
        const seg = d.maskUrl ? await loadSeg(d.maskUrl, rect) : null
        out.push({ ...d, id: id++, rect, seg, used: false })
      }
      detections = out
      tool = 'detect'
      if (!out.length) toast.info('Nothing found', { description: 'Try a lower confidence or another detector.' })
    } catch (e) {
      toast.error('Detection failed', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      detecting = false
    }
  }

  function addDet(d: Det, sub = subtract, commit = true) {
    const r = d.rect
    const rw = r.x1 - r.x0
    const seg = d.seg
    mask.combine(seg ? (x, y) => seg[(y - r.y0) * rw + (x - r.x0)] : () => 255, r, sub)
    if (commit) mask.commit()
    const i = detections.findIndex((x) => x.id === d.id)
    if (i >= 0) detections[i].used = !sub
  }

  function addAll() {
    for (const d of detections) addDet(d, subtract, false)
    mask.commit()
  }

  function segOutline(node: HTMLCanvasElement, d: Det) {
    const r = d.rect
    const w = r.x1 - r.x0
    const h = r.y1 - r.y0
    node.width = w
    node.height = h
    const x = node.getContext('2d')!
    const im = x.createImageData(w, h)
    const a = new Uint32Array(im.data.buffer)
    const s = d.seg!
    const line = (0xff000000 | rgb('--accent-strong')) >>> 0
    const fillc = ((0x38 << 24) | rgb('--accent-strong')) >>> 0
    const t = 2
    for (let yy = 0; yy < h; yy++)
      for (let xx = 0; xx < w; xx++) {
        const i = yy * w + xx
        if (s[i] < 128) continue
        let edge = false
        for (let k = 1; k <= t && !edge; k++)
          edge = xx < k || yy < k || xx >= w - k || yy >= h - k || s[i - k] < 128 || s[i + k] < 128 || s[i - k * w] < 128 || s[i + k * w] < 128
        a[i] = edge ? line : fillc
      }
    x.putImageData(im, 0, 0)
  }

  // uploads the processed mask; null (with a toast) when it is empty
  export async function exportMask(): Promise<string | null> {
    if (mask.isEmpty()) {
      toast.info('Mask is empty', { description: 'Paint or detect the area to repaint.' })
      return null
    }
    const out = process(mask.data, W, H, growPx, feather)
    const c = document.createElement('canvas')
    c.width = W
    c.height = H
    const x = c.getContext('2d')!
    const im = x.createImageData(W, H)
    const a = new Uint32Array(im.data.buffer)
    for (let i = 0; i < out.length; i++) {
      const v = out[i]
      a[i] = (0xff000000 | (v << 16) | (v << 8) | v) >>> 0
    }
    x.putImageData(im, 0, 0)
    const blob = await new Promise<Blob | null>((res) => c.toBlob(res, 'image/png'))
    if (!blob) throw new Error('could not encode mask')
    return (await api.upload(blob, 'mask.png')).id
  }

  export function fitView() {
    fit()
  }

  export function focusRect(r: Rect) {
    if (!vp) return
    const pad = 40
    const s = clamp(Math.min((vp.clientWidth - pad * 2) / (r.x1 - r.x0), (vp.clientHeight - pad * 2) / (r.y1 - r.y0)), 0.02, 40)
    scale = s
    tx = vp.clientWidth / 2 - ((r.x0 + r.x1) / 2) * s
    ty = vp.clientHeight / 2 - ((r.y0 + r.y1) / 2) * s
    userView = true
  }

  function bounds(): Rect | null {
    const d = mask.data
    let x0 = W, y0 = H, x1 = -1, y1 = -1
    for (let y = 0; y < H; y++) {
      const row = y * W
      for (let x = 0; x < W; x++)
        if (d[row + x] > 127) {
          if (x < x0) x0 = x
          if (x > x1) x1 = x
          if (y < y0) y0 = y
          if (y > y1) y1 = y
        }
    }
    if (x1 < 0) return null
    const g = Math.max(0, growPx)
    return { x0: Math.max(0, x0 - g), y0: Math.max(0, y0 - g), x1: Math.min(W, x1 + 1 + g), y1: Math.min(H, y1 + 1 + g) }
  }

  $effect(() => {
    void hist, growPx
    if (onbounds) onbounds(untrack(bounds))
  })

  $effect(() => {
    void imageUrl
    pixels = null
  })

  async function apply() {
    if (applying || !onapply) return
    applying = true
    try {
      const id = await exportMask()
      if (id) onapply({ maskId: id, denoise, maskBlur, padding, onlyMasked, fill })
    } catch (e) {
      toast.error('Could not save mask', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      applying = false
    }
  }

  const pct = (v: number) => `${Math.round(v * 100)}%`
  const px = (v: number) => `${v}px`
  const shortName = (m: LocalModel) => m.name.replace(/\s*\((bbox|segm)\)\s*$/, '')
  const detItems = $derived(
    detectors.map((m) => ({ value: m.id, label: shortName(m), hint: m.id.includes('segm/') ? 'segm' : 'bbox' })),
  )
  const ring = $derived(Math.max(4, size * scale))
  const showRing = $derived(sized && !!cursor && !spaceDown && !panning)
  const removing = $derived(
    tool === 'eraser' || tool === 'smartsub' ? !altDown : (tool === 'brush' || tool === 'smart') && altDown,
  )
  const vcursor = $derived(
    panning ? 'grabbing' : spaceDown ? 'grab' : sized ? 'none' : tool === 'wand' ? 'crosshair' : 'default',
  )
  const smartPath = $derived(smartPts.map((p) => `${p.x},${p.y}`).join(' '))
  const pixelated = $derived(scale >= 2)
</script>

<svelte:window onkeydown={keydown} onkeyup={keyup} onblur={() => (spaceDown = false)} />

{#snippet toolSettings()}
  {#if brushy}
    <Field label="Size" info="[ and ] change size. Shift with [ ] changes hardness.">
      {#snippet children(id)}
        <Slider {id} label="Size" bind:value={size} min={1} max={Math.min(1024, Math.max(256, Math.round(Math.max(W, H) / 3)))} step={1} defaultValue={Math.max(4, Math.round(Math.max(W, H) / 20))} editable />
      {/snippet}
    </Field>
    <Field label="Hardness">
      {#snippet children(id)}
        <Slider {id} label="Hardness" bind:value={hardness} min={0} max={1} step={0.05} defaultValue={0.7} editable format={pct} />
      {/snippet}
    </Field>
    <Toggle bind:checked={pressure} label="Pen pressure" size="sm" />
  {:else if smarty}
    <Field label="Size" info="Paint over what you want. The selection snaps to edges. Alt paints the opposite way.">
      {#snippet children(id)}
        <Slider {id} label="Size" bind:value={size} min={1} max={Math.min(1024, Math.max(256, Math.round(Math.max(W, H) / 3)))} step={1} editable />
      {/snippet}
    </Field>
    <Field label="Edge snap" info="Higher stops the selection at weaker edges.">
      {#snippet children(id)}
        <Slider {id} label="Edge snap" bind:value={snap} min={0} max={1} step={0.05} defaultValue={0.6} editable format={pct} />
      {/snippet}
    </Field>
    <Segmented
      items={[{ value: 'smart', label: 'Add', icon: 'add' }, { value: 'smartsub', label: 'Remove', icon: 'remove' }]}
      bind:value={() => tool, (v) => (tool = v as Tool)}
      full
      size="sm"
    />
  {:else if tool === 'wand'}
    <Field label="Tolerance" info="Click to select a region of similar color. Alt or shift click removes it.">
      {#snippet children(id)}
        <Slider {id} label="Tolerance" bind:value={tolerance} min={1} max={128} step={1} defaultValue={24} editable />
      {/snippet}
    </Field>
  {/if}
{/snippet}

{#snippet detectSection()}
  <div class="row">
    <Select items={detItems} bind:value={detector} placeholder="Detector" label="Detector" size="sm" style="flex: 1; min-width: 0" />
    <Button size="sm" icon="center_focus_strong" loading={detecting} disabled={!detector} onclick={runDetect}>Detect</Button>
  </div>
  <Field label="Confidence" info="Click a detection on the image to add it to the mask. Alt or shift click subtracts.">
    {#snippet children(id)}
      <Slider {id} label="Confidence" bind:value={confidence} min={0.05} max={0.95} step={0.05} defaultValue={0.3} editable format={pct} />
    {/snippet}
  </Field>
  {#if detections.length}
    <div class="dets">
      {#each detections as d (d.id)}
        <button
          class="det"
          class:used={d.used}
          onclick={(e) => addDet(d, subtract || e.altKey || e.shiftKey)}
          onpointerenter={() => (hoverDet = d.id)}
          onpointerleave={() => (hoverDet = null)}
        >
          <span class="icon">{d.used ? 'check_box' : d.seg ? 'gesture' : 'crop_free'}</span>
          <span class="dl">{d.label}</span>
          <span class="dc">{pct(d.confidence)}</span>
        </button>
      {/each}
    </div>
    <div class="row">
      <Button size="sm" icon={subtract ? 'remove_selection' : 'select_all'} onclick={addAll}>{subtract ? 'Subtract all' : 'Add all'}</Button>
      <Toggle bind:checked={subtract} label="Subtract" size="sm" />
    </div>
  {/if}
{/snippet}

{#snippet panel()}
  {#if mobile.current}
    <section>
      <Segmented items={previews} bind:value={preview} full size="sm" />
    </section>
  {/if}
  {#if sized || tool === 'wand'}
    <section>{@render toolSettings()}</section>
  {/if}
  {#if settings}{@render settings()}{/if}
  <section>{@render detectSection()}</section>
  <section>
    {#if preview === 'tint'}
      <Field label="Overlay">
        {#snippet children(id)}
          <div class="row">
            <Slider {id} label="Overlay opacity" bind:value={opacity} min={0.1} max={1} step={0.05} defaultValue={0.55} format={pct} style="flex: 1" />
            {#each tints as t (t)}
              <button class="swatch" class:on={tint === t} style="--c: var({t})" aria-label="Overlay color" onclick={() => (tint = t)}></button>
            {/each}
          </div>
        {/snippet}
      </Field>
    {/if}
    <Field label="Grow" info="Expands (or shrinks, below zero) the mask before it is applied.">
      {#snippet children(id)}
        <Slider {id} label="Grow" bind:value={growPx} min={-64} max={64} step={1} defaultValue={0} editable format={px} />
      {/snippet}
    </Field>
    <Field label="Feather" info="Softens the exported mask edge. Preview it with the edge view.">
      {#snippet children(id)}
        <Slider {id} label="Feather" bind:value={feather} min={0} max={64} step={1} defaultValue={0} editable format={px} />
      {/snippet}
    </Field>
    <div class="row actions">
      <Button size="sm" variant="ghost" icon="invert_colors" onclick={invert}>Invert</Button>
      <Button size="sm" variant="ghost" icon="format_color_fill" onclick={fillAll}>Fill</Button>
      <Button size="sm" variant="danger" icon="delete" onclick={clearAll}>Clear</Button>
    </div>
  </section>
  {#if !settings}
  <section>
    <Field label="Denoise" info="How much the masked area changes. 0.4 to 0.7 keeps the composition.">
      {#snippet children(id)}
        <Slider {id} label="Denoise" bind:value={denoise} min={0} max={1} step={0.01} defaultValue={0.6} editable />
      {/snippet}
    </Field>
    <Field label="Mask blur" info="Blend radius between the repainted area and the original.">
      {#snippet children(id)}
        <Slider {id} label="Mask blur" bind:value={maskBlur} min={0} max={64} step={1} defaultValue={4} editable format={px} />
      {/snippet}
    </Field>
    <Toggle bind:checked={onlyMasked} label="Only masked area" size="sm" />
    {#if onlyMasked}
      <Field label="Padding" info="Context around the mask that is rendered at full resolution.">
        {#snippet children(id)}
          <Slider {id} label="Padding" bind:value={padding} min={0} max={256} step={4} defaultValue={32} editable format={px} />
        {/snippet}
      </Field>
    {/if}
    <Field label="Masked content" info="What fills the masked area before denoising. Original works for most edits, noise for replacing things.">
      {#snippet children()}
        <Segmented items={fills} bind:value={fill} full size="sm" />
      {/snippet}
    </Field>
  </section>
  {/if}
{/snippet}

<div class="inpainter" class:embedded class:is-mobile={mobile.current}>
  <header class="bar">
    {#if oncancel}
      <IconButton icon="close" label="Cancel" onclick={oncancel} />
      <div class="sep"></div>
    {/if}
    <IconButton icon="undo" label="Undo (Ctrl+Z)" disabled={!canUndo} onclick={() => mask.undo()} />
    <IconButton icon="redo" label="Redo (Ctrl+Shift+Z)" disabled={!canRedo} onclick={() => mask.redo()} />
    {#if !mobile.current}
      <div class="sep"></div>
      <Segmented items={previews} bind:value={preview} iconOnly size="sm" />
      <div class="grow"></div>
      <button class="zoom" use:tooltip={'100%'} onclick={() => { const r = vp.getBoundingClientRect(); zoomAt(r.width / 2, r.height / 2, 1) }}>{Math.round(scale * 100)}%</button>
      <IconButton icon="fit_screen" label="Fit (F)" onclick={fit} />
      <IconButton icon="keyboard" label="Shortcuts (?)" active={help} onclick={() => (help = !help)} />
    {:else}
      <div class="grow"></div>
      <IconButton icon="fit_screen" label="Fit" onclick={fit} />
    {/if}
    {#if bar}{@render bar()}{/if}
    {#if onapply}
      <Button variant="primary" icon="check" loading={applying} onclick={apply}>Apply</Button>
    {/if}
  </header>

  <div class="main">
    {#if !mobile.current && panels}
      <nav class="tools">
        {#each tools as t (t.value)}
          <IconButton icon={t.icon} label="{t.label} ({t.key})" active={tool === t.value} tip="right" onclick={() => (tool = t.value)} />
        {/each}
      </nav>
    {/if}

    <div
      class="viewport"
      bind:this={vp}
      style:cursor={vcursor}
      onpointerdown={down}
      onpointermove={move}
      onpointerup={up}
      onpointercancel={up}
      onpointerleave={(e) => { if (e.pointerType !== 'touch') cursor = null }}
      oncontextmenu={(e) => e.preventDefault()}
      role="application"
      aria-label="Mask canvas"
    >
      <div class="stage" class:pixelated style="width: {W}px; height: {H}px; transform: translate({tx}px, {ty}px) scale({scale})">
        <img bind:this={img} src={imageUrl} alt="" draggable="false" width={W} height={H} />
        <canvas
          bind:this={ov}
          width={W}
          height={H}
          class="overlay"
          style:opacity={peek ? 0 : preview === 'tint' ? opacity : 1}
        ></canvas>
        {#if smartPts.length}
          <svg class="smartline" class:sub={smartSub} viewBox="0 0 {W} {H}" width={W} height={H}>
            <polyline points={smartPath} style="stroke-width: {Math.max(2 / scale, size * 0.5)}px" />
            <polyline class="core" points={smartPath} style="stroke-width: {1.5 / scale}px" />
          </svg>
        {/if}
        {#if stage}{@render stage(scale)}{/if}
        {#if tool === 'detect' || hoverDet !== null}
          {#each detections as d (d.id)}
            {#if tool === 'detect' || hoverDet === d.id}
              {#if d.seg}
                <canvas
                  class="seg"
                  class:hot={hoverDet === d.id}
                  use:segOutline={d}
                  style="left: {d.rect.x0}px; top: {d.rect.y0}px; width: {d.rect.x1 - d.rect.x0}px; height: {d.rect.y1 - d.rect.y0}px"
                ></canvas>
              {/if}
            {/if}
          {/each}
          <svg class="boxes" viewBox="0 0 {W} {H}" width={W} height={H}>
            {#each detections as d (d.id)}
              {#if tool === 'detect' || hoverDet === d.id}
                <g class:hot={hoverDet === d.id} class:used={d.used} class:segm={!!d.seg}>
                  <rect class="under" x={d.bbox[0]} y={d.bbox[1]} width={d.bbox[2] - d.bbox[0]} height={d.bbox[3] - d.bbox[1]} />
                  <rect class="line" x={d.bbox[0]} y={d.bbox[1]} width={d.bbox[2] - d.bbox[0]} height={d.bbox[3] - d.bbox[1]} />
                </g>
              {/if}
            {/each}
          </svg>
          {#each detections as d (d.id)}
            {#if tool === 'detect' || hoverDet === d.id}
              <span class="tag" style="left: {d.bbox[0]}px; top: {d.bbox[1]}px; transform: scale({1 / scale})">{d.label} {pct(d.confidence)}</span>
            {/if}
          {/each}
        {/if}
      </div>
      {#if showRing && cursor}
        <div class="ring" class:sub={removing} class:smart={smarty} style="left: {cursor.x}px; top: {cursor.y}px; width: {ring}px; height: {ring}px">
          {#if hardness < 0.95 && ring > 14}
            <div class="inner" style="width: {Math.max(2, ring * hardness)}px; height: {Math.max(2, ring * hardness)}px"></div>
          {/if}
        </div>
      {/if}
      {#if hud}
        <div class="ring hud" style="left: {hud.x}px; top: {hud.y}px; width: {ring}px; height: {ring}px">
          {#if hardness < 0.95 && ring > 14}
            <div class="inner" style="width: {Math.max(2, ring * hardness)}px; height: {Math.max(2, ring * hardness)}px"></div>
          {/if}
        </div>
        <div class="hudlbl" style="left: {hud.x}px; top: {hud.y + ring / 2 + 10}px">{size}px, {pct(hardness)}</div>
      {/if}
      {#if detecting || smartBusy}
        <div class="busy"><Spinner size={16} /></div>
      {/if}
      {#if help}
        <div class="help" role="dialog" aria-label="Shortcuts">
          <div class="hh">
            <span>Shortcuts</span>
            <IconButton icon="close" label="Close" size="sm" tip={false} onclick={() => (help = false)} />
          </div>
          <dl>
            {#each tools as t (t.value)}
              <dt><Kbd>{t.key}</Kbd></dt>
              <dd>{t.label}</dd>
            {/each}
            {#each shortcuts as [k, v] (k)}
              <dt><Kbd>{k}</Kbd></dt>
              <dd>{v}</dd>
            {/each}
          </dl>
        </div>
      {/if}
    </div>

    {#if !mobile.current && panels}
      <aside class="panel">{@render panel()}</aside>
    {/if}
  </div>

  {#if mobile.current}
    <footer class="strip">
      {#each tools as t (t.value)}
        <IconButton icon={t.icon} label={t.label} active={tool === t.value} tip={false} onclick={() => (tool = t.value)} />
      {/each}
      <div class="strip-ctl">
        {#if sized}
          <Slider label="Size" bind:value={size} min={1} max={Math.min(1024, Math.max(256, Math.round(Math.max(W, H) / 3)))} step={1} editable={false} />
        {:else if tool === 'detect'}
          <Button size="sm" icon="center_focus_strong" loading={detecting} disabled={!detector} onclick={runDetect} full>Detect</Button>
        {/if}
      </div>
      <IconButton icon="tune" label="Settings" tip={false} onclick={() => (sheet = true)} />
    </footer>
    <BottomSheet bind:open={sheet} title="Mask" snaps={[0.55, 0.92]}>
      <div class="sheet-body">{@render panel()}</div>
    </BottomSheet>
  {/if}
</div>

<style>
  .inpainter {
    position: fixed;
    inset: 0;
    z-index: calc(var(--z-popover) - 1);
    display: flex;
    flex-direction: column;
    background: var(--bg);
    color: var(--text);
    user-select: none;
  }
  .inpainter.embedded {
    position: relative;
    inset: auto;
    z-index: auto;
    height: 100%;
    min-height: 0;
    background: transparent;
  }
  .smartline {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    overflow: visible;
  }
  .smartline polyline {
    fill: none;
    stroke: var(--success);
    stroke-opacity: 0.35;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .smartline polyline.core {
    stroke-opacity: 1;
  }
  .smartline.sub polyline {
    stroke: var(--danger);
  }
  .hud {
    border-style: solid;
  }
  .hudlbl {
    position: absolute;
    translate: -50% 0;
    padding: 2px 8px;
    border-radius: var(--r-sm);
    background: var(--grad-3);
    border: 1px solid var(--hairline);
    font-size: var(--fs-xs);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    pointer-events: none;
  }
  .help {
    position: absolute;
    top: var(--sp-3);
    right: var(--sp-3);
    width: 300px;
    max-height: calc(100% - 24px);
    overflow-y: auto;
    padding: var(--sp-2) var(--sp-3) var(--sp-3);
    border-radius: var(--r-lg);
    border: 1px solid var(--hairline);
    background: var(--grad-2);
    box-shadow: var(--sheen), var(--shadow-3);
    user-select: text;
  }
  .hh {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-weight: 600;
    font-size: var(--fs-sm);
    margin-bottom: var(--sp-2);
  }
  .help dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px var(--sp-3);
    margin: 0;
    font-size: var(--fs-sm);
  }
  .help dt {
    white-space: nowrap;
  }
  .help dd {
    margin: 0;
    color: var(--text-muted);
  }
  .bar {
    display: flex;
    align-items: center;
    gap: var(--sp-1);
    padding: var(--sp-2) var(--sp-3);
    border-bottom: 1px solid var(--hairline);
    background: var(--surface-1);
    min-height: 52px;
  }
  .sep {
    width: 1px;
    height: 20px;
    margin: 0 var(--sp-1);
    background: var(--hairline);
  }
  .grow {
    flex: 1;
  }
  .zoom {
    min-width: 52px;
    height: var(--control-h-sm);
    border: 0;
    border-radius: var(--r-sm);
    background: transparent;
    color: var(--text-muted);
    font: inherit;
    font-size: var(--fs-sm);
    font-variant-numeric: tabular-nums;
    cursor: pointer;
  }
  .zoom:hover {
    background: var(--hover);
    color: var(--text);
  }
  .main {
    flex: 1;
    min-height: 0;
    display: flex;
  }
  .tools {
    display: flex;
    flex-direction: column;
    gap: var(--sp-1);
    padding: var(--sp-2);
    border-right: 1px solid var(--hairline);
    background: var(--surface-1);
  }
  .viewport {
    position: relative;
    flex: 1;
    min-width: 0;
    overflow: hidden;
    touch-action: none;
    background: var(--bg);
  }
  .stage {
    position: absolute;
    left: 0;
    top: 0;
    transform-origin: 0 0;
    box-shadow: 0 0 0 1px var(--hairline), var(--shadow-3);
  }
  .stage img,
  .stage .overlay {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    display: block;
    pointer-events: none;
  }
  .stage.pixelated img,
  .stage.pixelated canvas {
    image-rendering: pixelated;
  }
  .seg {
    position: absolute;
    pointer-events: none;
    opacity: 0.55;
  }
  .seg.hot {
    opacity: 1;
  }
  .boxes {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    overflow: visible;
  }
  .boxes rect {
    fill: none;
    vector-effect: non-scaling-stroke;
  }
  .boxes .under {
    stroke: var(--scrim);
    stroke-width: 3.5;
  }
  .boxes .line {
    stroke: var(--accent);
    stroke-width: 1.5;
    stroke-dasharray: 6 4;
  }
  .boxes .segm .line {
    stroke-opacity: 0.5;
  }
  .boxes .used .line {
    stroke: var(--success);
    stroke-dasharray: none;
  }
  .boxes .hot .line {
    stroke: var(--accent-strong);
    stroke-width: 2.5;
    stroke-dasharray: none;
  }
  .tag {
    position: absolute;
    transform-origin: 0 100%;
    translate: 0 -100%;
    padding: 1px 6px;
    border-radius: var(--r-sm);
    background: var(--surface-3);
    border: 1px solid var(--hairline);
    color: var(--text);
    font-size: var(--fs-xs);
    white-space: nowrap;
    pointer-events: none;
  }
  .ring {
    position: absolute;
    translate: -50% -50%;
    border-radius: 50%;
    border: 1px solid var(--accent-strong);
    box-shadow: 0 0 0 1px var(--scrim), inset 0 0 0 1px var(--scrim);
    pointer-events: none;
    display: grid;
    place-items: center;
  }
  .ring > *,
  .ring::after {
    grid-area: 1 / 1;
  }
  .ring.smart {
    border-color: var(--success);
  }
  .ring.sub {
    border-color: var(--danger);
  }
  .ring.sub::after,
  .ring.smart::after {
    content: '';
    width: 6px;
    height: 1.5px;
    background: currentColor;
    color: var(--danger);
  }
  .ring.smart:not(.sub)::after {
    color: var(--success);
    box-shadow: none;
    width: 6px;
    height: 6px;
    background:
      linear-gradient(currentColor, currentColor) center / 6px 1.5px no-repeat,
      linear-gradient(currentColor, currentColor) center / 1.5px 6px no-repeat;
  }
  .ring .inner {
    border-radius: 50%;
    border: 1px dashed var(--accent);
    opacity: 0.6;
  }
  .busy {
    position: absolute;
    top: var(--sp-3);
    left: 50%;
    translate: -50% 0;
    padding: var(--sp-2);
    border-radius: var(--r-md);
    background: var(--surface-2);
    border: 1px solid var(--hairline);
    box-shadow: var(--shadow-2);
  }
  .panel {
    width: 300px;
    flex: none;
    overflow-y: auto;
    border-left: 1px solid var(--hairline);
    background: var(--surface-1);
  }
  section {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    padding: var(--sp-4);
    border-bottom: 1px solid var(--hairline);
  }
  section:last-child {
    border-bottom: 0;
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
  }
  .actions {
    justify-content: space-between;
  }
  .swatch {
    width: 20px;
    height: 20px;
    flex: none;
    border-radius: var(--r-sm);
    border: 1px solid var(--hairline);
    background: var(--c);
    cursor: pointer;
  }
  .swatch.on {
    box-shadow: var(--focus-ring);
  }
  .dets {
    display: flex;
    flex-direction: column;
    gap: 2px;
    max-height: 200px;
    overflow-y: auto;
  }
  .det {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    height: var(--control-h-sm);
    padding: 0 var(--sp-2);
    border: 0;
    border-radius: var(--r-sm);
    background: transparent;
    color: var(--text);
    font: inherit;
    font-size: var(--fs-sm);
    text-align: left;
    cursor: pointer;
  }
  .det:hover {
    background: var(--hover);
  }
  .det:active {
    background: var(--pressed);
  }
  .det .icon {
    font-size: 18px;
    color: var(--text-muted);
  }
  .det.used .icon {
    color: var(--success);
  }
  .dl {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .dc {
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }
  .strip {
    display: flex;
    align-items: center;
    gap: var(--sp-1);
    padding: var(--sp-2);
    padding-bottom: max(var(--sp-2), env(safe-area-inset-bottom));
    border-top: 1px solid var(--hairline);
    background: var(--surface-1);
  }
  .strip-ctl {
    flex: 1;
    min-width: 0;
    padding: 0 var(--sp-2);
  }
  .sheet-body section {
    padding: var(--sp-3) 0;
  }
  .is-mobile .bar {
    padding: var(--sp-1) var(--sp-2);
    padding-top: max(var(--sp-1), env(safe-area-inset-top));
  }
</style>
