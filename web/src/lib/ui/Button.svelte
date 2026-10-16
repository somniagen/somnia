<script lang="ts">
  import type { Snippet } from 'svelte'
  import type { HTMLButtonAttributes } from 'svelte/elements'
  import Spinner from './Spinner.svelte'

  interface Props extends HTMLButtonAttributes {
    variant?: 'primary' | 'default' | 'ghost' | 'danger'
    size?: 'sm' | 'md'
    icon?: string
    iconRight?: string
    loading?: boolean
    full?: boolean
    el?: HTMLButtonElement
    children?: Snippet
  }
  let {
    variant = 'default',
    size = 'md',
    icon,
    iconRight,
    loading = false,
    full = false,
    el = $bindable(),
    type = 'button',
    disabled,
    class: klass,
    children,
    ...rest
  }: Props = $props()
</script>

<button
  bind:this={el}
  {type}
  class={['btn', variant, size, klass, { full, loading, only: !children }]}
  disabled={disabled || loading}
  aria-busy={loading || undefined}
  {...rest}
>
  {#if loading}
    <Spinner size={size === 'sm' ? 14 : 16} label="" aria-hidden="true" />
  {:else if icon}
    <span class="icon" aria-hidden="true">{icon}</span>
  {/if}
  {#if children}<span class="label">{@render children()}</span>{/if}
  {#if iconRight}<span class="icon" aria-hidden="true">{iconRight}</span>{/if}
</button>

<style>
  .btn {
    --h: var(--control-h);
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--sp-2);
    height: var(--h);
    min-width: var(--h);
    padding: 0 14px;
    border: 0;
    border-radius: var(--r-md);
    font: inherit;
    font-size: var(--fs-md);
    font-weight: 500;
    color: var(--text);
    background: var(--grad-3);
    box-shadow: var(--sheen), var(--shadow-1);
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
    transition:
      background var(--dur-fast) var(--ease),
      color var(--dur-fast) var(--ease),
      box-shadow var(--dur) var(--ease),
      transform var(--dur-fast) var(--ease),
      opacity var(--dur-fast) var(--ease);
  }
  .btn .icon {
    font-size: 20px;
    margin-left: -3px;
  }
  .btn .label + .icon {
    margin: 0 -3px 0 0;
  }
  .btn.only {
    padding: 0;
  }
  .btn.only .icon {
    margin: 0;
  }
  .sm {
    --h: var(--control-h-sm);
    padding: 0 10px;
    font-size: var(--fs-sm);
    gap: 6px;
  }
  .sm .icon {
    font-size: 18px;
  }
  .full {
    width: 100%;
  }
  .btn:hover:not(:disabled) {
    background: var(--grad-4);
  }
  .btn:active:not(:disabled) {
    transform: scale(0.97);
  }
  .btn:disabled {
    cursor: default;
    opacity: 0.45;
  }
  .btn.loading {
    opacity: 0.8;
  }

  .primary {
    background: var(--grad-accent);
    color: var(--text-on-accent);
    box-shadow: var(--sheen-strong), 0 0 0 1px rgb(255 255 255 / 0.1), 0 2px 10px -2px var(--accent-glow);
  }
  .primary:hover:not(:disabled) {
    box-shadow: var(--sheen-strong), 0 0 0 1px rgb(255 255 255 / 0.2), 0 2px 16px -2px var(--accent-glow);
  }
  .primary:hover:not(:disabled) {
    background: var(--grad-accent-hi);
  }

  .ghost {
    background: transparent;
    box-shadow: none;
    color: var(--text-muted);
  }
  .ghost:hover:not(:disabled) {
    background: var(--hover);
    color: var(--text);
  }
  .ghost:active:not(:disabled) {
    background: var(--pressed);
  }

  .danger {
    background: var(--grad-danger);
    box-shadow: var(--sheen), var(--shadow-1);
    color: var(--text-on-danger);
  }
  .danger:hover:not(:disabled) {
    background: color-mix(in srgb, var(--danger), var(--text) 10%);
  }

  @media (pointer: coarse) {
    .btn {
      min-height: var(--touch);
    }
    .btn.only {
      min-width: var(--touch);
    }
  }
</style>
