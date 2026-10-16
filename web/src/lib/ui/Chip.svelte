<script lang="ts">
  import type { Snippet } from 'svelte'

  interface Props {
    label?: string
    color?: string
    icon?: string
    locked?: boolean
    selected?: boolean
    removable?: boolean
    size?: 'sm' | 'md'
    title?: string
    class?: string
    style?: string
    onclick?: (e: MouseEvent) => void
    onremove?: () => void
    children?: Snippet
  }
  let {
    label,
    color,
    icon,
    locked = false,
    selected = false,
    removable = false,
    size = 'md',
    title,
    class: klass,
    style,
    onclick,
    onremove,
    children,
  }: Props = $props()

  const c = $derived(color ? (color.startsWith('--') ? `var(${color})` : color) : 'var(--text-muted)')
  function key(e: KeyboardEvent) {
    if (removable && (e.key === 'Backspace' || e.key === 'Delete')) {
      e.preventDefault()
      onremove?.()
    }
  }
</script>

<span
  class={['chip', size, klass, { locked, selected, clickable: !!onclick, tinted: !!color }]}
  style="--chip: {c}; {style ?? ''}"
  {title}
>
  {#if onclick}
    <button type="button" class="main" aria-pressed={selected || undefined} onclick={onclick} onkeydown={key}>
      {@render body()}
    </button>
  {:else}
    <span class="main">{@render body()}</span>
  {/if}
  {#if removable}
    <button type="button" class="rm" aria-label="Remove {label ?? ''}" onclick={() => onremove?.()}>
      <span class="icon">close</span>
    </button>
  {/if}
</span>

{#snippet body()}
  {#if locked}<span class="icon lead" role="img" aria-label="Locked">lock</span>{:else if icon}<span class="icon lead" aria-hidden="true">{icon}</span>{/if}
  <span class="txt">{#if children}{@render children()}{:else}{label}{/if}</span>
{/snippet}

<style>
  .chip {
    --h: 28px;
    display: inline-flex;
    align-items: center;
    max-width: 100%;
    height: var(--h);
    border-radius: var(--r-sm);
    background: var(--grad-3);
    color: var(--text);
    font-size: var(--fs-sm);
    vertical-align: middle;
    transition:
      background var(--dur-fast) var(--ease),
      color var(--dur-fast) var(--ease),
      opacity var(--dur-fast) var(--ease);
  }
  .sm {
    --h: 22px;
    font-size: var(--fs-xs);
  }
  .tinted {
    background: color-mix(in srgb, var(--chip) 14%, transparent);
    color: var(--chip);
  }
  .main {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
    height: 100%;
    padding: 0 9px;
    border: 0;
    border-radius: inherit;
    background: none;
    color: inherit;
    font: inherit;
  }
  .sm .main {
    padding: 0 7px;
  }
  button.main {
    cursor: pointer;
  }
  button.main:active {
    transform: scale(0.97);
  }
  .clickable:hover {
    background: var(--grad-4);
  }
  .tinted.clickable:hover {
    background: color-mix(in srgb, var(--chip) 22%, transparent);
  }
  .txt {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .lead {
    font-size: 15px;
    margin-left: -2px;
  }
  .rm {
    display: grid;
    place-items: center;
    width: 22px;
    height: 22px;
    margin: 0 3px 0 -5px;
    padding: 0;
    border: 0;
    border-radius: 4px;
    background: none;
    color: inherit;
    opacity: 0.6;
    cursor: pointer;
  }
  .rm .icon {
    font-size: 15px;
  }
  .rm:hover {
    opacity: 1;
    background: var(--hover);
  }
  .selected {
    box-shadow: inset 0 0 0 1px var(--accent);
  }
  .locked {
    background: var(--grad-2);
    color: var(--boilerplate);
  }
  .locked.tinted {
    background: var(--grad-2);
    color: var(--boilerplate);
  }
  @media (pointer: coarse) {
    .chip {
      --h: 34px;
    }
    .rm {
      width: 30px;
      height: 30px;
    }
  }
</style>
