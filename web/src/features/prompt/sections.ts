import { bareTag, promptItems } from '$lib/session.svelte'
import type { PromptSection, PromptSegment } from '$lib/types'

export const SECTIONS: { key: PromptSection; label: string; placeholder: string }[] = [
  { key: 'quality', label: 'Quality', placeholder: 'masterpiece, best quality, year 2025' },
  { key: 'subject', label: 'Subject', placeholder: '1girl, solo' },
  { key: 'artists', label: 'Artists', placeholder: '@artist' },
  { key: 'prompt', label: 'Prompt', placeholder: 'Character, series, appearance, scene' },
]

const QUALITY = new Set([
  'masterpiece', 'best quality', 'high quality', 'good quality', 'normal quality', 'low quality', 'worst quality',
  'highres', 'absurdres', 'lowres', 'newest', 'recent', 'mid', 'early', 'old',
  'safe', 'sensitive', 'nsfw', 'explicit', 'general', 'questionable',
])
const SUBJECT = new Set(['solo', 'solo focus', 'no humans', 'multiple girls', 'multiple boys', 'multiple others', 'male focus'])

export function sectionOf(item: string): PromptSection {
  const t = bareTag(item.replace(/^-/, ''))
  if (t.startsWith('@')) return 'artists'
  if (QUALITY.has(t) || /^year \d{4}$/.test(t) || /^score \d/.test(t) || t.startsWith('rating:')) return 'quality'
  if (SUBJECT.has(t) || /^\d\+?(girl|boy|other)s?$/.test(t)) return 'subject'
  return 'prompt'
}

const order = (s: PromptSegment) => SECTIONS.findIndex((x) => x.key === (s.section ?? 'prompt'))

// splits unsectioned segments item by item into sections, keeping lock state and color, then orders by section
export function sectionize(segs: PromptSegment[]): PromptSegment[] {
  const out: PromptSegment[] = []
  for (const s of segs) {
    if (s.section) {
      out.push(s)
      continue
    }
    let run: PromptSegment | null = null
    for (const it of promptItems(s.text)) {
      const section = sectionOf(it)
      if (run && run.section === section) run.text += ', ' + it
      else {
        run = { ...s, text: it, section }
        out.push(run)
      }
    }
  }
  return out.map((s, i) => ({ s, i })).sort((a, b) => order(a.s) - order(b.s) || a.i - b.i).map((x) => x.s)
}
