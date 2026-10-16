<script lang="ts">
  import type { HTMLButtonAttributes } from 'svelte/elements'
  import { tooltip } from './tooltip'
  import type { Placement } from './util'

  interface Props extends HTMLButtonAttributes {
    icon: string
    label: string
    variant?: 'ghost' | 'default' | 'primary' | 'danger'
    size?: 'sm' | 'md'
    active?: boolean
    filled?: boolean
    tip?: Placement | false
    el?: HTMLButtonElement
  }
  let {
    icon,
    label,
    variant = 'ghost',
    size = 'md',
    active,
    filled = false,
    tip = 'top',
    el = $bindable(),
    type = 'button',
    class: klass,
    ...rest
  }: Props = $props()
</script>

<button
  bind:this={el}
  {type}
  class={['ib', variant, size, klass, { active }]}
  aria-label={label}
  aria-pressed={active}
  use:tooltip={tip ? { text: label, placement: tip, describe: false } : null}
  {...rest}
>
  <span class="icon" class:filled={filled || active} aria-hidden="true">{icon}</span>
</button>

<style>
  .ib {
    --h: var(--control-h);
    display: inline-grid;
    place-items: center;
    flex: none;
    width: var(--h);
    height: var(--h);
    padding: 0;
    border: 0;
    border-radius: var(--r-md);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    transition:
      background var(--dur-fast) var(--ease),
      color var(--dur-fast) var(--ease),
      transform var(--dur-fast) var(--ease);
  }
  .sm {
    --h: var(--control-h-sm);
    border-radius: var(--r-sm);
  }
  .sm .icon {
    font-size: 18px;
  }
  .ib:hover:not(:disabled) {
    background: var(--hover);
    color: var(--text);
  }
  .ib:active:not(:disabled) {
    transform: scale(0.92);
    background: var(--pressed);
  }
  .ib:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .default {
    background: var(--grad-3);
    box-shadow: var(--sheen);
    color: var(--text);
  }
  .default:hover:not(:disabled) {
    background: var(--grad-4);
  }
  .primary {
    background: var(--grad-accent);
    box-shadow: var(--sheen-strong), 0 2px 10px -2px var(--accent-glow);
    color: var(--text-on-accent);
  }
  .primary:hover:not(:disabled) {
    background: var(--grad-accent-hi);
    color: var(--text-on-accent);
  }
  .danger {
    color: var(--danger);
  }
  .danger:hover:not(:disabled) {
    background: var(--danger-soft);
    color: var(--danger);
  }
  .active,
  .active:hover:not(:disabled) {
    background: linear-gradient(180deg, rgb(255 255 255 / 0.14), rgb(255 255 255 / 0.06));
    box-shadow: var(--sheen);
    color: var(--accent-strong);
  }
  .filled {
    font-variation-settings: 'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24;
  }
  @media (pointer: coarse) {
    .ib {
      width: var(--touch);
      height: var(--touch);
    }
  }
</style>
