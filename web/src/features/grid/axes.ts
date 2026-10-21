import type { GenParams, GridAxis, GridAxisValue } from '$lib/types'

export type AxisKind =
  | 'seed'
  | 'steps'
  | 'cfg'
  | 'sampler'
  | 'scheduler'
  | 'model'
  | 'lora'
  | 'prompt'
  | 'clipSkip'
  | 'spDenoise'
  | 'spScale'
  | 'pag'
  | 'cfgRescale'
  | 'vae'
  | 'size'
  | 'detDenoise'
  | 'variation'
  | 'stepCache'

export type Input = 'int' | 'number' | 'select' | 'lines' | 'size'

export interface AxisDraft {
  kind: AxisKind
  // number lists, prompt lines, sizes
  text: string
  // select kinds
  picks: string[]
  // lora weight: which lora of the base
  lora: string | null
}

export interface KindDef {
  kind: AxisKind
  label: string
  input: Input
  placeholder?: string
  patch: (v: string | number, base: GenParams) => Record<string, unknown>
  // value shown in the table header
  show?: (v: string | number) => string
}

export const short = (id: string) => id.split(':').pop()?.replace(/\.(safetensors|ckpt|pt|pth)$/, '').split('/').pop() ?? id

export const KINDS: KindDef[] = [
  { kind: 'seed', label: 'Seed', input: 'int', placeholder: '1, 2, 3 or 100-104', patch: (v) => ({ seed: v }) },
  { kind: 'steps', label: 'Steps', input: 'int', placeholder: '20-40 (+10)', patch: (v) => ({ steps: v }) },
  { kind: 'cfg', label: 'CFG', input: 'number', placeholder: '3-7 [5]', patch: (v) => ({ cfg: v }) },
  { kind: 'sampler', label: 'Sampler', input: 'select', patch: (v) => ({ sampler: v }) },
  { kind: 'scheduler', label: 'Scheduler', input: 'select', patch: (v) => ({ scheduler: v }) },
  { kind: 'model', label: 'Checkpoint', input: 'select', patch: (v) => ({ model: v }), show: (v) => short(String(v)) },
  { kind: 'lora', label: 'LoRA weight', input: 'number', placeholder: '0.4-1 (+0.2)', patch: () => ({}) },
  { kind: 'prompt', label: 'Prompt S/R', input: 'lines', placeholder: 'red hair\nblue hair\nblonde hair', patch: () => ({}) },
  { kind: 'clipSkip', label: 'Clip skip', input: 'int', placeholder: '1, 2', patch: (v) => ({ clipSkip: v }) },
  {
    kind: 'spDenoise',
    label: 'Second pass denoise',
    input: 'number',
    placeholder: '0.3-0.6 (+0.1)',
    patch: (v) => ({ secondPass: { enabled: true, denoise: v } }),
  },
  {
    kind: 'spScale',
    label: 'Second pass scale',
    input: 'number',
    placeholder: '1.25, 1.5',
    patch: (v) => ({ secondPass: { enabled: true, scale: v } }),
  },
  { kind: 'pag', label: 'PAG scale', input: 'number', placeholder: '0, 1.5, 3', patch: (v) => ({ pag: { enabled: Number(v) > 0, scale: v } }) },
  { kind: 'cfgRescale', label: 'CFG rescale', input: 'number', placeholder: '0, 0.35, 0.7', patch: (v) => ({ cfgRescale: v }) },
  { kind: 'stepCache', label: 'Step cache', input: 'int', placeholder: '0, 1, 2', patch: (v) => ({ stepCache: v }), show: (v) => ['Off', 'Light', 'Fast'][Number(v)] ?? String(v) },
  { kind: 'vae', label: 'VAE', input: 'select', patch: (v) => ({ vae: v || null }), show: (v) => (v ? short(String(v)) : 'Built in') },
  {
    kind: 'size',
    label: 'Size',
    input: 'size',
    placeholder: '1024x1024, 832x1216',
    patch: (v) => {
      const [w, h] = String(v).split('x').map(Number)
      return { width: w, height: h }
    },
  },
  {
    kind: 'detDenoise',
    label: 'Detailer denoise',
    input: 'number',
    placeholder: '0.3-0.5 (+0.1)',
    patch: (v, base) => ({ detailers: base.detailers.map((d) => ({ ...d, denoise: v })) }),
  },
  {
    kind: 'variation',
    label: 'Variation strength',
    input: 'number',
    placeholder: '0-0.3 (+0.1)',
    patch: (v) => ({ variation: { enabled: Number(v) > 0, strength: v } }),
  },
]

