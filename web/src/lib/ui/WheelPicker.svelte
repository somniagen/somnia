<script lang="ts" generics="T">
  import type { Snippet } from 'svelte'
  import { clamp, coarse, labelOf, normalize, uid, type Item } from './util'

  interface Props {
    items: (T | Item<T>)[]
    value?: T
    visible?: number
    itemHeight?: number
    label?: string
    class?: string
    style?: string
    item?: Snippet<[Item<T>, boolean]>
    onchange?: (v: T) => void
  }
  let {
    items,
    value = $bindable(),
    visible = 5,
    itemHeight,
    label,
    class: klass,
    style,
    item,
    onchange,
  }: Props = $props()

  const id = uid('wheel')
  const list = $derived(normalize(items))
  const ih = $derived(itemHeight ?? (coarse.current ? 44 : 36))
  const n = $derived(visible % 2 ? visible : visible + 1)
  const selected = $derived(Math.max(0, list.findIndex((it) => it.value === value)))

  let sc: HTMLDivElement
  let pos = $state(0)
  let settle: ReturnType<typeof setTimeout> | undefined
  let busy = false
  let ready = false
  let drag = $state<{ y: number; top: number; t: number; v: number } | null>(null)

  function onScroll() {
    pos = sc.scrollTop / ih
    busy = true
    clearTimeout(settle)
    settle = setTimeout(finish, 110)
  }
  function finish() {
    busy = false
    if (drag) return
    const i = clamp(Math.round(sc.scrollTop / ih), 0, list.length - 1)
    const it = list[i]
    if (it && it.value !== value) {
      value = it.value
      onchange?.(it.value)
    }
  }
  function go(i: number, smooth = true) {
    i = clamp(i, 0, list.length - 1)
    sc.scrollTo({ top: i * ih, behavior: smooth ? 'smooth' : 'instant' })
  }
  function key(e: KeyboardEvent) {
    const cur = Math.round(sc.scrollTop / ih)
    const map: Record<string, number> = {
      ArrowUp: cur - 1,
      ArrowDown: cur + 1,
      PageUp: cur - n,
      PageDown: cur + n,
      Home: 0,
      End: list.length - 1,
    }
    if (!(e.key in map)) return
    e.preventDefault()
    go(map[e.key])
  }
  function down(e: PointerEvent) {
    if (e.pointerType !== 'mouse' || e.button !== 0) return
    sc.setPointerCapture(e.pointerId)
    drag = { y: e.clientY, top: sc.scrollTop, t: performance.now(), v: 0 }
  }
  function move(e: PointerEvent) {
    if (!drag) return
    const now = performance.now()
    const top = drag.top - (e.clientY - drag.y)
    const dt = Math.max(1, now - drag.t)
    drag.v = 0.8 * ((sc.scrollTop - top) / dt) + 0.2 * drag.v
    drag.t = now
    sc.scrollTop = top
    drag.top = top
    drag.y = e.clientY
  }
  function up() {
    if (!drag) return
    const target = sc.scrollTop - drag.v * 180
    drag = null
    go(Math.round(target / ih))
  }

  $effect(() => {
    const i = selected
    void ih
    if (!sc || busy || drag) return
    if (Math.round(sc.scrollTop / ih) !== i || !ready) go(i, ready)
    ready = true
  })

  function itemStyle(i: number) {
    const dd = i - pos
    const a = Math.min(Math.abs(dd), (n + 1) / 2)
    return `opacity: ${Math.max(0.12, 1 - a * 0.28)}; transform: rotateX(${clamp(-dd * 16, -70, 70)}deg) scale(${1 - a * 0.04})`
  }
</script>

<div
  class={['wheel', klass, { grabbing: drag }]}
  style="--ih: {ih}px; --n: {n}; {style ?? ''}"
  role="listbox"
  tabindex="0"
  aria-label={label}
  aria-activedescendant="{id}-{selected}"
  onkeydown={key}
>
  <div class="band" aria-hidden="true"></div>
  <div
    class="scroller"
    role="presentation"
    bind:this={sc}
    onscroll={onScroll}
    onpointerdown={down}
    onpointermove={move}
    onpointerup={up}
    onpointercancel={up}
  >
    <div class="pad"></div>
    {#each list as it, i (i)}
      <div
        id="{id}-{i}"
        class="opt"
        class:sel={i === selected}
        role="option"
        aria-selected={i === selected}
        tabindex="-1"
        style={itemStyle(i)}
        onclick={() => go(i)}
        onkeydown={() => {}}
      >
        {#if item}{@render item(it, i === selected)}{:else}{labelOf(it)}{/if}
      </div>
    {/each}
    <div class="pad"></div>
  </div>
</div>

<style>
  .wheel {
    position: relative;
    height: calc(var(--ih) * var(--n));
    border-radius: var(--r-md);
    background: var(--grad-2);
    overflow: hidden;
    user-select: none;
    outline: none;
  }
  .wheel:focus-visible {
    box-shadow: var(--focus-ring);
  }
  .band {
    position: absolute;
    left: 6px;
    right: 6px;
    top: 50%;
    height: var(--ih);
    margin-top: calc(var(--ih) / -2);
    border-radius: var(--r-sm);
    background: var(--grad-4);
    pointer-events: none;
  }
  .scroller {
    position: relative;
    height: 100%;
    overflow-y: auto;
    scroll-snap-type: y mandatory;
    scrollbar-width: none;
    perspective: 600px;
    overscroll-behavior: contain;
    mask-image: linear-gradient(transparent, var(--text) 30%, var(--text) 70%, transparent);
  }
  .scroller::-webkit-scrollbar {
    display: none;
  }
  .grabbing .scroller {
    scroll-snap-type: none;
    cursor: grabbing;
  }
  .pad {
    height: calc(var(--ih) * (var(--n) - 1) / 2);
  }
  .opt {
    display: flex;
    align-items: center;
    justify-content: center;
    height: var(--ih);
    padding: 0 var(--sp-4);
    scroll-snap-align: center;
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    cursor: pointer;
    will-change: transform;
  }
  .opt.sel {
    color: var(--text);
    font-weight: 500;
  }
</style>
