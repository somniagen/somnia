<script lang="ts" generics="T">
  import { normalize, labelOf, type Item } from './util'
  import { tooltip } from './tooltip'

  interface Props {
    items: (T | Item<T>)[]
    value?: T
    size?: 'sm' | 'md'
    full?: boolean
    label?: string
    iconOnly?: boolean
    disabled?: boolean
    class?: string
    style?: string
    onchange?: (v: T) => void
  }
  let {
    items,
    value = $bindable(),
    size = 'md',
    full = false,
    label,
    iconOnly = false,
    disabled = false,
    class: klass,
    style,
    onchange,
  }: Props = $props()

  const list = $derived(normalize(items))
  const idx = $derived(list.findIndex((it) => it.value === value))
  let root: HTMLDivElement
  let ind = $state({ x: 0, w: 0 })
  let ready = $state(false)

  function choose(it: Item<T>) {
    if (it.disabled || disabled) return
    if (it.value !== value) {
      value = it.value
      onchange?.(it.value)
    }
  }
  function key(e: KeyboardEvent) {
    const d = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0
    if (!d) return
    e.preventDefault()
    const n = list.length
    let i = idx
    for (let k = 0; k < n; k++) {
      i = (i + d + n) % n
      if (!list[i].disabled) break
    }
    choose(list[i])
    root.querySelectorAll<HTMLElement>('[role="radio"]')[i]?.focus()
  }
  function measure() {
    const b = root?.querySelectorAll<HTMLElement>('[role="radio"]')[idx]
    if (!b) return
    ind = { x: b.offsetLeft, w: b.offsetWidth }
  }
  $effect(() => {
    void idx
    void list
    measure()
    requestAnimationFrame(() => (ready = true))
  })
  $effect(() => {
    const ro = new ResizeObserver(measure)
    ro.observe(root)
    return () => ro.disconnect()
  })
</script>

<div
  bind:this={root}
  class={['seg', size, klass, { full, disabled }]}
  {style}
  role="radiogroup"
  aria-label={label}
  tabindex="-1"
  onkeydown={key}
>
  {#if idx >= 0}
    <span class="ind" class:ready style="transform: translateX({ind.x}px); width: {ind.w}px"></span>
  {/if}
  {#each list as it, i (i)}
    <button
      type="button"
      role="radio"
      aria-checked={i === idx}
      aria-label={iconOnly ? labelOf(it) : undefined}
      tabindex={i === idx || (idx < 0 && i === 0) ? 0 : -1}
      class:sel={i === idx}
      disabled={it.disabled || disabled}
      onclick={() => choose(it)}
      use:tooltip={iconOnly ? { text: labelOf(it), describe: false } : null}
    >
      {#if it.icon}<span class="icon" aria-hidden="true">{it.icon}</span>{/if}
      {#if !iconOnly}<span>{labelOf(it)}</span>{/if}
    </button>
  {/each}
</div>

<style>
  .seg {
    --h: var(--control-h);
    position: relative;
    display: inline-flex;
    padding: 3px;
    gap: 2px;
    border-radius: var(--r-md);
    background: var(--grad-2);
    box-shadow: inset 0 1px 2px rgb(0 0 0 / 0.35);
    isolation: isolate;
  }
  .sm {
    --h: var(--control-h-sm);
    border-radius: var(--r-sm);
  }
  .full {
    display: flex;
  }
  .full button {
    flex: 1;
  }
  .ind {
    position: absolute;
    top: 3px;
    bottom: 3px;
    left: 0;
    z-index: -1;
    border-radius: calc(var(--r-md) - 3px);
    background: var(--grad-4);
    box-shadow: var(--sheen), var(--shadow-1);
  }
  .sm .ind {
    border-radius: calc(var(--r-sm) - 2px);
  }
  .ind.ready {
    transition:
      transform var(--dur) var(--ease),
      width var(--dur) var(--ease);
  }
  button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    height: calc(var(--h) - 6px);
    min-width: calc(var(--h) - 6px);
    padding: 0 12px;
    border: 0;
    border-radius: calc(var(--r-md) - 3px);
    background: none;
    color: var(--text-muted);
    font: inherit;
    font-size: var(--fs-sm);
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
    transition:
      color var(--dur-fast) var(--ease),
      transform var(--dur-fast) var(--ease);
  }
  .sm button {
    padding: 0 9px;
  }
  button .icon {
    font-size: 18px;
  }
  button:hover:not(:disabled) {
    color: var(--text);
  }
  button:active:not(:disabled) {
    transform: scale(0.96);
  }
  button.sel {
    color: var(--text);
  }
  button:disabled {
    opacity: 0.4;
    cursor: default;
  }
  @media (pointer: coarse) {
    .seg {
      --h: var(--touch);
    }
  }
</style>
