export interface FindResult {
  total: number
  groups: Record<string, number>
}

const HL = 'settings-find'

// material icon ligatures are text too
const iconText = (n: Node) => !!n.parentElement?.closest('.icon')

function text(el: Element) {
  let out = ''
  const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
  for (let n = walk.nextNode(); n; n = walk.nextNode()) if (!iconText(n)) out += ` ${n.textContent}`
  return out
}

function hay(el: Element) {
  const extra = [...el.querySelectorAll('[data-tip], [placeholder], [data-find]')].map(
    (e) => `${e.getAttribute('data-tip') ?? ''} ${e.getAttribute('placeholder') ?? ''} ${e.getAttribute('data-find') ?? ''}`,
  )
  return `${el.getAttribute('data-find') ?? ''} ${text(el)} ${extra.join(' ')}`.toLowerCase()
}

const all = (h: string, terms: string[]) => terms.every((t) => h.includes(t))

function mark(el: Element, terms: string[], ranges: Range[]) {
  const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
  for (let n = walk.nextNode(); n; n = walk.nextNode()) {
    if (iconText(n)) continue
    const text = (n.textContent ?? '').toLowerCase()
    for (const t of terms) {
      for (let i = text.indexOf(t); i >= 0; i = text.indexOf(t, i + t.length)) {
        const r = new Range()
        r.setStart(n, i)
        r.setEnd(n, i + t.length)
        ranges.push(r)
      }
    }
  }
  for (const tip of el.querySelectorAll('[data-tip]')) {
    const t = (tip.getAttribute('data-tip') ?? '').toLowerCase()
    tip.toggleAttribute('data-hit', terms.some((x) => t.includes(x)))
  }
}

// groups are [data-group] blocks of cards, rows are the direct children of a card's .stack
export function applyFind(root: HTMLElement, query: string): FindResult {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean)
  const res: FindResult = { total: 0, groups: {} }
  const ranges: Range[] = []
  for (const el of root.querySelectorAll('[data-miss], [data-hit]')) {
    el.removeAttribute('data-miss')
    el.removeAttribute('data-hit')
  }
  for (const g of root.querySelectorAll<HTMLElement>('[data-group]')) {
    let gn = 0
    if (terms.length) {
      const gh = (g.getAttribute('data-find') ?? '').toLowerCase()
      for (const card of g.querySelectorAll(':scope > section')) {
        const head = card.querySelector(':scope > header')
        const ch = `${gh} ${head ? hay(head) : ''}`
        const whole = all(ch, terms)
        let cn = 0
        for (const row of card.querySelectorAll(':scope > .stack > *')) {
          const hit = whole || all(`${ch} ${hay(row)}`, terms)
          row.toggleAttribute('data-miss', !hit)
          if (hit) {
            cn++
            mark(row, terms, ranges)
          }
        }
        card.toggleAttribute('data-miss', !cn)
        if (cn && head) mark(head, terms, ranges)
        gn += cn
      }
      g.toggleAttribute('data-miss', !gn)
    }
    res.groups[g.dataset.group!] = gn
    res.total += gn
  }
  if (typeof Highlight !== 'undefined') {
    if (ranges.length) CSS.highlights.set(HL, new Highlight(...ranges))
    else CSS.highlights.delete(HL)
  }
  return res
}

export function clearFind() {
  if (typeof Highlight !== 'undefined') CSS.highlights.delete(HL)
}
