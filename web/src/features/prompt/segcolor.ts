import type { TagCategory } from '$lib/types'
import { tokenize } from './tokenize'

export const segColors: { key: string; label: string; v: string }[] = [
  { key: 'amber', label: 'Amber', v: '--tag-meta' },
  { key: 'copper', label: 'Copper', v: '--tag-lora' },
  { key: 'rose', label: 'Rose', v: '--tag-artist' },
  { key: 'violet', label: 'Violet', v: '--tag-copyright' },
  { key: 'blue', label: 'Blue', v: '--tag-general' },
  { key: 'green', label: 'Green', v: '--tag-character' },
  { key: 'gray', label: 'Gray', v: '--text-muted' },
]

const QUALITY =
  /^(masterpiece|best_quality|amazing_quality|high_quality|great_quality|good_quality|normal_quality|low_quality|worst_quality|bad_quality|very_aesthetic|aesthetic|displeasing|very_displeasing|absurdres|highres|lowres|newest|recent|mid|early|old|year_\d+|score_\d+(_up)?|safe|sensitive|nsfw|explicit|general|questionable|rating:.*|ultra-detailed|detailed|very_awa|4k|8k)$/

export type SegKind = 'quality' | 'lora' | 'style' | 'negative' | 'user'
const kindColor: Record<SegKind, string> = { quality: 'amber', lora: 'copper', style: 'violet', negative: 'rose', user: 'blue' }

export function segKind(
  text: string,
  prompt: 'positive' | 'negative',
  cat: (t: string) => TagCategory | null | undefined,
  loraWords: Set<string>,
): SegKind {
  if (prompt === 'negative') return 'negative'
  const t = text.trim()
  if (loraWords.has(t)) return 'lora'
  const tags = tokenize(t).flatMap((x) => (x.tag ? [x.tag] : []))
  if (!tags.length) return 'user'
  const q = tags.filter((x) => QUALITY.test(x) || cat(x) === 5).length
  if (q / tags.length >= 0.5) return 'quality'
  if (tags.some((x) => !QUALITY.test(x) && loraWords.has(x.replace(/_/g, ' ')))) return 'lora'
  if (tags.some((x) => cat(x) === 1 || x.startsWith('@') || x.startsWith('by_') || x.endsWith('_style'))) return 'style'
  return 'user'
}

export function colorKey(seg: { text: string; color?: string }, kind: SegKind) {
  return seg.color && segColors.some((c) => c.key === seg.color) ? seg.color : kindColor[kind]
}

export const colorVar = (key: string) => `var(${segColors.find((c) => c.key === key)?.v ?? '--text-muted'})`