export const kindDef = (k: AxisKind) => KINDS.find((d) => d.kind === k) ?? KINDS[0]

const round = (v: number) => Number(v.toFixed(4))
const NUM = String.raw`-?\d*\.?\d+`
const RANGE = new RegExp(String.raw`^(${NUM})\s*-\s*(${NUM})\s*(?:\(\s*([+-]?\d*\.?\d+)\s*\)|\[\s*(\d+)\s*\])?$`)

// "1, 2, 3", a1111 ranges "1-10 (+2)" and "4-8 [5]"; null when a part does not parse
export function parseNumbers(text: string, int: boolean): number[] | null {
  const out: number[] = []
  for (const raw of text.split(',')) {
    const t = raw.trim()
    if (!t) continue
    const m = RANGE.exec(t)
    if (m) {
      const a = Number(m[1])
      const b = Number(m[2])
      if (m[4]) {
        const n = Math.max(1, Math.min(500, Number(m[4])))
        for (let i = 0; i < n; i++) out.push(n === 1 ? a : a + ((b - a) * i) / (n - 1))
      } else {
        const step = Math.abs(m[3] ? Number(m[3]) : 1) || 1
        const dir = b >= a ? 1 : -1
        for (let v = a; dir > 0 ? v <= b + 1e-9 : v >= b - 1e-9; v += step * dir) {
          out.push(v)
          if (out.length > 500) break
        }
      }
      continue
    }
    if (!/^-?\d*\.?\d+$/.test(t)) return null
    out.push(Number(t))
  }
  return out.map((v) => (int ? Math.round(v) : round(v)))
}

export function parseSizes(text: string): string[] | null {
  const out: string[] = []
  for (const raw of text.split(',')) {
    const t = raw.trim().toLowerCase()
    if (!t) continue
    const m = /^(\d+)\s*[x*]\s*(\d+)$/.exec(t)
    if (!m) return null
    out.push(`${m[1]}x${m[2]}`)
  }
  return out
}

export function rawValues(d: AxisDraft): (string | number)[] | null {
  const def = kindDef(d.kind)
  if (def.input === 'select') return d.picks
  if (def.input === 'size') return parseSizes(d.text)
  if (def.input === 'lines')
    return d.text
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
  return parseNumbers(d.text, def.input === 'int')
}

export function axisLabel(d: AxisDraft) {
  if (d.kind === 'lora' && d.lora) return short(d.lora)
  return kindDef(d.kind).label
}

export function buildAxis(d: AxisDraft, base: GenParams): GridAxis | null {
  const def = kindDef(d.kind)
  const raw = rawValues(d)
  if (!raw?.length) return null
  if (d.kind === 'lora' && !d.lora) return null
  const values: GridAxisValue[] = raw.map((v) => {
    let patch = def.patch(v, base)
    if (d.kind === 'prompt') patch = { $sr: [String(raw[0]), String(v)] }
    else if (d.kind === 'lora') patch = { $lora: { id: d.lora, weight: v } }
    return { label: def.show ? def.show(v) : String(v), patch }
  })
  return { kind: d.kind, label: axisLabel(d), values }
}

export const newDraft = (kind: AxisKind = 'cfg'): AxisDraft => ({ kind, text: '', picks: [], lora: null })
