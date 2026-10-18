<script lang="ts">
  import type { HTMLInputAttributes } from 'svelte/elements'
  import IconButton from './IconButton.svelte'
  import Kbd from './Kbd.svelte'

  interface Props extends Omit<HTMLInputAttributes, 'value' | 'size'> {
    value?: string
    size?: 'sm' | 'md'
    shortcut?: string
    input?: HTMLInputElement
    onclear?: () => void
  }
  let {
    value = $bindable(''),
    size = 'md',
    shortcut,
    input = $bindable(),
    onclear,
    placeholder = 'Search',
    class: klass,
    style,
    onkeydown,
    ...rest
  }: Props = $props()

  function clear() {
    value = ''
    onclear?.()
    input?.focus()
  }
  function key(e: KeyboardEvent & { currentTarget: EventTarget & HTMLInputElement }) {
    onkeydown?.(e)
    if (e.defaultPrevented || e.key !== 'Escape') return
    if (value) clear()
    else input?.blur()
  }
</script>

<label class={['sf', size, klass]} {style}>
  <span class="icon" aria-hidden="true">search</span>
  <input
    bind:this={input}
    bind:value
    type="search"
    {placeholder}
    aria-label={placeholder}
    spellcheck="false"
    autocomplete="off"
    onkeydown={key}
    {...rest}
  />
  {#if value}
    <IconButton icon="close" label="Clear" size="sm" tip={false} onclick={clear} />
  {:else if shortcut}
    <Kbd>{shortcut}</Kbd>
  {/if}
</label>

<style>
  .sf {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    min-width: 0;
    height: var(--control-h);
    padding: 0 4px 0 var(--sp-3);
    border-radius: var(--r-md);
    background: var(--grad-2);
    color: var(--text-muted);
    cursor: text;
    transition: background-color var(--dur-fast) var(--ease);
  }
  .sf.sm {
    height: var(--control-h-sm);
    border-radius: var(--r-sm);
  }
  .sf:hover {
    background: var(--grad-3);
  }
  .sf:focus-within {
    background: var(--grad-3);
    box-shadow: inset 0 0 0 1px var(--focus-line);
  }
  .icon {
    font-size: 18px;
  }
  input {
    flex: 1;
    min-width: 0;
    height: 100%;
    border: 0;
    outline: 0;
    background: none;
    color: var(--text);
    font: inherit;
    font-size: var(--fs-sm);
  }
  input::placeholder {
    color: var(--text-faint);
  }
  input::-webkit-search-cancel-button {
    display: none;
  }
  .sf :global(kbd) {
    margin-right: 4px;
  }
  @media (pointer: coarse) {
    .sf:not(.sm) {
      height: var(--touch);
    }
  }
</style>
