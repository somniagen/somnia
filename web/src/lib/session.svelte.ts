import { api } from './api'
import type { Family, FamilyInfo, GenParams, LoraRef, PromptSegment, Presets } from './types'

const KEY = 'somnia.session.v1'

// top level comma items, ignoring commas inside parentheses or escaped
export function promptItems(text: string): string[] {
  const out: string[] = []
  let depth = 0
  let cur = ''
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (c === '\\' && i + 1 < text.length) {
      cur += c + text[++i]
      continue
    }
    if (c === '(' || c === '[' || c === '{') depth++
    else if ((c === ')' || c === ']' || c === '}') && depth > 0) depth--
    if ((c === ',' || c === '\n') && depth === 0) {
      out.push(cur)
      cur = ''
    } else cur += c
  }
  out.push(cur)
  return out.map((x) => x.trim()).filter(Boolean)
}

// "(tag:1.2)", "(tag)" and "[tag]" all compare as "tag"
export function bareTag(item: string): string {
  let t = item.trim()
  for (let m; (m = /^[([{]([^]*?)(?::\s*-?\d*\.?\d+\s*)?[)\]}]$/.exec(t)); ) t = m[1].trim()
  return t.replace(/\\([()[\]{}])/g, '$1').replace(/_/g, ' ').replace(/\s+/g, ' ').toLowerCase()
}

// "-tag" items in editable text remove that tag from the boilerplate
export function removedTags(segs: PromptSegment[]): Set<string> {
  const out = new Set<string>()
  for (const s of segs) if (!s.locked) for (const it of promptItems(s.text)) if (/^-\S/.test(it)) out.add(bareTag(it.slice(1)))
  return out
}

export function segmentsToText(segs: PromptSegment[]): string {
  const removed = removedTags(segs)
  return segs
    .map((s) => {
      const t = s.text.trim().replace(/^,+|,+$/g, '').trim()
      if (!removed.size) return t
      const keep = s.locked
        ? promptItems(t).filter((it) => !removed.has(bareTag(it)))
        : promptItems(t).filter((it) => !/^-\S/.test(it))
      return keep.join(', ')
    })
    .filter(Boolean)
    .join(', ')
}

export function textToSegments(text: string): PromptSegment[] {
  return text.trim() ? [{ text: text.trim(), locked: false }] : []
}

interface Stored {
  v?: number
  family: Family
  params: Partial<Record<Family, GenParams>>
  positive: Partial<Record<Family, PromptSegment[]>>
  negative: Partial<Record<Family, PromptSegment[]>>
  structured?: boolean
}

class Session {
  presets = $state<Presets | null>(null)
  family = $state<Family>('illustrious')
  byFamily = $state<Partial<Record<Family, GenParams>>>({})
  positive = $state<Partial<Record<Family, PromptSegment[]>>>({})
  negative = $state<Partial<Record<Family, PromptSegment[]>>>({})
  count = $state(1)
  // anima positive prompt split into quality, subject, artists and prompt sections
  structured = $state(false)

  info = $derived<FamilyInfo | null>(this.presets?.families[this.family] ?? null)
  params = $derived<GenParams | null>(this.byFamily[this.family] ?? null)

  async init() {
    try {
      const s = JSON.parse(localStorage.getItem(KEY) ?? 'null') as Stored | null
      if (s) {
        this.family = s.family
        this.byFamily = s.params
        this.positive = s.positive
        this.negative = s.negative
        this.structured = !!s.structured
        const ill = this.byFamily.illustrious
        if (!s.v && ill && ill.width === 832 && ill.height === 1216) Object.assign(ill, { width: 1024, height: 1536 })
      }
    } catch {}
    this.presets = await api.presets()
    for (const f of Object.keys(this.presets.families) as Family[]) {
      const d = this.presets.families[f].defaults
      this.byFamily[f] = { ...structuredClone($state.snapshot(d)), ...(this.byFamily[f] ?? {}) }
      if (!this.positive[f]) this.positive[f] = this.splitDefault(d.prompt)
      if (!this.negative[f]) this.negative[f] = this.splitDefault(d.negative)
    }
    $effect.root(() => {
      $effect(() => {
        const s: Stored = {
          v: 2,
          family: this.family,
          params: $state.snapshot(this.byFamily),
          positive: $state.snapshot(this.positive),
          negative: $state.snapshot(this.negative),
          structured: this.structured,
        }
        try {
          localStorage.setItem(KEY, JSON.stringify(s))
        } catch {}
      })
    })
  }

