export type Rect = { x0: number; y0: number; x1: number; y1: number }

type Patch = { r: Rect; before: Uint8ClampedArray; after: Uint8ClampedArray }

const HISTORY_BYTES = 192 * 1024 * 1024

function union(a: Rect | null, b: Rect): Rect {
  if (!a) return { ...b }
  return { x0: Math.min(a.x0, b.x0), y0: Math.min(a.y0, b.y0), x1: Math.max(a.x1, b.x1), y1: Math.max(a.y1, b.y1) }
}

function crop(src: Uint8ClampedArray, w: number, r: Rect): Uint8ClampedArray {
  const rw = r.x1 - r.x0
  const out = new Uint8ClampedArray(rw * (r.y1 - r.y0))
  for (let y = r.y0; y < r.y1; y++) out.set(src.subarray(y * w + r.x0, y * w + r.x1), (y - r.y0) * rw)
  return out
}

function paste(dst: Uint8ClampedArray, w: number, r: Rect, data: Uint8ClampedArray) {
  const rw = r.x1 - r.x0
  for (let y = r.y0; y < r.y1; y++) dst.set(data.subarray((y - r.y0) * rw, (y - r.y0 + 1) * rw), y * w + r.x0)
}

export class Mask {
  readonly w: number
  readonly h: number
  data: Uint8ClampedArray
  private prev: Uint8ClampedArray
  private undos: Patch[] = []
  private redos: Patch[] = []
  private pend: Rect | null = null
  dirty: Rect | null = null
  version = 0
  onhistory?: () => void

  constructor(w: number, h: number) {
    this.w = w
    this.h = h
    this.data = new Uint8ClampedArray(w * h)
    this.prev = new Uint8ClampedArray(w * h)
  }

  // last committed state, without the stroke in progress
  get committed() {
    return this.prev
  }

  get canUndo() {
    return this.undos.length > 0
  }
  get canRedo() {
    return this.redos.length > 0
  }

  mark(x0: number, y0: number, x1: number, y1: number) {
    const r = {
      x0: Math.max(0, Math.floor(x0)),
      y0: Math.max(0, Math.floor(y0)),
      x1: Math.min(this.w, Math.ceil(x1)),
      y1: Math.min(this.h, Math.ceil(y1)),
    }
    if (r.x1 <= r.x0 || r.y1 <= r.y0) return
    this.dirty = union(this.dirty, r)
    this.pend = union(this.pend, r)
    this.version++
  }

  markAll() {
    this.mark(0, 0, this.w, this.h)
  }

  stamp(cx: number, cy: number, r: number, hardness: number, erase: boolean) {
    const { w, h, data } = this
    const inner = Math.max(0, Math.min(r * hardness, r - 1))
    const span = Math.max(1e-3, r - inner)
    const x0 = Math.max(0, Math.floor(cx - r))
    const x1 = Math.min(w - 1, Math.ceil(cx + r))
    const y0 = Math.max(0, Math.floor(cy - r))
    const y1 = Math.min(h - 1, Math.ceil(cy + r))
    if (x1 < x0 || y1 < y0) return
    const r2 = r * r
    const in2 = inner * inner
    for (let y = y0; y <= y1; y++) {
      const dy = y + 0.5 - cy
      const dy2 = dy * dy
      const row = y * w
      for (let x = x0; x <= x1; x++) {
        const dx = x + 0.5 - cx
        const d2 = dx * dx + dy2
        if (d2 >= r2) continue
        let v = 255
        if (d2 > in2) {
          const t = (r - Math.sqrt(d2)) / span
          v = 255 * t * t * (3 - 2 * t)
        }
        const i = row + x
        if (erase) {
          const e = 255 - v
          if (e < data[i]) data[i] = e
        } else if (v > data[i]) data[i] = v
      }
    }
    this.mark(x0, y0, x1 + 1, y1 + 1)
  }

  combine(src: Uint8ClampedArray | ((x: number, y: number) => number), rect: Rect, subtract: boolean) {
    const { w, data } = this
    for (let y = rect.y0; y < rect.y1; y++) {
      for (let x = rect.x0; x < rect.x1; x++) {
        const i = y * w + x
        const v = typeof src === 'function' ? src(x, y) : src[i]
        if (subtract) {
          const e = 255 - v
          if (e < data[i]) data[i] = e
        } else if (v > data[i]) data[i] = v
      }
    }
    this.mark(rect.x0, rect.y0, rect.x1, rect.y1)
  }

