import type { Rect } from './mask'

export type SmartPoint = { x: number; y: number }
export type SmartOpts = {
  // 0..1, how strongly image edges stop the selection
  edges: number
  // working resolution cap, lower is faster
  res: number
  // existing mask (full image) used to seed the region the stroke extends or protects
  mask?: Uint8ClampedArray
  subtract?: boolean
}

class Heap {
  k = new Float64Array(4096)
  v = new Int32Array(4096)
  n = 0
  top = 0

  push(key: number, val: number) {
    if (this.n === this.k.length) {
      const k = new Float64Array(this.n * 2)
      const v = new Int32Array(this.n * 2)
      k.set(this.k)
      v.set(this.v)
      this.k = k
      this.v = v
    }
    let i = this.n++
    const { k, v } = this
    while (i > 0) {
      const p = (i - 1) >> 1
      if (k[p] <= key) break
      k[i] = k[p]
      v[i] = v[p]
      i = p
    }
    k[i] = key
    v[i] = val
  }

  pop(): number {
    const { k, v } = this
    const out = v[0]
    this.top = k[0]
    const n = --this.n
    if (n > 0) {
      const key = k[n]
      const val = v[n]
      let i = 0
      for (;;) {
        let c = 2 * i + 1
        if (c >= n) break
        if (c + 1 < n && k[c + 1] < k[c]) c++
        if (k[c] >= key) break
        k[i] = k[c]
        v[i] = v[c]
        i = c
      }
      k[i] = key
      v[i] = val
    }
    return out
  }
}

const DX = [1, -1, 0, 0, 1, 1, -1, -1]
const DY = [0, 0, 1, -1, 1, -1, 1, -1]

function watershed(
  w: number,
  h: number,
  fg: Uint8Array,
  bg: Uint8Array,
  col: Float32Array,
  uF: Float32Array,
  uB: Float32Array,
  edgeK: number,
  floor: number,
) {
  const n = w * h
  // 0 unlabeled, 1 inside, 2 outside
  const lab = new Uint8Array(n)
  const heap = new Heap()
  const queued = new Uint8Array(n)
  const push = (i: number, from: number, L: number) => {
    const r = col[i * 3] - col[from * 3], g = col[i * 3 + 1] - col[from * 3 + 1], b = col[i * 3 + 2] - col[from * 3 + 2]
    const e = edgeK * Math.max(0, Math.sqrt(r * r + g * g + b * b) - floor)
    heap.push(e + (L === 1 ? uF[i] : uB[i]), i * 2 + L - 1)
  }
  const spread = (i: number, L: number) => {
    const x = i % w
    const y = (i - x) / w
    for (let k = 0; k < 4; k++) {
      const nx = x + DX[k], ny = y + DY[k]
      if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue
      const j = ny * w + nx
      if (lab[j] || queued[j] & L) continue
      queued[j] |= L
      push(j, i, L)
    }
  }
  for (let i = 0; i < n; i++) {
    if (fg[i]) lab[i] = 1
    else if (bg[i]) lab[i] = 2
  }
  for (let i = 0; i < n; i++) if (lab[i]) spread(i, lab[i])
  while (heap.n) {
    const v = heap.pop()
    const i = v >> 1
    if (lab[i]) continue
    const L = (v & 1) + 1
    lab[i] = L
    spread(i, L)
  }
  return lab
}

function boxBlur3(src: Float32Array, w: number, h: number, ch: number) {
  const out = new Float32Array(src.length)
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++)
      for (let c = 0; c < ch; c++) {
        let s = 0
        let m = 0
        for (let yy = Math.max(0, y - 1); yy <= Math.min(h - 1, y + 1); yy++)
          for (let xx = Math.max(0, x - 1); xx <= Math.min(w - 1, x + 1); xx++) {
            s += src[(yy * w + xx) * ch + c]
            m++
          }
        out[(y * w + x) * ch + c] = s / m
      }
  return out
}

