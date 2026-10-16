<script lang="ts">
  import type { HTMLAttributes } from 'svelte/elements'
  import { clamp, decimals, snap } from './util'

  interface Props extends Omit<HTMLAttributes<HTMLDivElement>, 'onchange'> {
    value?: number
    min?: number
    max?: number
    step?: number
    defaultValue?: number
    label?: string
    icon?: string
    suffix?: string
    steppers?: boolean
    disabled?: boolean
    id?: string
    size?: 'sm' | 'md'
    onchange?: (v: number) => void
  }
  let {
    value = $bindable(0),
    min = -Infinity,
    max = Infinity,
    step = 1,
    defaultValue,
    label,
    icon,
    suffix,
    steppers = true,
    disabled = false,
    id,
    size = 'md',
    onchange,
    class: klass,
    ...rest
  }: Props = $props()

  let draft = $state<string | null>(null)
  let scrubbing = $state(false)
  let input: HTMLInputElement
  let startX = 0
  let startV = 0
  let moved = false

  const d = $derived(decimals(step))
  const base = $derived(Number.isFinite(min) ? min : 0)

  function set(v: number) {
    const nv = clamp(snap(v, step, base), min, max)
    if (nv !== value) {
      value = nv
      onchange?.(nv)
    }
  }
  function bump(dir: number, e?: { shiftKey: boolean; altKey?: boolean }) {
    const m = e?.shiftKey ? 10 : e?.altKey ? 0.1 : 1
    draft = null
    set(value + dir * step * m)
  }
  function commitDraft() {
    if (draft === null) return
    const n = parseFloat(draft.replace(',', '.'))
    draft = null
    if (Number.isFinite(n)) set(n)
  }
  function key(e: KeyboardEvent) {
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault()
      bump(e.key === 'ArrowUp' ? 1 : -1, e)
    } else if (e.key === 'Enter') input.blur()
    else if (e.key === 'Escape') {
      draft = null
      input.blur()
    }
  }
  function wheel(e: WheelEvent) {
    if (disabled || document.activeElement !== input) return
    e.preventDefault()
    bump(e.deltaY < 0 ? 1 : -1, e)
  }
  function scrubDown(e: PointerEvent) {
    if (disabled || e.button !== 0) return
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    scrubbing = true
    moved = false
    startX = e.clientX
    startV = value
    e.preventDefault()
  }
  function scrubMove(e: PointerEvent) {
    if (!scrubbing) return
    const dx = e.clientX - startX
    if (!moved && Math.abs(dx) < 3) return
    moved = true
    const px = e.shiftKey ? 20 : 4
    draft = null
    set(startV + Math.round(dx / px) * step)
  }
  function scrubUp() {
    if (!scrubbing) return
    scrubbing = false
    if (!moved) input.focus()
  }
  function reset() {
    if (defaultValue !== undefined && !disabled) set(defaultValue)
  }

  $effect(() => {
    input.addEventListener('wheel', wheel, { passive: false })
    return () => input.removeEventListener('wheel', wheel)
  })
</script>

<div class={['nf', size, klass, { disabled, scrubbing }]} {...rest}>
  {#if label || icon}
    <span
      class="scrub"
      role="presentation"
      onpointerdown={scrubDown}
      onpointermove={scrubMove}
      onpointerup={scrubUp}
      onpointercancel={scrubUp}
      ondblclick={reset}
    >
      {#if icon}<span class="icon" aria-hidden="true">{icon}</span>{/if}
      {#if label}<span class="lbl">{label}</span>{/if}
    </span>
  {/if}
  <input
    bind:this={input}
    {id}
    type="text"
    inputmode={d > 0 || min < 0 ? 'decimal' : 'numeric'}
    role="spinbutton"
    aria-label={label}
    aria-valuenow={value}
    aria-valuemin={Number.isFinite(min) ? min : undefined}
    aria-valuemax={Number.isFinite(max) ? max : undefined}
    {disabled}
    value={draft ?? value.toFixed(d)}
    oninput={(e) => (draft = e.currentTarget.value)}
    onfocus={(e) => e.currentTarget.select()}
    onblur={commitDraft}
    onkeydown={key}
  />
  {#if suffix}<span class="suffix">{suffix}</span>{/if}
  {#if steppers}
    <span class="steps">
      <button type="button" tabindex="-1" aria-label="Decrease" {disabled} onclick={(e) => bump(-1, e)}>
        <span class="icon">remove</span>
      </button>
      <button type="button" tabindex="-1" aria-label="Increase" {disabled} onclick={(e) => bump(1, e)}>
        <span class="icon">add</span>
      </button>
    </span>
  {/if}
</div>

<style>
  .nf {
    --h: var(--control-h);
    display: inline-flex;
    align-items: center;
    height: var(--h);
    min-width: 0;
    border-radius: var(--r-md);
    background: var(--grad-2);
    transition: background var(--dur-fast) var(--ease);
  }
  .sm {
    --h: var(--control-h-sm);
    border-radius: var(--r-sm);
  }
  .nf:hover {
    background: var(--grad-3);
  }
  .nf:focus-within {
    background: var(--grad-3);
    box-shadow: inset 0 0 0 1px var(--focus-line);
  }
  .scrub {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    align-self: stretch;
    padding: 0 4px 0 10px;
    color: var(--text-muted);
    font-size: var(--fs-sm);
    cursor: ew-resize;
    user-select: none;
    touch-action: none;
    white-space: nowrap;
  }
  .scrub .icon {
    font-size: 18px;
  }
  .scrubbing .scrub,
  .scrub:hover {
    color: var(--accent-strong);
  }
  input {
    flex: 1;
    min-width: 0;
    width: 4ch;
    height: 100%;
    padding: 0 10px;
    border: 0;
    background: none;
    color: var(--text);
    font: inherit;
    font-size: var(--fs-md);
    font-variant-numeric: tabular-nums;
    outline: none;
  }
  .scrub + input {
    padding-left: 4px;
  }
  input:focus-visible {
    box-shadow: none;
  }
  .suffix {
    color: var(--text-faint);
    font-size: var(--fs-sm);
    padding-right: 6px;
  }
  .steps {
    display: flex;
    align-self: stretch;
    padding: 3px;
    gap: 2px;
  }
  .steps button {
    display: grid;
    place-items: center;
    width: calc(var(--h) - 10px);
    border: 0;
    border-radius: calc(var(--r-md) - 4px);
    background: none;
    color: var(--text-muted);
    cursor: pointer;
    transition:
      background var(--dur-fast) var(--ease),
      transform var(--dur-fast) var(--ease);
  }
  .steps .icon {
    font-size: 18px;
  }
  .steps button:hover:not(:disabled) {
    background: var(--hover);
    color: var(--text);
  }
  .steps button:active:not(:disabled) {
    transform: scale(0.9);
    background: var(--pressed);
  }
  .disabled {
    opacity: 0.45;
  }
  @media (pointer: coarse) {
    .nf {
      --h: var(--touch);
    }
    .steps button {
      width: 38px;
    }
  }
</style>