  commit() {
    const r = this.pend
    if (!r) return
    this.pend = null
    const before = crop(this.prev, this.w, r)
    const after = crop(this.data, this.w, r)
    paste(this.prev, this.w, r, after)
    this.undos.push({ r, before, after })
    this.redos = []
    let bytes = 0
    for (let i = this.undos.length - 1; i >= 0; i--) {
      bytes += this.undos[i].before.length * 2
      if (bytes > HISTORY_BYTES) {
        this.undos.splice(0, i + 1)
        break
      }
    }
    this.onhistory?.()
  }

  revert() {
    const r = this.pend
    if (!r) return
    this.pend = null
    paste(this.data, this.w, r, crop(this.prev, this.w, r))
    this.dirty = union(this.dirty, r)
    this.version++
  }

  private step(from: Patch[], to: Patch[], key: 'before' | 'after') {
    this.revert()
    const p = from.pop()
    if (!p) return
    paste(this.data, this.w, p.r, p[key])
    paste(this.prev, this.w, p.r, p[key])
    to.push(p)
    this.dirty = union(this.dirty, p.r)
    this.version++
    this.onhistory?.()
  }

  undo() {
    this.step(this.undos, this.redos, 'before')
  }
  redo() {
    this.step(this.redos, this.undos, 'after')
  }

  replace(next: Uint8ClampedArray) {
    this.data.set(next)
    this.markAll()
    this.commit()
  }

  isEmpty() {
    const d = this.data
    for (let i = 0; i < d.length; i++) if (d[i] > 8) return false
    return true
  }
}

function edt(feature: Uint8Array, w: number, h: number): Float32Array {
  const INF = 1e20
  const n = Math.max(w, h)
  const f = new Float32Array(n)
  const d = new Float32Array(n)
  const v = new Int32Array(n)
  const z = new Float32Array(n + 1)
  const out = new Float32Array(w * h)
  for (let i = 0; i < w * h; i++) out[i] = feature[i] ? 0 : INF
  const pass = (len: number, get: (i: number) => number, set: (i: number, val: number) => void) => {
    for (let i = 0; i < len; i++) f[i] = get(i)
    let k = 0
    v[0] = 0
    z[0] = -INF
    z[1] = INF
    for (let q = 1; q < len; q++) {
      let s = (f[q] + q * q - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k])
      while (s <= z[k]) {
        k--
        s = (f[q] + q * q - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k])
      }
      k++
      v[k] = q
      z[k] = s
      z[k + 1] = INF
    }
    k = 0
    for (let q = 0; q < len; q++) {
      while (z[k + 1] < q) k++
      const dq = q - v[k]
      d[q] = dq * dq + f[v[k]]
    }
    for (let i = 0; i < len; i++) set(i, d[i])
  }
  for (let x = 0; x < w; x++) pass(h, (i) => out[i * w + x], (i, val) => (out[i * w + x] = val))
  for (let y = 0; y < h; y++) {
    const row = y * w
    pass(w, (i) => out[row + i], (i, val) => (out[row + i] = val))
  }
  return out
}

export function grow(src: Uint8ClampedArray, w: number, h: number, px: number): Uint8ClampedArray {
  const out = new Uint8ClampedArray(src)
  if (!px) return out
  const n = w * h
  const feat = new Uint8Array(n)
  const r = Math.abs(px)
  if (px > 0) {
    for (let i = 0; i < n; i++) feat[i] = src[i] >= 128 ? 1 : 0
    const d = edt(feat, w, h)
    for (let i = 0; i < n; i++) {
      const v = (r + 0.5 - Math.sqrt(d[i])) * 255
      if (v > out[i]) out[i] = v
    }
  } else {
    for (let i = 0; i < n; i++) feat[i] = src[i] < 128 ? 1 : 0
    const d = edt(feat, w, h)
    for (let i = 0; i < n; i++) {
      const v = (Math.sqrt(d[i]) - r - 0.5) * 255
      if (v < out[i]) out[i] = v
    }
  }
  return out
}

function boxes(sigma: number): number[] {
  const n = 3
  const wIdeal = Math.sqrt((12 * sigma * sigma) / n + 1)
  let wl = Math.floor(wIdeal)
  if (wl % 2 === 0) wl--
  const wu = wl + 2
  const m = Math.round((12 * sigma * sigma - n * wl * wl - 4 * n * wl - 3 * n) / (-4 * wl - 4))
  return Array.from({ length: n }, (_, i) => ((i < m ? wl : wu) - 1) / 2)
}

