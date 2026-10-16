<script lang="ts">
  import type { Snippet } from 'svelte'
  import type { HTMLInputAttributes } from 'svelte/elements'

  interface Props extends Omit<HTMLInputAttributes, 'onchange' | 'type'> {
    checked?: boolean
    indeterminate?: boolean
    label?: string
    onchange?: (v: boolean) => void
    children?: Snippet
  }
  let {
    checked = $bindable(false),
    indeterminate = $bindable(false),
    label,
    disabled,
    onchange,
    class: klass,
    style,
    children,
    ...rest
  }: Props = $props()
</script>

<label class={['cb', klass, { disabled }]} {style}>
  <input
    type="checkbox"
    bind:checked
    bind:indeterminate
    {disabled}
    onchange={() => onchange?.(checked)}
    {...rest}
  />
  <span class="box" aria-hidden="true">
    <span class="icon">{indeterminate ? 'remove' : 'check'}</span>
  </span>
  {#if children}{@render children()}{:else if label}<span>{label}</span>{/if}
</label>

<style>
  .cb {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: var(--control-h-sm);
    cursor: pointer;
    user-select: none;
  }
  input {
    position: absolute;
    opacity: 0;
    width: 1px;
    height: 1px;
    margin: 0;
  }
  .box {
    display: grid;
    place-items: center;
    flex: none;
    width: 18px;
    height: 18px;
    border-radius: 5px;
    background: var(--grad-4);
    color: var(--text-on-accent);
    transition:
      background var(--dur-fast) var(--ease),
      transform var(--dur-fast) var(--ease);
  }
  .box .icon {
    font-size: 16px;
    font-variation-settings: 'FILL' 0, 'wght' 700, 'GRAD' 0, 'opsz' 20;
    opacity: 0;
    transform: scale(0.5);
    transition:
      opacity var(--dur-fast) var(--ease),
      transform var(--dur) var(--ease);
  }
  .cb:hover .box {
    background: color-mix(in srgb, var(--surface-4), var(--text) 10%);
  }
  .cb:active .box {
    transform: scale(0.9);
  }
  input:checked + .box,
  input:indeterminate + .box {
    background: var(--grad-accent);
  }
  input:checked + .box .icon,
  input:indeterminate + .box .icon {
    opacity: 1;
    transform: none;
  }
  input:focus-visible + .box {
    box-shadow: var(--focus-ring);
  }
  .disabled {
    opacity: 0.45;
    cursor: default;
  }
  @media (pointer: coarse) {
    .cb {
      min-height: var(--touch);
    }
  }
</style>
