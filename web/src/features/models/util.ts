import type { CivitaiImage, GenParams } from '$lib/types'

export function fmtSize(bytes: number) {
  if (bytes >= 1e9) return (bytes / 1e9).toFixed(2) + ' GB'
  if (bytes >= 1e6) return (bytes / 1e6).toFixed(0) + ' MB'
  return (bytes / 1e3).toFixed(0) + ' KB'
}

export function fmtCount(n: number) {
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + 'k'
  return String(n)
}

const ALLOWED = new Set(['P', 'BR', 'B', 'STRONG', 'I', 'EM', 'U', 'UL', 'OL', 'LI', 'A', 'H1', 'H2', 'H3', 'H4', 'CODE', 'PRE', 'BLOCKQUOTE', 'HR', 'SPAN', 'DIV', 'S'])

export function sanitize(html: string): string {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  const walk = (node: Element) => {
    for (const child of Array.from(node.children)) {
      if (!ALLOWED.has(child.tagName)) {
        if (['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'FORM', 'IMG', 'VIDEO', 'SVG'].includes(child.tagName.toUpperCase())) {
          child.remove()
          continue
        }
        walk(child)
        child.replaceWith(...Array.from(child.childNodes))
        continue
      }
      for (const a of Array.from(child.attributes)) {
        if (child.tagName === 'A' && a.name === 'href' && /^https?:/i.test(a.value)) continue
        child.removeAttribute(a.name)
      }
      if (child.tagName === 'A') {
        child.setAttribute('target', '_blank')
        child.setAttribute('rel', 'noopener noreferrer')
      }
      walk(child)
    }
  }
  walk(doc.body)
  return doc.body.innerHTML
}

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '')

export function paramsFromMeta(meta: NonNullable<CivitaiImage['meta']>, samplers: string[]): Partial<GenParams> {
  const p: Partial<GenParams> = {}
  if (meta.prompt) p.prompt = meta.prompt
  if (meta.negativePrompt !== undefined) p.negative = meta.negativePrompt
  if (typeof meta.cfgScale === 'number') p.cfg = meta.cfgScale
  if (typeof meta.steps === 'number') p.steps = meta.steps
  if (typeof meta.seed === 'number') p.seed = meta.seed
  if (meta.sampler) {
    const n = norm(meta.sampler)
    const hit = samplers.find((s) => norm(s) === n) ?? samplers.find((s) => n.startsWith(norm(s)) && norm(s).length > 3)
    if (hit) p.sampler = hit
  }
  const m = typeof meta.Size === 'string' ? meta.Size.match(/(\d+)\s*x\s*(\d+)/i) : null
  if (m) {
    p.width = Number(m[1])
    p.height = Number(m[2])
  }
  return p
}

export const thumbUrl = (url: string, w = 450) => url.replace('/original=true/', `/width=${w}/`)