  defaultSegments(family: Family, kind: 'positive' | 'negative'): PromptSegment[] {
    const d = this.presets?.families[family]?.defaults
    return this.splitDefault((kind === 'positive' ? d?.prompt : d?.negative) ?? '')
  }

  // preset prompts come as "quality prefix, " so the prefix becomes a locked boilerplate segment
  private splitDefault(text: string): PromptSegment[] {
    return text.trim() ? [{ text: text.trim().replace(/,\s*$/, ''), locked: true }, { text: '', locked: false }] : [{ text: '', locked: false }]
  }

  update(patch: Partial<GenParams>) {
    const p = this.byFamily[this.family]
    if (p) Object.assign(p, patch)
  }

  // patches the current family's params and returns an undo that restores the replaced values
  patchWithUndo(patch: Partial<GenParams>): () => void {
    const p = this.byFamily[this.family]
    if (!p) return () => {}
    const fam = this.family
    const prev = $state.snapshot(Object.fromEntries(Object.keys(patch).map((k) => [k, p[k as keyof GenParams]]))) as Partial<GenParams>
    Object.assign(p, structuredClone($state.snapshot(patch)))
    return () => {
      const q = this.byFamily[fam]
      if (q) Object.assign(q, prev)
    }
  }

  resetDefaults() {
    const d = this.presets?.families[this.family]?.defaults
    if (!d) return
    const keep = this.byFamily[this.family]
    this.byFamily[this.family] = { ...structuredClone($state.snapshot(d)), model: keep?.model || d.model, loras: keep?.loras ?? [] }
  }

  setFamily(f: Family) {
    this.family = f
  }

  addLora(id: string, weight = 1) {
    const p = this.byFamily[this.family]
    if (!p || p.loras.some((l) => l.id === id)) return
    p.loras = [...p.loras, { id, weight }]
  }

  removeLora(id: string) {
    const p = this.byFamily[this.family]
    if (p) p.loras = p.loras.filter((l: LoraRef) => l.id !== id)
  }

  addBoilerplate(text: string, which: 'positive' | 'negative' = 'positive') {
    const segs = (which === 'positive' ? this.positive : this.negative)[this.family] ?? []
    if (segs.some((s) => s.text.trim() === text.trim())) return
    const next = [...segs]
    const firstFree = next.findIndex((s) => !s.locked)
    next.splice(firstFree < 0 ? next.length : firstFree, 0, { text: text.trim(), locked: true })
    ;(which === 'positive' ? this.positive : this.negative)[this.family] = next
  }

  setPrompt(positive: string, negative?: string) {
    const keepLocked = (segs: PromptSegment[] | undefined) => (segs ?? []).filter((s) => s.locked)
    this.positive[this.family] = [...keepLocked(this.positive[this.family]), { text: positive, locked: false }]
    if (negative !== undefined)
      this.negative[this.family] = [...keepLocked(this.negative[this.family]), { text: negative, locked: false }]
  }

  // applies params loaded from an image or a civitai example; unknown fields are ignored
  applyParams(p: Partial<GenParams>) {
    if (p.family && p.family !== this.family && this.byFamily[p.family]) this.family = p.family
    // snapshot so gallery state proxies are neither cloned nor shared
    const { prompt, negative, segments, stackId: _s, ...rest } = $state.snapshot(p) as Partial<GenParams>
    this.update(rest)
    if (segments?.positive?.length) {
      this.positive[this.family] = segments.positive
      this.negative[this.family] = segments.negative ?? textToSegments(negative ?? '')
    } else if (prompt !== undefined) {
      this.positive[this.family] = textToSegments(prompt)
      if (negative !== undefined) this.negative[this.family] = textToSegments(negative)
    }
  }

  build(): GenParams | null {
    const p = this.byFamily[this.family]
    if (!p) return null
    return {
      ...$state.snapshot(p),
      family: this.family,
      prompt: segmentsToText(this.positive[this.family] ?? []),
      negative: segmentsToText(this.negative[this.family] ?? []),
      segments: {
        positive: $state.snapshot(this.positive[this.family] ?? []) as PromptSegment[],
        negative: $state.snapshot(this.negative[this.family] ?? []) as PromptSegment[],
      },
    } as GenParams
  }

  async generate(count = this.count, repeat = false) {
    const p = this.build()
    if (!p) return
    return api.queue(p, count, repeat)
  }
}

export const session = new Session()