function boxMean(src: Float32Array, w: number, h: number, r: number) {
  const W1 = w + 1
  const ii = new Float64Array(W1 * (h + 1))
  for (let y = 0; y < h; y++) {
    let row = 0
    for (let x = 0; x < w; x++) {
      row += src[y * w + x]
      ii[(y + 1) * W1 + x + 1] = ii[y * W1 + x + 1] + row
    }
  }
  const out = new Float32Array(w * h)
  for (let y = 0; y < h; y++) {
    const y0 = Math.max(0, y - r), y1 = Math.min(h, y + r + 1)
    for (let x = 0; x < w; x++) {
      const x0 = Math.max(0, x - r), x1 = Math.min(w, x + r + 1)
      const s = ii[y1 * W1 + x1] - ii[y0 * W1 + x1] - ii[y1 * W1 + x0] + ii[y0 * W1 + x0]
      out[y * w + x] = s / ((x1 - x0) * (y1 - y0))
    }
  }
  return out
}

// edge-aware softening of the hard label (guided filter, gray guide)
function guided(I: Float32Array, p: Float32Array, w: number, h: number, r: number, eps: number) {
  const n = w * h
  const Ip = new Float32Array(n)
  const II = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    Ip[i] = I[i] * p[i]
    II[i] = I[i] * I[i]
  }
  const mI = boxMean(I, w, h, r)
  const mp = boxMean(p, w, h, r)
  const mIp = boxMean(Ip, w, h, r)
  const mII = boxMean(II, w, h, r)
  const a = new Float32Array(n)
  const b = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const cov = mIp[i] - mI[i] * mp[i]
    const v = mII[i] - mI[i] * mI[i]
    a[i] = cov / (v + eps)
    b[i] = mp[i] - a[i] * mI[i]
  }
  const ma = boxMean(a, w, h, r)
  const mb = boxMean(b, w, h, r)
  const out = new Float32Array(n)
  for (let i = 0; i < n; i++) out[i] = ma[i] * I[i] + mb[i]
  return out
}

function sample(col: Float32Array, idx: number[], max: number): Float32Array {
  const step = Math.max(1, Math.floor(idx.length / max))
  const out: number[] = []
  for (let k = 0; k < idx.length && out.length < max * 3; k += step) {
    const i = idx[k]
    out.push(col[i * 3], col[i * 3 + 1], col[i * 3 + 2])
  }
  return Float32Array.from(out)
}

function nearest(col: Float32Array, i: number, s: Float32Array) {
  const r = col[i * 3], g = col[i * 3 + 1], b = col[i * 3 + 2]
  let best = Infinity
  for (let k = 0; k < s.length; k += 3) {
    const dr = s[k] - r, dg = s[k + 1] - g, db = s[k + 2] - b
    const d = dr * dr + dg * dg + db * db
    if (d < best) best = d
  }
  return Math.sqrt(best)
}

