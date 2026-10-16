<script lang="ts">
  import type { Snippet } from 'svelte'
  import { clamp, uid } from './util'

  interface Props {
    open?: boolean
    title?: string
    snaps?: number[]
    snap?: number
    dismissible?: boolean
    class?: string
    style?: string
    onclose?: () => void
    header?: Snippet
    footer?: Snippet
    children?: Snippet
  }
  let {
    open = $bindable(false),
    title,
    snaps,
    snap = $bindable(0),
    dismissible = true,
    class: klass,
    style,
    onclose,
    header,
    footer,
    children,
  }: Props = $props()

  const tid = uid('sheet')
  let dlg: HTMLDialogElement
  let panel: HTMLDivElement
  let body: HTMLDivElement
  let shown = $state(false)
  let drag = $state(0)
  let dragging = $state(false)
  let vh = $state(typeof window === 'undefined' ? 800 : window.innerHeight)
  let downOnSelf = false
  let ret: Element | null = null
  let g: { y: number; t: number; v: number; last: number } | null = null

  const top = $derived(snaps?.length ? Math.max(...snaps) : 0)
  const base = $derived(snaps?.length ? (top - snaps[clamp(snap, 0, snaps.length - 1)]) * vh : 0)
  const ty = $derived(Math.max(base + drag, -12))

  function close() {
    if (!open) return
    open = false
    onclose?.()
  }

  $effect(() => {
    if (open && !dlg.open) {
      ret = document.activeElement
      drag = 0
      dlg.showModal()
      document.documentElement.style.overflow = 'hidden'
      requestAnimationFrame(() => requestAnimationFrame(() => (shown = true)))
    } else if (!open && dlg.open) {
      shown = false
      setTimeout(() => {
        if (open) return
        dlg.close()
        drag = 0
        document.documentElement.style.overflow = ''
        if (ret instanceof HTMLElement) ret.focus({ preventScroll: true })
      }, 300)
    }
  })
  $effect(() => {
    const r = () => (vh = window.innerHeight)
    addEventListener('resize', r)
    return () => {
      removeEventListener('resize', r)
      if (dlg?.open) document.documentElement.style.overflow = ''
    }
  })

  function start(y: number) {
    g = { y, t: performance.now(), v: 0, last: y }
  }
  function moveTo(y: number) {
    if (!g) return
    const now = performance.now()
    g.v = 0.7 * ((y - g.last) / Math.max(1, now - g.t)) + 0.3 * g.v
    g.t = now
    g.last = y
    dragging = true
    const dy = y - g.y
    drag = dy < 0 ? dy * 0.35 : dy
  }
  function end() {
    if (!g) return
    const v = g.v
    g = null
    dragging = false
    const h = panel.offsetHeight
    if (!snaps?.length) {
      if (dismissible && (drag > h * 0.3 || v > 0.6)) close()
      drag = 0
      return
    }
    const f = top - (base + drag) / vh
    let i: number
    if (v > 0.6) i = snap - 1
    else if (v < -0.6) i = snap + 1
    else i = snaps.reduce((b, s, k) => (Math.abs(s - f) < Math.abs(snaps[b] - f) ? k : b), 0)
    if (i < 0 || (f < snaps[0] * 0.6 && v >= 0)) {
      if (dismissible) close()
      i = 0
    }
    snap = clamp(i, 0, snaps.length - 1)
    drag = 0
  }

  function hDown(e: PointerEvent) {
    if (e.button !== 0) return
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    start(e.clientY)
  }

  $effect(() => {
    let y0 = 0
    let active = false
    const ts = (e: TouchEvent) => {
      y0 = e.touches[0].clientY
      active = false
    }
    const tm = (e: TouchEvent) => {
      const y = e.touches[0].clientY
      if (!active && body.scrollTop <= 0 && y - y0 > 6) {
        active = true
        start(y0)
      }
      if (active) {
        e.preventDefault()
        moveTo(y)
      }
    }
    const te = () => {
      if (active) end()
      active = false
    }
    body.addEventListener('touchstart', ts, { passive: true })
    body.addEventListener('touchmove', tm, { passive: false })
    body.addEventListener('touchend', te)
    body.addEventListener('touchcancel', te)
    return () => {
      body.removeEventListener('touchstart', ts)
      body.removeEventListener('touchmove', tm)
      body.removeEventListener('touchend', te)
      body.removeEventListener('touchcancel', te)
    }
  })
</script>

<dialog
  bind:this={dlg}
  class="sheet"
  class:shown
  aria-labelledby={title ? tid : undefined}
  oncancel={(e) => {
    e.preventDefault()
    if (dismissible) close()
  }}
  onpointerdown={(e) => (downOnSelf = e.target === dlg)}
  onclick={(e) => {
    if (dismissible && downOnSelf && e.target === dlg) close()
  }}
>
  <div
    bind:this={panel}
    class={['panel', klass, { dragging, snapped: snaps?.length }]}
    style="{snaps?.length ? `height: ${top * 100}dvh;` : ''} {shown ? `transform: translateY(${ty}px);` : ''} {style ?? ''}"
  >
    <div
      class="grab"
      role="presentation"
      onpointerdown={hDown}
      onpointermove={(e) => g && moveTo(e.clientY)}
      onpointerup={end}
      onpointercancel={end}
    >
      <span class="handle"></span>
      {#if header}
        {@render header()}
      {:else if title}
        <h2 id={tid}>{title}</h2>
      {/if}
    </div>
    <div class="body" bind:this={body}>{@render children?.()}</div>
    {#if footer}<footer>{@render footer()}</footer>{/if}
  </div>
</dialog>

<style>
  .sheet {
    position: fixed;
    inset: 0;
    width: 100%;
    height: 100%;
    max-width: none;
    max-height: none;
    margin: 0;
    padding: 0;
    border: 0;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    background: var(--scrim);
    color: var(--text);
    opacity: 0;
    transition: opacity 260ms var(--ease);
    overscroll-behavior: contain;
  }
  .sheet:not([open]) {
    display: none;
  }
  .sheet::backdrop {
    background: transparent;
  }
  .sheet.shown {
    opacity: 1;
  }
  .panel {
    display: flex;
    flex-direction: column;
    width: 100%;
    max-height: 92dvh;
    border-radius: var(--r-lg) var(--r-lg) 0 0;
    background: var(--grad-1);
    border: 1px solid var(--hairline);
    border-bottom: 0;
    box-shadow: var(--shadow-3);
    padding-bottom: env(safe-area-inset-bottom);
    transform: translateY(100%);
    transition: transform 300ms var(--ease);
    will-change: transform;
  }
  .panel.dragging {
    transition: none;
  }
  .grab {
    flex: none;
    padding: 8px var(--sp-4) var(--sp-2);
    touch-action: none;
    cursor: grab;
  }
  .handle {
    display: block;
    width: 36px;
    height: 4px;
    margin: 0 auto var(--sp-2);
    border-radius: 2px;
    background: var(--grad-4);
  }
  h2 {
    margin: 0;
    font-size: var(--fs-lg);
    font-weight: 600;
  }
  .body {
    flex: 1;
    min-height: 0;
    overflow: auto;
    overscroll-behavior: contain;
    padding: var(--sp-2) var(--sp-4) var(--sp-4);
  }
  footer {
    display: flex;
    gap: var(--sp-2);
    padding: 0 var(--sp-4) var(--sp-4);
  }
  footer :global(> *) {
    flex: 1;
  }
  @media (prefers-reduced-motion: reduce) {
    .panel {
      transition-duration: 0ms;
    }
  }
</style>
