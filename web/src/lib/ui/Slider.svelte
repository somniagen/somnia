<script lang="ts">
  import type { HTMLAttributes } from 'svelte/elements'
  import { clamp, decimals, snap } from './util'

  type Mark = number | { value: number; label?: string }
  interface Props extends Omit<HTMLAttributes<HTMLDivElement>, 'onchange' | 'oninput'> {
    value?: number
    min?: number
    max?: number
    step?: number
    defaultValue?: number
    marks?: Mark[]
    editable?: boolean
    disabled?: boolean
    label?: string
    id?: string
    format?: (v: number) => string
    oninput?: (v: number) => void
    onchange?: (v: number) => void
  }
  let {
    value = $bindable(0),
    min = 0,
    max = 100,
    step = 1,
    defaultValue,
    marks,
    editable = true,
    disabled = false,
    label,
    id,
    format,
    oninput,
    onchange,
    class: klass,
    ...rest
  }: Props = $props()

  let track: HTMLDivElement
  let thumb: HTMLDivElement
  let dragging = $state(false)
  let raw = 0
  let lastX = 0
  let pendingTouch = false
  let draft = $state<string | null>(null)

  const d = $derived(decimals(step))
  const fmt = (v: number) => (format ? format(v) : v.toFixed(d))
  const pct = $derived(((clamp(value, min, max) - min) / (max - min || 1)) * 100)
  const markList = $derived(
    (marks ?? []).map((m) => (typeof m === 'number' ? { value: m, label: undefined } : m)),
  )

  function set(v: number) {
    const nv = clamp(snap(clamp(v, min, max), step, min), min, max)
    if (nv !== value) {
      value = nv
      oninput?.(nv)
    }
  }
  function commit() {
    onchange?.(value)
  }
  function fromX(x: number) {
    const r = track.getBoundingClientRect()
    return min + clamp((x - r.left) / r.width, 0, 1) * (max - min)
  }
  function down(e: PointerEvent) {
    if (disabled || e.button !== 0) return
    track.setPointerCapture(e.pointerId)
    dragging = true
    lastX = e.clientX
    raw = value
    pendingTouch = e.pointerType === 'touch'
    if (!pendingTouch && !e.shiftKey) set((raw = fromX(e.clientX)))
    thumb.focus({ preventScroll: true })
    if (!pendingTouch) e.preventDefault()
  }
  function move(e: PointerEvent) {
    if (!dragging) return
    const r = track.getBoundingClientRect()
    const dx = e.clientX - lastX
    lastX = e.clientX
    if (e.shiftKey) raw = clamp(raw + (dx / r.width) * (max - min) * 0.1, min, max)
    else raw = fromX(e.clientX)
    pendingTouch = false
    set(raw)
  }
  function up(e: PointerEvent) {
    if (!dragging) return
    dragging = false
    if (pendingTouch && e.type === 'pointerup') set(fromX(e.clientX))
    pendingTouch = false
    commit()
  }
  function reset() {
    if (defaultValue === undefined || disabled) return
    set(defaultValue)
    commit()
  }
  function key(e: KeyboardEvent) {
    if (disabled) return
    const big = Math.max(step, (max - min) / 10)
    const k = e.key
    let v: number | null = null
    if (k === 'ArrowRight' || k === 'ArrowUp') v = value + (e.shiftKey ? step * 10 : step)
    else if (k === 'ArrowLeft' || k === 'ArrowDown') v = value - (e.shiftKey ? step * 10 : step)
    else if (k === 'PageUp') v = value + big
    else if (k === 'PageDown') v = value - big
    else if (k === 'Home') v = min
    else if (k === 'End') v = max
    else if (k === 'Delete' || k === 'Backspace') return reset()
    if (v === null) return
    e.preventDefault()
    set(v)
    commit()
  }
  function commitDraft() {
    if (draft === null) return
    const n = parseFloat(draft.replace(',', '.'))
    draft = null
    if (Number.isFinite(n)) {
      set(n)
      commit()
    }
  }
  function inputKey(e: KeyboardEvent) {
    const t = e.currentTarget as HTMLInputElement
    if (e.key === 'Enter') t.blur()
    else if (e.key === 'Escape') {
      draft = null
      t.blur()
    } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault()
      draft = null
      set(value + (e.key === 'ArrowUp' ? 1 : -1) * step * (e.shiftKey ? 10 : 1))
      commit()
    }
  }
