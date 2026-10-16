<script lang="ts">
  import type { Snippet } from 'svelte'
  import type { HTMLButtonAttributes } from 'svelte/elements'

  interface Props extends Omit<HTMLButtonAttributes, 'onchange'> {
    checked?: boolean
    label?: string
    size?: 'sm' | 'md'
    onchange?: (v: boolean) => void
    children?: Snippet
  }
  let {
    checked = $bindable(false),
    label,
    size = 'md',
    disabled,
    onchange,
    class: klass,
    children,
    ...rest
  }: Props = $props()

  function flip() {
    checked = !checked
    onchange?.(checked)
  }
</script>

<button
  type="button"
  role="switch"
  aria-checked={checked}
  class={['toggle', size, klass, { on: checked }]}
  {disabled}
  onclick={flip}
  {...rest}
>
  <span class="track"><span class="knob"></span></span>
  {#if children}{@render children()}{:else if label}<span class="text">{label}</span>{/if}
</button>

<style>
  .toggle {
    --w: 36px;
    --hh: 20px;
    display: inline-flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: var(--control-h-sm);
    padding: 0;
    border: 0;
    background: none;
    color: var(--text);
    font: inherit;
    cursor: pointer;
    text-align: left;
  }
  .sm {
    --w: 30px;
    --hh: 17px;
  }
  .track {
    position: relative;
    flex: none;
    width: var(--w);
    height: var(--hh);
    border-radius: calc(var(--hh) / 2);
    background: var(--grad-4);
    box-shadow: inset 0 1px 2px rgb(0 0 0 / 0.4);
    transition: background var(--dur) var(--ease);
  }
  .knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: calc(var(--hh) - 4px);
    height: calc(var(--hh) - 4px);
    border-radius: 50%;
    background: var(--text-muted);
    transition:
      transform var(--dur) var(--ease),
      background var(--dur) var(--ease),
      width var(--dur-fast) var(--ease);
  }
  .toggle:active:not(:disabled) .knob {
    width: calc(var(--hh) + 1px);
  }
  .on .track {
    background: var(--grad-accent);
    box-shadow: 0 0 10px -2px var(--accent-glow);
  }
  .on .knob {
    background: var(--text-on-accent);
    transform: translateX(calc(var(--w) - var(--hh)));
  }
  .on:active:not(:disabled) .knob {
    transform: translateX(calc(var(--w) - var(--hh) - 5px));
  }
  .toggle:focus-visible {
    box-shadow: none;
  }
  .toggle:focus-visible .track {
    box-shadow: var(--focus-ring);
  }
  .toggle:disabled {
    opacity: 0.45;
    cursor: default;
  }
  @media (pointer: coarse) {
    .toggle {
      min-height: var(--touch);
    }
  }
</style>