// segments the object under a brush stroke: marker watershed between the stroke (inside) and the region
// border plus surroundings-colored pixels (outside), so boundaries settle on edges, then edge-refined
export function smartSelect(
  rgba: Uint8ClampedArray,
  W: number,
  H: number,
  pts: SmartPoint[],
  radius: number,
  opts: SmartOpts,
  grow = 0,
): { rect: Rect; alpha: Uint8ClampedArray } | null {
  if (!pts.length) return null
  let bx0 = Infinity, by0 = Infinity, bx1 = -Infinity, by1 = -Infinity
  for (const p of pts) {
    bx0 = Math.min(bx0, p.x)
    by0 = Math.min(by0, p.y)
    bx1 = Math.max(bx1, p.x)
    by1 = Math.max(by1, p.y)
  }
  const span = Math.max(bx1 - bx0, by1 - by0)
  const m = Math.max(48, radius * 4, span * 0.45) * 2 ** grow
  const rect: Rect = {
    x0: Math.max(0, Math.floor(bx0 - m)),
    y0: Math.max(0, Math.floor(by0 - m)),
    x1: Math.min(W, Math.ceil(bx1 + m)),
    y1: Math.min(H, Math.ceil(by1 + m)),
  }
  const rw = rect.x1 - rect.x0
  const rh = rect.y1 - rect.y0
  if (rw < 2 || rh < 2) return null
  const s = Math.min(1, opts.res / Math.max(rw, rh))
  const w = Math.max(2, Math.ceil(rw * s))
  const h = Math.max(2, Math.ceil(rh * s))
  const n = w * h

  const acc = new Float32Array(n * 3)
  const cnt = new Float32Array(n)
  for (let y = rect.y0; y < rect.y1; y++) {
    const wy = Math.min(h - 1, Math.floor((y - rect.y0) * s))
    for (let x = rect.x0; x < rect.x1; x++) {
      const wx = Math.min(w - 1, Math.floor((x - rect.x0) * s))
      const j = wy * w + wx
      const p = (y * W + x) * 4
      acc[j * 3] += rgba[p]
      acc[j * 3 + 1] += rgba[p + 1]
      acc[j * 3 + 2] += rgba[p + 2]
      cnt[j]++
    }
  }
  for (let j = 0; j < n; j++) {
    const c = cnt[j] || 1
    acc[j * 3] /= c * 255
    acc[j * 3 + 1] /= c * 255
    acc[j * 3 + 2] /= c * 255
  }
  const col = boxBlur3(acc, w, h, 3)

  const fg = new Uint8Array(n)
  const bg = new Uint8Array(n)
  const core = Math.max(1, radius * s * 0.5)
  const stamp = (cx: number, cy: number) => {
    const x0 = Math.max(0, Math.floor(cx - core)), x1 = Math.min(w - 1, Math.ceil(cx + core))
    const y0 = Math.max(0, Math.floor(cy - core)), y1 = Math.min(h - 1, Math.ceil(cy + core))
    for (let y = y0; y <= y1; y++)
      for (let x = x0; x <= x1; x++) if ((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= core * core || (x === Math.floor(cx) && y === Math.floor(cy))) fg[y * w + x] = 1
  }
  let prev: SmartPoint | null = null
  for (const p of pts) {
    const q = { x: (p.x - rect.x0) * s, y: (p.y - rect.y0) * s }
    if (prev) {
      const L = Math.hypot(q.x - prev.x, q.y - prev.y)
      const k = Math.ceil(L / Math.max(0.5, core * 0.5))
      for (let i = 1; i <= k; i++) stamp(prev.x + ((q.x - prev.x) * i) / k, prev.y + ((q.y - prev.y) * i) / k)
    } else stamp(q.x, q.y)
    prev = q
  }
  const fgIdx: number[] = []
  for (let i = 0; i < n; i++) if (fg[i]) fgIdx.push(i)
  if (!fgIdx.length) return null
  const fgS = sample(col, fgIdx, 48)

  // region borders inside the image are outside seeds; image borders only where colors differ from the stroke
  const border = (x: number, y: number, inner: boolean) => {
    const i = y * w + x
    if (fg[i]) return
    if (inner || nearest(col, i, fgS) > 0.18) bg[i] = 1
  }
  for (let x = 0; x < w; x++) {
    border(x, 0, rect.y0 > 0)
    border(x, h - 1, rect.y1 < H)
  }
  for (let y = 0; y < h; y++) {
    border(0, y, rect.x0 > 0)
    border(w - 1, y, rect.x1 < W)
  }

  // the existing mask extends the stroke when adding and protects what is kept when subtracting
  if (opts.mask) {
    const mk = opts.mask
    const far = (radius * 2.5) ** 2
    for (let y = 0; y < h; y++) {
      const sy = Math.min(H - 1, rect.y0 + Math.floor((y + 0.5) / s))
      for (let x = 0; x < w; x++) {
        const i = y * w + x
        if (fg[i]) continue
        const sx = Math.min(W - 1, rect.x0 + Math.floor((x + 0.5) / s))
        const v = mk[sy * W + sx]
        if (!opts.subtract) {
          if (v > 200) fg[i] = 2
        } else if (v > 200) {
          let near = false
          for (const p of pts) if ((p.x - sx) ** 2 + (p.y - sy) ** 2 < far) { near = true; break }
          if (!near) bg[i] = 1
        }
      }
    }
  }

  const bgIdx: number[] = []
  for (let i = 0; i < n; i++) if (bg[i]) bgIdx.push(i)
  const bgS = bgIdx.length ? sample(col, bgIdx, 96) : null

  // texture and sensor noise should not count as edges
  const diffs: number[] = []
  for (let i = 0; i < n - 1; i += Math.max(1, Math.floor(n / 4000))) {
    if ((i + 1) % w === 0) continue
    const dr = col[i * 3] - col[i * 3 + 3], dg = col[i * 3 + 1] - col[i * 3 + 4], db = col[i * 3 + 2] - col[i * 3 + 5]
    diffs.push(Math.sqrt(dr * dr + dg * dg + db * db))
  }
  diffs.sort((a, b) => a - b)
  const floor = (diffs[Math.floor(diffs.length * 0.5)] ?? 0) * 1.2
  const edgeK = 4 + 28 * opts.edges

  // color likeness only breaks ties inside flat areas, edges decide the boundary
  const uF = new Float32Array(n)
  const uB = new Float32Array(n)
  const CW = 5
  if (bgS) {
    for (let i = 0; i < n; i++) {
      const dF = nearest(col, i, fgS)
      const dB = nearest(col, i, bgS)
      uF[i] = dF * CW
      uB[i] = dB * CW
      // looks like the surroundings and not like the stroke: outside even when enclosed (eyes in a face)
      if (!fg[i] && dF > 0.22 && dF > 2.2 * dB) bg[i] = 1
    }
  } else for (let i = 0; i < n; i++) uF[i] = nearest(col, i, fgS) * CW

  if (!bgIdx.length) {
    // no outside seeds at all: anything clearly unlike the stroke is outside
    for (let i = 0; i < n; i++) if (!fg[i] && uF[i] > 0.3 * CW) bg[i] = 1
  }
  const lab0 = watershed(w, h, fg, bg, col, uF, uB, edgeK, floor)
  const lab = new Uint8Array(n)
  for (let i = 0; i < n; i++) lab[i] = lab0[i] === 1 ? 1 : 0

  // keep only parts connected to the stroke itself
  const keep = new Uint8Array(n)
  const stack: number[] = []
  for (let i = 0; i < n; i++) if (fg[i] === 1 && lab[i]) { keep[i] = 1; stack.push(i) }
  while (stack.length) {
    const i = stack.pop()!
    const x = i % w
    const y = (i - x) / w
    for (let k = 0; k < 4; k++) {
      const nx = x + DX[k], ny = y + DY[k]
      if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue
      const j = ny * w + nx
      if (lab[j] && !keep[j]) {
        keep[j] = 1
        stack.push(j)
      }
    }
  }

  // the object runs past the work region: retry with a larger one
  if (grow < 3) {
    let hit = 0
    const band = Math.max(3, Math.round(Math.min(w, h) * 0.04))
    for (let b = 0; b < band; b++) {
      for (let x = 0; x < w; x++) {
        if (rect.y0 > 0 && keep[b * w + x]) hit++
        if (rect.y1 < H && keep[(h - 1 - b) * w + x]) hit++
      }
      for (let y = 0; y < h; y++) {
        if (rect.x0 > 0 && keep[y * w + b]) hit++
        if (rect.x1 < W && keep[y * w + w - 1 - b]) hit++
      }
    }
    if (hit > band * 2) return smartSelect(rgba, W, H, pts, radius, opts, grow + 1)
  }

  const gray = new Float32Array(n)
  const p = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    gray[i] = col[i * 3] * 0.299 + col[i * 3 + 1] * 0.587 + col[i * 3 + 2] * 0.114
    p[i] = keep[i]
  }
  const soft = guided(gray, p, w, h, Math.max(1, Math.round(2 * Math.min(1, s * 2))), 2e-3)

  const alpha = new Uint8ClampedArray(rw * rh)
  for (let y = 0; y < rh; y++) {
    const fy = Math.min(h - 1, Math.max(0, (y + 0.5) * s - 0.5))
    const y0 = Math.floor(fy), y1 = Math.min(h - 1, y0 + 1), ty = fy - y0
    for (let x = 0; x < rw; x++) {
      const fx = Math.min(w - 1, Math.max(0, (x + 0.5) * s - 0.5))
      const x0 = Math.floor(fx), x1 = Math.min(w - 1, x0 + 1), tx = fx - x0
      const a =
        (soft[y0 * w + x0] * (1 - tx) + soft[y0 * w + x1] * tx) * (1 - ty) +
        (soft[y1 * w + x0] * (1 - tx) + soft[y1 * w + x1] * tx) * ty
      alpha[y * rw + x] = Math.max(0, Math.min(1, (a - 0.5) * 2.2 + 0.5)) * 255
    }
  }
  return { rect, alpha }
}