</script>

<div class={['slider', klass, { disabled, dragging, marked: markList.length > 0 }]} {...rest}>
  <div
    class="track"
    bind:this={track}
    onpointerdown={down}
    onpointermove={move}
    onpointerup={up}
    onpointercancel={up}
    ondblclick={reset}
    role="presentation"
  >
    <div class="rail">
      <div class="fill" style="width: {pct}%"></div>
    </div>
    {#each markList as m (m.value)}
      {@const p = ((m.value - min) / (max - min || 1)) * 100}
      <span class="mark" class:passed={m.value <= value} style="left: {p}%"></span>
      {#if m.label}<span class="mark-label" style="left: {p}%">{m.label}</span>{/if}
    {/each}
    <div
      bind:this={thumb}
      class="thumb"
      style="left: {pct}%"
      role="slider"
      {id}
      tabindex={disabled ? -1 : 0}
      aria-label={label}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-valuetext={fmt(value)}
      aria-disabled={disabled || undefined}
      onkeydown={key}
    ></div>
  </div>
  {#if editable}
    <input
      class="num"
      type="text"
      inputmode="decimal"
      aria-label={label ? `${label} value` : 'Value'}
      {disabled}
      value={draft ?? fmt(value)}
      oninput={(e) => (draft = e.currentTarget.value)}
      onfocus={(e) => e.currentTarget.select()}
      onblur={commitDraft}
      onkeydown={inputKey}
    />
  {/if}
</div>

<style>
  .slider {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    min-width: 0;
  }
  .slider.marked {
    padding-bottom: 14px;
  }
  .track {
    position: relative;
    flex: 1;
    min-width: 60px;
    height: 28px;
    cursor: pointer;
    touch-action: pan-y;
  }
  .rail {
    position: absolute;
    left: 0;
    right: 0;
    top: 50%;
    height: 4px;
    margin-top: -2px;
    border-radius: 2px;
    background: var(--grad-4);
    overflow: hidden;
  }
  .fill {
    height: 100%;
    background: var(--grad-progress);
    border-radius: 2px;
  }
  .thumb {
    position: absolute;
    top: 50%;
    width: 16px;
    height: 16px;
    margin: -8px 0 0 -8px;
    border-radius: 50%;
    background: var(--grad-accent);
    box-shadow: var(--shadow-1), 0 0 8px -1px var(--accent-glow);
    transition:
      transform var(--dur-fast) var(--ease),
      box-shadow var(--dur) var(--ease);
  }
  .track:hover .thumb,
  .dragging .thumb {
    transform: scale(1.12);
    box-shadow:
      var(--shadow-1),
      0 0 0 6px var(--accent-soft);
  }
  .thumb:focus-visible {
    box-shadow: var(--focus-ring);
  }
  .mark {
    position: absolute;
    top: 50%;
    width: 2px;
    height: 8px;
    margin: -4px 0 0 -1px;
    border-radius: 1px;
    background: var(--text-faint);
    pointer-events: none;
  }
  .mark.passed {
    background: var(--text-on-accent);
    opacity: 0.6;
  }
  .mark-label {
    position: absolute;
    top: calc(100% + 0px);
    transform: translateX(-50%);
    font-size: var(--fs-xs);
    color: var(--text-faint);
    white-space: nowrap;
    pointer-events: none;
  }
  .num {
    flex: none;
    width: 58px;
    height: var(--control-h-sm);
    padding: 0 8px;
    border: 0;
    border-radius: var(--r-sm);
    background: var(--grad-2);
    color: var(--text);
    font: inherit;
    font-size: var(--fs-sm);
    font-variant-numeric: tabular-nums;
    text-align: right;
    transition: background var(--dur-fast) var(--ease);
  }
  .num:hover {
    background: var(--grad-3);
  }
  .num:focus {
    background: var(--grad-3);
  }
  .disabled {
    opacity: 0.45;
  }
  .disabled .track {
    cursor: default;
  }
  @media (pointer: coarse) {
    .track {
      height: var(--touch);
    }
    .thumb {
      width: 22px;
      height: 22px;
      margin: -11px 0 0 -11px;
    }
    .num {
      height: 36px;
    }
  }
</style>
