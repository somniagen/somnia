<script lang="ts" generics="T">
  import type { Snippet } from 'svelte'
  import { labelOf, normalize, uid, type Item } from './util'

  interface Props {
    items: (T | Item<T>)[]
    value?: T
    label?: string
    class?: string
    style?: string
    onchange?: (v: T) => void
    children?: Snippet<[T]>
  }
  let { items, value = $bindable(), label, class: klass, style, onchange, children }: Props = $props()

  const id = uid('tabs')
  const list = $derived(normalize(items))
  const idx = $derived(Math.max(0, list.findIndex((it) => it.value === value)))
  let bar: HTMLDivElement
  let ind = $state({ x: 0, w: 0 })
  let ready = $state(false)

  function choose(i: number) {
    const it = list[i]
    if (!it || it.disabled) return
    if (it.value !== value) {
      value = it.value
      onchange?.(it.value)
    }
  }
  function key(e: KeyboardEvent) {
    const n = list.length
    let i = idx
    if (e.key === 'ArrowRight') i = (idx + 1) % n
    else if (e.key === 'ArrowLeft') i = (idx - 1 + n) % n
    else if (e.key === 'Home') i = 0
    else if (e.key === 'End') i = n - 1
    else return
    e.preventDefault()
    choose(i)
    bar.querySelectorAll<HTMLElement>('[role="tab"]')[i]?.focus()
  }
  function measure() {
    const t = bar?.querySelectorAll<HTMLElement>('[role="tab"]')[idx]
    if (t) ind = { x: t.offsetLeft, w: t.offsetWidth }
  }
  $effect(() => {
    void idx
    void list
    measure()
    requestAnimationFrame(() => (ready = true))
  })
  $effect(() => {
    const ro = new ResizeObserver(measure)
    ro.observe(bar)
    return () => ro.disconnect()
  })
</script>

<div class={['tabs', klass]} {style}>
  <div class="bar" bind:this={bar} role="tablist" aria-label={label} tabindex="-1" onkeydown={key}>
    {#each list as it, i (i)}
      <button
        type="button"
        role="tab"
        id="{id}-t{i}"
        aria-selected={i === idx}
        aria-controls="{id}-p"
        tabindex={i === idx ? 0 : -1}
        class:sel={i === idx}
        disabled={it.disabled}
        onclick={() => choose(i)}
      >
        {#if it.icon}<span class="icon" aria-hidden="true">{it.icon}</span>{/if}
        {labelOf(it)}
      </button>
    {/each}
    <span class="ind" class:ready style="transform: translateX({ind.x}px); width: {ind.w}px"></span>
  </div>
  {#if children}
    <div class="panel" id="{id}-p" role="tabpanel" aria-labelledby="{id}-t{idx}" tabindex="-1">
      {@render children(list[idx]?.value)}
    </div>
  {/if}
</div>

<style>
  .bar {
    position: relative;
    display: flex;
    gap: var(--sp-1);
    overflow-x: auto;
    scrollbar-width: none;
    box-shadow: inset 0 -1px 0 var(--hairline);
  }
  button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 40px;
    padding: 0 12px;
    border: 0;
    border-radius: var(--r-sm) var(--r-sm) 0 0;
    background: none;
    color: var(--text-muted);
    font: inherit;
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
    transition: color var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease);
  }
  button .icon {
    font-size: 18px;
  }
  button:hover:not(:disabled) {
    color: var(--text);
    background: var(--hover);
  }
  button.sel {
    color: var(--text);
  }
  button:disabled {
    opacity: 0.4;
  }
  .ind {
    position: absolute;
    left: 0;
    bottom: 0;
    height: 2px;
    border-radius: 1px;
    background: var(--grad-accent);
  }
  .ind.ready {
    transition:
      transform var(--dur) var(--ease),
      width var(--dur) var(--ease);
  }
  .panel {
    padding-top: var(--sp-4);
    outline: none;
  }
  @media (pointer: coarse) {
    button {
      height: var(--touch);
    }
  }
</style>
