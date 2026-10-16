export type TokenKind = 'tag' | 'sep' | 'syntax' | 'weight' | 'lora' | 'break' | 'space'

export interface Token {
  kind: TokenKind
  text: string
  start: number
  tag?: string
}

const SYNTAX = '()[]{}'
const WEIGHT = /^:\s*-?\d*\.?\d+\s*(?=[)\]])/

export function normalizeTag(s: string): string {
  return s
    .trim()
    .replace(/\\([()[\]])/g, '$1')
    .replace(/\s+/g, '_')
    .toLowerCase()
}

export function displayTag(name: string): string {
  return name.replace(/_/g, ' ').replace(/([()[\]])/g, '\\$1')
}

export function tokenize(text: string): Token[] {
  const out: Token[] = []
  let i = 0
  let run = -1
  const flush = (end: number) => {
    if (run < 0) return
    pushRun(out, text.slice(run, end), run)
    run = -1
  }
  while (i < text.length) {
    const c = text[i]
    if (c === '\\' && i + 1 < text.length) {
      if (run < 0) run = i
      i += 2
      continue
    }
    if (c === ',' || c === '\n') {
      flush(i)
      out.push({ kind: 'sep', text: c, start: i })
      i++
      continue
    }
    if (SYNTAX.includes(c)) {
      flush(i)
      out.push({ kind: 'syntax', text: c, start: i })
      i++
      continue
    }
    if (c === '<') {
      const j = text.indexOf('>', i)
      const nl = text.indexOf('\n', i)
      if (j > 0 && (nl < 0 || nl > j)) {
        flush(i)
        out.push({ kind: 'lora', text: text.slice(i, j + 1), start: i })
        i = j + 1
        continue
      }
    }
    if (c === ':') {
      const m = WEIGHT.exec(text.slice(i, i + 16))
      if (m) {
        flush(i)
        out.push({ kind: 'weight', text: m[0], start: i })
        i += m[0].length
        continue
      }
    }
    if (run < 0) run = i
    i++
  }
  flush(text.length)
  return out
}

function pushRun(out: Token[], s: string, start: number) {
  const lead = s.length - s.trimStart().length
  const body = s.trim()
  if (lead) out.push({ kind: 'space', text: s.slice(0, lead), start })
  if (body) {
    const at = start + lead
    if (body === 'BREAK') out.push({ kind: 'break', text: body, start: at })
    else out.push({ kind: 'tag', text: body, start: at, tag: normalizeTag(body) })
  }
  const trail = s.length - lead - body.length
  if (trail > 0 && body) out.push({ kind: 'space', text: s.slice(s.length - trail), start: start + s.length - trail })
}

// bounds of the tag fragment around the caret, or null when the caret is not inside a taggable spot
export function fragmentAt(text: string, caret: number): { start: number; end: number; query: string } | null {
  let s = caret
  while (s > 0) {
    const c = text[s - 1]
    if (c === ',' || c === '\n' || c === '<' || c === '>' || ((c === '(' || c === '[' || c === '{') && text[s - 2] !== '\\')) break
    s--
  }
  if (text[s - 1] === '<') return null
  let e = caret
  while (e < text.length) {
    const c = text[e]
    if (c === ',' || c === '\n' || c === '<' || ((c === ')' || c === ']' || c === '}' || c === ':') && text[e - 1] !== '\\')) break
    e++
  }
  while (s < e && /\s/.test(text[s])) s++
  while (e > s && /\s/.test(text[e - 1])) e--
  const query = text.slice(s, caret)
  if (caret < s || !query.trim() || /:[\d.\s-]*$/.test(query) || /^[\d.\s]+$/.test(query) || query === 'BREAK') return null
  return { start: s, end: Math.max(e, caret), query }
}

export function estimateTokens(text: string): number {
  let n = 0
  for (const m of text.matchAll(/[a-z0-9]+|[^\sa-z0-9]/gi)) n += m[0].length > 7 ? Math.ceil(m[0].length / 5) : 1
  return n
}

const unescaped = (s: string, re: RegExp) => (s.replace(/\\./g, '').match(re) ?? []).length

function balanced(s: string) {
  return unescaped(s, /[(]/g) === unescaped(s, /[)]/g) && unescaped(s, /\[/g) === unescaped(s, /\]/g)
}

export interface Weighted {
  // replaced range, including any (...:w) wrapper
  start: number
  end: number
  inner: string
  weight: number
}

// the weighted item at a selection or around the caret: "(tag:1.2)", "(tag)" (1.1) or a bare "tag" (1)
export function weightAt(text: string, s: number, e: number): Weighted | null {
  let a = s
  let b = e
  if (a === b) {
    while (a > 0 && text[a - 1] !== ',' && text[a - 1] !== '\n') a--
    while (b < text.length && text[b] !== ',' && text[b] !== '\n') b++
  }
  while (a < b && /\s/.test(text[a])) a++
  while (b > a && /\s/.test(text[b - 1])) b--
  const seg = text.slice(a, b)
  if (!seg || seg.startsWith('<') || seg === 'BREAK' || !balanced(seg)) return null
  let m = /^\(([^]*):\s*(-?\d*\.?\d+)\s*\)$/.exec(seg)
  if (m && balanced(m[1])) return { start: a, end: b, inner: m[1], weight: Number(m[2]) }
  if (/^\([^]*\)$/.test(seg) && balanced(seg.slice(1, -1))) return { start: a, end: b, inner: seg.slice(1, -1), weight: 1.1 }
  // a selection of the text inside an existing wrapper
  if (text[a - 1] === '(' && text[a - 2] !== '\\') {
    m = /^:\s*(-?\d*\.?\d+)\s*\)/.exec(text.slice(b))
    if (m) return { start: a - 1, end: b + m[0].length, inner: seg, weight: Number(m[1]) }
    if (text[b] === ')') return { start: a - 1, end: b + 1, inner: seg, weight: 1.1 }
  }
  return { start: a, end: b, inner: seg, weight: 1 }
}

// steps the weight; weight 1 drops the wrapper. sel is the inner text range after the edit
export function reweight(text: string, s: number, e: number, delta: number) {
  const w = weightAt(text, s, e)
  if (!w) return null
  const weight = Math.min(3, Math.max(0, Math.round((w.weight + delta) * 100) / 100))
  const out = weight === 1 ? w.inner : `(${w.inner}:${weight})`
  const lead = weight === 1 ? 0 : 1
  return {
    start: w.start,
    end: w.end,
    out,
    weight,
    sel: [w.start + lead, w.start + lead + w.inner.length] as [number, number],
  }
}
