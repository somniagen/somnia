import { MediaQuery } from 'svelte/reactivity'

export const mobile = new MediaQuery('(max-width: 640px)')
export const coarse = new MediaQuery('(pointer: coarse)')
export const reducedMotion = new MediaQuery('(prefers-reduced-motion: reduce)')

export const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v))

export function decimals(step: number) {
  const s = String(step)
  const i = s.indexOf('.')
  return i < 0 ? 0 : s.length - i - 1
}

export function snap(v: number, step: number, min = 0) {
  const d = decimals(step)
  return Number((Math.round((v - min) / step) * step + min).toFixed(d))
}

export type Item<T = string> = { value: T; label?: string; icon?: string; hint?: string; disabled?: boolean }

export function normalize<T>(items: (T | Item<T>)[]): Item<T>[] {
  return items.map((it) =>
    it !== null && typeof it === 'object' && 'value' in (it as object) ? (it as Item<T>) : { value: it as T, label: String(it) },
  )
}

export const labelOf = <T>(it: Item<T>) => it.label ?? String(it.value)

export type Side = 'top' | 'bottom' | 'left' | 'right'
export type Placement = Side | `${Side}-start` | `${Side}-end`
export type Anchor = HTMLElement | { x: number; y: number } | null | undefined

export function anchorRect(a: Anchor): DOMRect | null {
  if (!a) return null
  if (a instanceof HTMLElement) return a.getBoundingClientRect()
  return new DOMRect(a.x, a.y, 0, 0)
}

export function place(rect: DOMRect, el: HTMLElement, placement: Placement, offset = 6, pad = 8) {
  const [side0, align = 'center'] = placement.split('-') as [Side, string?]
  const w = el.offsetWidth
  const h = el.offsetHeight
  const vw = window.innerWidth
  const vh = window.innerHeight
  let side = side0
  const room = {
    top: rect.top - pad,
    bottom: vh - rect.bottom - pad,
    left: rect.left - pad,
    right: vw - rect.right - pad,
  }
  const opp: Record<Side, Side> = { top: 'bottom', bottom: 'top', left: 'right', right: 'left' }
  const need = side === 'top' || side === 'bottom' ? h + offset : w + offset
  if (room[side] < need && room[opp[side]] > room[side]) side = opp[side]
  let x: number
  let y: number
  if (side === 'top' || side === 'bottom') {
    y = side === 'bottom' ? rect.bottom + offset : rect.top - offset - h
    x = align === 'start' ? rect.left : align === 'end' ? rect.right - w : rect.left + rect.width / 2 - w / 2
    x = clamp(x, pad, Math.max(pad, vw - w - pad))
    y = clamp(y, pad, Math.max(pad, vh - h - pad))
  } else {
    x = side === 'right' ? rect.right + offset : rect.left - offset - w
    y = align === 'start' ? rect.top : align === 'end' ? rect.bottom - h : rect.top + rect.height / 2 - h / 2
    y = clamp(y, pad, Math.max(pad, vh - h - pad))
    x = clamp(x, pad, Math.max(pad, vw - w - pad))
  }
  return { x, y, side }
}

export function layerRoot(a: Anchor): HTMLElement {
  if (a instanceof HTMLElement) {
    const d = a.closest('dialog')
    if (d) return d
  }
  return document.body
}

export function portal(node: HTMLElement, target?: HTMLElement) {
  ;(target ?? document.body).appendChild(node)
  return {
    update(t?: HTMLElement) {
      ;(t ?? document.body).appendChild(node)
    },
    destroy() {
      node.remove()
    },
  }
}

let n = 0
export const uid = (p = 'ui') => `${p}-${++n}`
