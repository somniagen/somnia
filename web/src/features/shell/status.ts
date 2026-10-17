import type { Phase, Progress } from '$lib/types'

export const phaseNames: Record<Phase, string> = {
  load: 'Loading model',
  encode: 'Encoding prompt',
  sample: 'Sampling',
  second: 'Second pass',
  detail: 'Detailer',
  upscale: 'Upscaling',
  refine: 'Refining',
  decode: 'Decoding',
  save: 'Saving',
}

const stepped: Phase[] = ['sample', 'second', 'detail', 'upscale', 'refine']

export function hasSteps(p: Progress | null) {
  return !!p && p.total > 0 && stepped.includes(p.phase)
}

export function phaseValue(p: Progress | null): number | null {
  if (!p || !hasSteps(p)) return null
  return Math.max(0, Math.min(1, p.step / p.total))
}

export function statusText(p: Progress | null): string {
  if (!p) return 'Starting'
  const base = p.label?.trim() || phaseNames[p.phase]
  return hasSteps(p) ? `${base} ${p.step}/${p.total}` : base
}

export function eta(s: number | null | undefined) {
  if (s === null || s === undefined || !isFinite(s) || s <= 0) return ''
  const t = Math.round(s)
  return t >= 60 ? `${Math.floor(t / 60)}m ${t % 60}s` : `${t}s`
}