function boxH(src: Uint8ClampedArray, dst: Uint8ClampedArray, w: number, h: number, r: number) {
  const iarr = 1 / (r + r + 1)
  for (let y = 0; y < h; y++) {
    const row = y * w
    const fv = src[row]
    let acc = (r + 1) * fv
    for (let j = 0; j < r; j++) acc += src[row + Math.min(j, w - 1)]
    for (let x = 0; x < w; x++) {
      acc += src[row + Math.min(x + r, w - 1)] - (x - r - 1 >= 0 ? src[row + x - r - 1] : fv)
      dst[row + x] = acc * iarr
    }
  }
}

function boxV(src: Uint8ClampedArray, dst: Uint8ClampedArray, w: number, h: number, r: number) {
  const iarr = 1 / (r + r + 1)
  for (let x = 0; x < w; x++) {
    const fv = src[x]
    let acc = (r + 1) * fv
    for (let j = 0; j < r; j++) acc += src[Math.min(j, h - 1) * w + x]
    for (let y = 0; y < h; y++) {
      acc += src[Math.min(y + r, h - 1) * w + x] - (y - r - 1 >= 0 ? src[(y - r - 1) * w + x] : fv)
      dst[y * w + x] = acc * iarr
    }
  }
}

export function blur(src: Uint8ClampedArray, w: number, h: number, sigma: number): Uint8ClampedArray {
  if (sigma < 0.5) return new Uint8ClampedArray(src)
  let a = new Uint8ClampedArray(src)
  let b = new Uint8ClampedArray(src.length)
  for (const r of boxes(sigma)) {
    const ri = Math.round(r)
    if (ri < 1) continue
    boxH(a, b, w, h, ri)
    boxV(b, a, w, h, ri)
  }
  return a
}

export function process(src: Uint8ClampedArray, w: number, h: number, growPx: number, sigma: number) {
  return blur(grow(src, w, h, growPx), w, h, sigma)
}

export function boundary(src: Uint8ClampedArray, w: number, h: number): Int32Array {
  const out: number[] = []
  for (let y = 0; y < h; y++) {
    const row = y * w
    for (let x = 0; x < w; x++) {
      const i = row + x
      if (src[i] < 128) continue
      if (
        x === 0 || y === 0 || x === w - 1 || y === h - 1 ||
        src[i - 1] < 128 || src[i + 1] < 128 || src[i - w] < 128 || src[i + w] < 128
      )
        out.push(i)
    }
  }
  return Int32Array.from(out)
}

export function flood(rgba: Uint8ClampedArray, w: number, h: number, sx: number, sy: number, tol: number): { data: Uint8ClampedArray; rect: Rect } | null {
  sx = Math.floor(sx)
  sy = Math.floor(sy)
  if (sx < 0 || sy < 0 || sx >= w || sy >= h) return null
  const out = new Uint8ClampedArray(w * h)
  const seen = new Uint8Array(w * h)
  const s = (sy * w + sx) * 4
  const r0 = rgba[s], g0 = rgba[s + 1], b0 = rgba[s + 2]
  const t = tol * 3
  const ok = (i: number) => {
    const p = i * 4
    return Math.abs(rgba[p] - r0) + Math.abs(rgba[p + 1] - g0) + Math.abs(rgba[p + 2] - b0) <= t
  }
  const stack = [sy * w + sx]
  seen[sy * w + sx] = 1
  let x0 = sx, x1 = sx, y0 = sy, y1 = sy
  while (stack.length) {
    const i = stack.pop()!
    out[i] = 255
    const x = i % w
    const y = (i - x) / w
    if (x < x0) x0 = x
    if (x > x1) x1 = x
    if (y < y0) y0 = y
    if (y > y1) y1 = y
    if (x > 0 && !seen[i - 1]) { seen[i - 1] = 1; if (ok(i - 1)) stack.push(i - 1) }
    if (x < w - 1 && !seen[i + 1]) { seen[i + 1] = 1; if (ok(i + 1)) stack.push(i + 1) }
    if (y > 0 && !seen[i - w]) { seen[i - w] = 1; if (ok(i - w)) stack.push(i - w) }
    if (y < h - 1 && !seen[i + w]) { seen[i + w] = 1; if (ok(i + w)) stack.push(i + w) }
  }
  return { data: out, rect: { x0, y0, x1: x1 + 1, y1: y1 + 1 } }
}
