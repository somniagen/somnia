<script lang="ts">
  import type { Snippet } from 'svelte'

  interface Props {
    src?: string | null
    alt?: string
    aspect?: number | string
    fit?: 'cover' | 'contain'
    selected?: boolean
    selectable?: boolean
    // checkerboard behind transparent images
    checker?: boolean
    radius?: string
    class?: string
    style?: string
    onclick?: (e: MouseEvent) => void
    onselect?: (v: boolean) => void
    actions?: Snippet
    badge?: Snippet
    children?: Snippet
  }
  let {
    src,
    alt = '',
    aspect = 1,
    fit = 'cover',
    selected = $bindable(false),
    selectable = false,
    checker = false,
    radius = 'var(--r-md)',
    class: klass,
    style,
    onclick,
    onselect,
    actions,
    badge,
    children,
  }: Props = $props()

  let loaded = $state(false)
  let failed = $state(false)
  const ar = $derived(typeof aspect === 'number' ? String(aspect) : aspect.replace(/[x:]/, ' / '))

  $effect(() => {
    void src
    loaded = false
    failed = false
  })

  function toggle(e: Event) {
    e.stopPropagation()
    selected = !selected
    onselect?.(selected)
  }
  function key(e: KeyboardEvent) {
    if (!onclick) return
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onclick(e as unknown as MouseEvent)
    }
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
  class={['tile', klass, { selected, loaded, checker, clickable: !!onclick }]}
  style="aspect-ratio: {ar}; --rad: {radius}; {style ?? ''}"
  role={onclick ? 'button' : undefined}
  tabindex={onclick ? 0 : undefined}
  aria-label={onclick ? alt || 'Image' : undefined}
  aria-pressed={onclick && selectable ? selected : undefined}
  {onclick}
  onkeydown={key}
>
  {#if src && !failed}
    <img
      {src}
      {alt}
      loading="lazy"
      decoding="async"
      draggable="false"
      style="object-fit: {fit}"
      onload={() => (loaded = true)}
      onerror={() => (failed = true)}
    />
  {/if}
  {#if !loaded}
    <div class="ph" class:failed aria-hidden="true">
      {#if failed || !src}<span class="icon">{failed ? 'broken_image' : 'image'}</span>{/if}
    </div>
  {/if}
  {@render children?.()}
  {#if badge}<div class="badge">{@render badge()}</div>{/if}
  {#if actions}
    <div class="actions">{@render actions()}</div>
  {/if}
  {#if selectable}
    <button type="button" class="check" aria-label={selected ? 'Deselect' : 'Select'} aria-pressed={selected} onclick={toggle}>
      <span class="icon">check</span>
    </button>
  {/if}
</div>

<style>
  .tile {
    position: relative;
    overflow: hidden;
    border-radius: var(--rad);
    background: var(--grad-2);
    isolation: isolate;
    transition:
      box-shadow var(--dur) var(--ease),
      transform var(--dur-fast) var(--ease);
  }
  .tile::after {
    content: '';
    position: absolute;
    inset: 0;
    z-index: 1;
    border: 1px solid var(--hairline);
    border-radius: inherit;
    pointer-events: none;
  }
  .clickable {
    cursor: pointer;
  }
  .checker.loaded {
    background: var(--checker);
  }
  .clickable:active {
    transform: scale(0.985);
  }
  img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    opacity: 0;
    transition:
      opacity 300ms var(--ease),
      transform 400ms var(--ease);
  }
  .loaded img {
    opacity: 1;
  }
  .clickable:hover img {
    transform: scale(1.02);
  }
  .ph {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    color: var(--text-faint);
    background-color: var(--surface-2);
    background-image: linear-gradient(90deg, transparent 25%, var(--shimmer) 50%, transparent 75%);
    background-size: 200% 100%;
    animation: shimmer 1.4s linear infinite;
  }
  .ph.failed {
    animation: none;
    background-image: none;
  }
  .ph .icon {
    font-size: 28px;
  }
  .actions {
    position: absolute;
    inset: auto 0 0 0;
    display: flex;
    justify-content: flex-end;
    gap: 2px;
    padding: var(--sp-5) 6px 6px;
    background: linear-gradient(transparent, var(--scrim));
    opacity: 0;
    transform: translateY(4px);
    transition:
      opacity var(--dur) var(--ease),
      transform var(--dur) var(--ease);
  }
  .tile:hover .actions,
  .tile:focus-within .actions {
    opacity: 1;
    transform: none;
  }
  .actions :global(.ib) {
    color: var(--text);
  }
  .badge {
    position: absolute;
    top: 6px;
    right: 6px;
    display: flex;
    gap: 4px;
  }
  .check {
    position: absolute;
    top: 6px;
    left: 6px;
    display: grid;
    place-items: center;
    width: 24px;
    height: 24px;
    padding: 0;
    border: 0;
    border-radius: 50%;
    background: var(--scrim);
    box-shadow: inset 0 0 0 1.5px var(--text-muted);
    color: transparent;
    cursor: pointer;
    opacity: 0;
    transition:
      opacity var(--dur-fast) var(--ease),
      background var(--dur-fast) var(--ease),
      transform var(--dur-fast) var(--ease);
  }
  .check .icon {
    font-size: 16px;
    font-variation-settings: 'FILL' 0, 'wght' 700, 'GRAD' 0, 'opsz' 20;
  }
  .tile:hover .check,
  .tile:focus-within .check,
  .selected .check {
    opacity: 1;
  }
  .check:active {
    transform: scale(0.9);
  }
  .selected .check {
    background: var(--grad-accent);
    box-shadow: none;
    color: var(--text-on-accent);
  }
  .selected {
    box-shadow:
      0 0 0 2px var(--bg),
      0 0 0 4px var(--accent);
  }
  @keyframes shimmer {
    from {
      background-position: 150% 0;
    }
    to {
      background-position: -50% 0;
    }
  }
  @media (pointer: coarse) {
    .actions,
    .check {
      opacity: 1;
      transform: none;
    }
    .check {
      width: 32px;
      height: 32px;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .ph {
      animation: none;
    }
  }
</style>
