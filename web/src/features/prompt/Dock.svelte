<script lang="ts">
  import type { Snippet } from 'svelte'
  import { portal } from '$lib/ui'

  interface Props {
    open: boolean
    avoid?: () => DOMRect | null | undefined
    label?: string
    class?: string
    keep?: () => (HTMLElement | null | undefined)[]
    onclose?: () => void
    children: Snippet
  }
  let { open = $bindable(false), avoid, label, class: klass, keep, onclose, children }: Props = $props()

  let el = $state<HTMLDivElement>()
  let top = $state(0)
  let room = $state(320)
  let atTop = $state(false)
  let raf = 0

  function update() {
    if (!el) return
    const vv = window.visualViewport
    const ot = vv?.offsetTop ?? 0
    const vh = vv?.height ?? innerHeight
    room = Math.max(120, Math.round(vh * 0.42))
    const h = el.offsetHeight
    const a = avoid?.()
    let t = ot + vh - h - 8
    atTop = false
    if (a && a.bottom + 4 > t && a.top - 4 > ot + h + 8) {
      t = ot + 8
      atTop = true
    } else if (a && a.bottom + 4 > t) {
      t = Math.min(ot + vh - h - 8, a.bottom + 8)
    }
    top = Math.max(ot + 8, t)
  }
  function schedule() {
    cancelAnimationFrame(raf)
    raf = requestAnimationFrame(update)
  }

  $effect(() => {
    if (!open || !el) return
    update()
    const vv = window.visualViewport
    const ro = new ResizeObserver(schedule)
    ro.observe(el)
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node
      if (el?.contains(t) || keep?.().some((k) => k?.contains(t))) return
      open = false
      onclose?.()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      open = false
      onclose?.()
    }
    vv?.addEventListener('resize', schedule)
    vv?.addEventListener('scroll', schedule)
    addEventListener('resize', schedule)
    addEventListener('scroll', schedule, true)
    document.addEventListener('pointerdown', onDown, true)
    document.addEventListener('keydown', onKey, true)
    return () => {
      ro.disconnect()
      cancelAnimationFrame(raf)
      vv?.removeEventListener('resize', schedule)
      vv?.removeEventListener('scroll', schedule)
      removeEventListener('resize', schedule)
      removeEventListener('scroll', schedule, true)
      document.removeEventListener('pointerdown', onDown, true)
      document.removeEventListener('keydown', onKey, true)
    }
  })

  function rise(_: Element) {
    return {
      duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 160,
      css: (t: number) => `opacity: ${t}; transform: translateY(${(1 - t) * (atTop ? -8 : 8)}px)`,
    }
  }
</script>

{#if open}
  <div
    use:portal
    bind:this={el}
    class={['dock', klass]}
    role="dialog"
    aria-label={label}
    style="top: {top}px; --room: {room}px"
    transition:rise
  >
    {@render children()}
  </div>
{/if}

<style>
  .dock {
    position: fixed;
    left: 8px;
    right: 8px;
    z-index: var(--z-popover);
    max-width: 480px;
    margin: 0 auto;
    max-height: var(--room);
    overflow: auto;
    overscroll-behavior: contain;
    border-radius: var(--r-lg);
    background: var(--surface-3);
    border: 1px solid var(--hairline);
    box-shadow: var(--shadow-3);
    color: var(--text);
  }
</style>
