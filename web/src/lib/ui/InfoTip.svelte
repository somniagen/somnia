<script lang="ts">
  import type { Snippet } from 'svelte'
  import Popover from './Popover.svelte'
  import { uid, type Placement } from './util'

  interface Props {
    text?: string
    label?: string
    placement?: Placement
    icon?: string
    class?: string
    style?: string
    children?: Snippet
  }
  let { text, label = 'More info', placement = 'top', icon = 'info', class: klass, style, children }: Props = $props()

  const id = uid('info')
  let open = $state(false)
  let pinned = false
  let btn = $state<HTMLButtonElement>()
  let timer: ReturnType<typeof setTimeout> | undefined

  function enter(e: PointerEvent) {
    if (e.pointerType === 'touch') return
    clearTimeout(timer)
    timer = setTimeout(() => (open = true), 150)
  }
  function leave(e: PointerEvent) {
    if (e.pointerType === 'touch' || pinned) return
    clearTimeout(timer)
    timer = setTimeout(() => (open = false), 120)
  }
  function click() {
    pinned = !open || !pinned
    open = pinned
  }
</script>

<button
  bind:this={btn}
  type="button"
  class={['info', klass]}
  {style}
  aria-label={label}
  aria-expanded={open}
  aria-describedby={open ? id : undefined}
  onpointerenter={enter}
  onpointerleave={leave}
  onfocus={(e) => e.currentTarget.matches(':focus-visible') && (open = true)}
  onblur={() => {
    pinned = false
    open = false
  }}
  onclick={click}
>
  <span class="icon" aria-hidden="true">{icon}</span>
</button>

<Popover
  bind:open
  anchor={btn}
  {placement}
  offset={4}
  onclose={() => (pinned = false)}
  {id}
  role="tooltip"
>
  <div class="tip">
    {#if children}{@render children()}{:else}{text}{/if}
  </div>
</Popover>

<style>
  .info {
    position: relative;
    display: inline-grid;
    place-items: center;
    width: 18px;
    height: 18px;
    padding: 0;
    border: 0;
    border-radius: 50%;
    background: none;
    color: var(--text-faint);
    vertical-align: middle;
    cursor: help;
    transition: color var(--dur-fast) var(--ease);
  }
  .info .icon {
    font-size: 16px;
  }
  .info:hover,
  .info[aria-expanded='true'] {
    color: var(--accent-strong);
  }
  .info::after {
    content: '';
    position: absolute;
    inset: -6px;
  }
  .tip {
    max-width: 260px;
    padding: 4px 6px;
    font-size: var(--fs-sm);
    line-height: 1.45;
    color: var(--text);
  }
  @media (pointer: coarse) {
    .info::after {
      inset: -13px;
    }
  }
</style>
