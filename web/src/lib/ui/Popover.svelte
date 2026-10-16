<script lang="ts">
  import type { Snippet } from 'svelte'
  import type { HTMLAttributes } from 'svelte/elements'
  import { anchorRect, layerRoot, place, portal, type Anchor, type Placement, type Side } from './util'

  interface Props extends HTMLAttributes<HTMLDivElement> {
    open?: boolean
    anchor?: Anchor
    placement?: Placement
    offset?: number
    matchWidth?: boolean
    autofocus?: boolean
    dismissible?: boolean
    el?: HTMLDivElement
    onclose?: () => void
    children?: Snippet
  }
  let {
    open = $bindable(false),
    anchor,
    placement = 'bottom-start',
    offset = 6,
    matchWidth = false,
    autofocus = false,
    dismissible = true,
    el = $bindable(),
    onclose,
    class: klass,
    style,
    children,
    ...rest
  }: Props = $props()

  let x = $state(0)
  let y = $state(0)
  let side = $state<Side>('bottom')
  let minW = $state(0)
  let raf = 0

  function close() {
    if (!open) return
    open = false
    onclose?.()
  }
  function update() {
    const r = anchorRect(anchor)
    if (!r || !el) return
    if (matchWidth) minW = r.width
    const p = place(r, el, placement, offset)
    x = p.x
    y = p.y
    side = p.side
  }
  function schedule() {
    cancelAnimationFrame(raf)
    raf = requestAnimationFrame(update)
  }

  $effect(() => {
    if (!open || !el) return
    update()
    if (autofocus) {
      const f = el.querySelector<HTMLElement>('[autofocus], input, [tabindex="0"], button:not(:disabled), [href]')
      ;(f ?? el).focus({ preventScroll: true })
    }
    const ro = new ResizeObserver(schedule)
    ro.observe(el)
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node
      if (!dismissible || el?.contains(t)) return
      if (anchor instanceof HTMLElement && anchor.contains(t)) return
      close()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || !dismissible) return
      e.stopPropagation()
      e.preventDefault()
      const inside = el?.contains(document.activeElement)
      close()
      if (inside && anchor instanceof HTMLElement) anchor.focus()
    }
    addEventListener('resize', schedule)
    addEventListener('scroll', schedule, true)
    document.addEventListener('pointerdown', onDown, true)
    document.addEventListener('keydown', onKey, true)
    return () => {
      ro.disconnect()
      cancelAnimationFrame(raf)
      removeEventListener('resize', schedule)
      removeEventListener('scroll', schedule, true)
      document.removeEventListener('pointerdown', onDown, true)
      document.removeEventListener('keydown', onKey, true)
    }
  })

  function pop(_: Element) {
    const d = side === 'top' ? 4 : side === 'bottom' ? -4 : 0
    const dx = side === 'left' ? 4 : side === 'right' ? -4 : 0
    return {
      duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 140,
      css: (t: number) =>
        `opacity: ${t}; transform: translate(${(1 - t) * dx}px, ${(1 - t) * d}px) scale(${0.97 + 0.03 * t})`,
    }
  }
</script>

{#if open}
  <div
    use:portal={layerRoot(anchor)}
    bind:this={el}
    class={['popover', klass]}
    data-side={side}
    tabindex="-1"
    style="left: {x}px; top: {y}px; {minW ? `min-width: ${minW}px;` : ''} {style ?? ''}"
    transition:pop
    {...rest}
  >
    {@render children?.()}
  </div>
{/if}

<style>
  .popover {
    position: fixed;
    z-index: var(--z-popover);
    max-width: min(420px, calc(100vw - 16px));
    max-height: min(420px, calc(100dvh - 16px));
    overflow: auto;
    padding: var(--sp-1);
    border-radius: var(--r-md);
    background: var(--grad-3);
    border: 1px solid var(--hairline);
    box-shadow: var(--shadow-3);
    color: var(--text);
    outline: none;
    transform-origin: top left;
  }
  .popover[data-side='top'] {
    transform-origin: bottom left;
  }
</style>
