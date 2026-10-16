import { place, uid, type Placement } from './util'
import './global.css'

export type TooltipOptions = string | { text: string; placement?: Placement; describe?: boolean; delay?: number } | null | undefined

function opts(o: TooltipOptions) {
  if (!o) return null
  if (typeof o === 'string') return { text: o, placement: 'top' as Placement, describe: true, delay: 350 }
  return { placement: 'top' as Placement, describe: true, delay: 350, ...o }
}

export function tooltip(node: HTMLElement, options: TooltipOptions) {
  let o = opts(options)
  let el: HTMLDivElement | null = null
  let timer: ReturnType<typeof setTimeout> | undefined
  const id = uid('tip')

  function show() {
    if (!o || !o.text || el) return
    el = document.createElement('div')
    el.className = 'ui-tooltip'
    el.id = id
    el.role = 'tooltip'
    el.textContent = o.text
    ;(node.closest('dialog') ?? document.body).appendChild(el)
    const p = place(node.getBoundingClientRect(), el, o.placement)
    el.style.left = `${p.x}px`
    el.style.top = `${p.y}px`
    el.dataset.side = p.side
    requestAnimationFrame(() => el?.classList.add('in'))
    if (o.describe) node.setAttribute('aria-describedby', id)
    addEventListener('keydown', onKey, true)
    addEventListener('scroll', hide, true)
  }
  function hide() {
    clearTimeout(timer)
    if (!el) return
    el.remove()
    el = null
    if (node.getAttribute('aria-describedby') === id) node.removeAttribute('aria-describedby')
    removeEventListener('keydown', onKey, true)
    removeEventListener('scroll', hide, true)
  }
  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') hide()
  }
  function enter(e: PointerEvent) {
    if (e.pointerType === 'touch') return
    clearTimeout(timer)
    timer = setTimeout(show, o?.delay ?? 350)
  }
  function focus() {
    if (node.matches(':focus-visible')) show()
  }
  node.addEventListener('pointerenter', enter)
  node.addEventListener('pointerleave', hide)
  node.addEventListener('pointerdown', hide)
  node.addEventListener('focus', focus)
  node.addEventListener('blur', hide)
  return {
    update(next: TooltipOptions) {
      o = opts(next)
      if (el && o) el.textContent = o.text
      if (el && !o) hide()
    },
    destroy() {
      hide()
      node.removeEventListener('pointerenter', enter)
      node.removeEventListener('pointerleave', hide)
      node.removeEventListener('pointerdown', hide)
      node.removeEventListener('focus', focus)
      node.removeEventListener('blur', hide)
    },
  }
}
