import type { HfCategory, HfFile, ModelKind } from '$lib/types'

export const HF_CATEGORIES: { value: HfCategory; label: string }[] = [
  { value: '', label: 'All' },
  { value: 'checkpoint', label: 'Checkpoint' },
  { value: 'lora', label: 'LoRA' },
  { value: 'vae', label: 'VAE' },
  { value: 'text_encoder', label: 'Text encoder' },
  { value: 'upscaler', label: 'Upscaler' },
  { value: 'bbox', label: 'BBox' },
  { value: 'segm', label: 'Segm' },
  { value: 'embedding', label: 'Embedding' },
]

const LABELS: Record<string, string> = Object.fromEntries(HF_CATEGORIES.filter((c) => c.value).map((c) => [c.value, c.label]))

export const hfKindLabel = (k: string) => LABELS[k] ?? k

// a file's kind as a category value, detectors split into bbox / segm
export const fileCategory = (f: Pick<HfFile, 'kind' | 'sub'>): HfCategory =>
  f.kind === 'detector' ? (f.sub ?? 'bbox') : ((f.kind ?? '') as HfCategory)

export function categoryKind(c: HfCategory): { kind: ModelKind; sub: 'bbox' | 'segm' | null } | null {
  if (!c) return null
  if (c === 'bbox' || c === 'segm') return { kind: 'detector', sub: c }
  return { kind: c, sub: null }
}
