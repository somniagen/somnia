<script lang="ts">
  import { fade } from 'svelte/transition'
  import { live } from '$lib/live.svelte'
  import type { GalleryItem } from '$lib/types'
  import { EmptyState, Spinner, reducedMotion } from '$lib/ui'
  import { eta, statusText } from '$features/shell/status'
  import ImageActions from './ImageActions.svelte'

  let {
    item,
    live: showLive,
    onopen,
    onbacktolive,
  }: { item: GalleryItem | null; live: boolean; onopen?: () => void; onbacktolive?: () => void } = $props()

  const cur = $derived(live.current)
  const job = $derived(live.running)
  const running = $derived(!!cur || !!job)
  const showingLive = $derived(running && showLive)
  const src = $derived(showingLive ? live.preview : (item?.url ?? null))
  const dur = $derived(reducedMotion.current ? 0 : 260)
</script>

<div class="stage">
  <div class="frame">
    {#each src ? [src] : [] as s (s)}
      <button type="button" class="imgbtn" onclick={onopen} disabled={showingLive} transition:fade={{ duration: dur }}>
        <img src={s} alt="" draggable="false" />
      </button>
    {/each}

    {#if showingLive && !src}
      <div class="wait">
        <Spinner size={22} label="" />
        <span>{statusText(cur)}</span>
      </div>
    {:else if !src}
      <EmptyState icon="image" title="Nothing yet" description="Results appear here." />
    {/if}

    {#if showingLive && cur}
      <div class="hud">
        <span class="phase">{statusText(cur)}</span>
        {#if cur.phase !== 'load'}<span class="mono">{Math.round(cur.overall * 100)}%</span>{/if}
        {#if eta(cur.etaSec)}<span class="mono dim">{eta(cur.etaSec)}</span>{/if}
      </div>
    {:else if running && !showLive}
      <button type="button" class="back" onclick={onbacktolive}>
        <span class="icon">sensors</span>
        Live
      </button>
    {/if}

    {#if !showingLive && item}
      <div class="bar">
        <div class="meta mono">{item.width}x{item.height} / {item.seed}</div>
        <ImageActions {item} editorLabel="Open" />
      </div>
    {/if}
  </div>
</div>

<style>
  .stage {
    position: relative;
    width: 100%;
    height: 100%;
    min-height: 0;
    display: grid;
    place-items: center;
    padding: var(--sp-4);
  }
  .frame {
    position: relative;
    width: 100%;
    height: 100%;
    min-width: 0;
    min-height: 0;
    border-radius: var(--r-lg);
    overflow: hidden;
    background: var(--surface-1);
    border: 1px solid var(--hairline);
    display: grid;
    place-items: center;
  }
  .imgbtn {
    position: absolute;
    inset: 0;
    padding: 0;
    border: 0;
    background: none;
    cursor: zoom-in;
    display: block;
  }
  .imgbtn:disabled {
    cursor: default;
  }
  img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: block;
    user-select: none;
  }
  .wait {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--sp-3);
    color: var(--text-muted);
    font-size: var(--fs-sm);
  }
  .hud {
    position: absolute;
    left: var(--sp-3);
    bottom: var(--sp-3);
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    padding: 4px var(--sp-3);
    border-radius: var(--r-md);
    background: var(--scrim);
    border: 1px solid var(--hairline);
    font-size: var(--fs-xs);
    backdrop-filter: blur(6px);
  }
  .mono {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
  }
  .dim {
    color: var(--text-muted);
  }
  .phase {
    font-weight: 500;
  }
  .back {
    position: absolute;
    left: var(--sp-3);
    top: var(--sp-3);
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px var(--sp-3);
    border-radius: var(--r-md);
    border: 1px solid var(--hairline);
    background: var(--scrim);
    color: var(--text);
    font: inherit;
    font-size: var(--fs-xs);
    cursor: pointer;
    backdrop-filter: blur(6px);
  }
  .back .icon {
    font-size: 16px;
  }
  .bar {
    position: absolute;
    left: 50%;
    bottom: var(--sp-3);
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    padding: 2px var(--sp-2);
    border-radius: var(--r-lg);
    background: var(--scrim);
    border: 1px solid var(--hairline);
    backdrop-filter: blur(8px);
    max-width: calc(100% - 16px);
    opacity: 0.95;
  }
  .meta {
    font-size: var(--fs-xs);
    color: var(--text-muted);
    padding: 0 var(--sp-2);
    white-space: nowrap;
  }
  @media (max-width: 640px) {
    .stage {
      padding: var(--sp-2);
    }
    .meta {
      display: none;
    }
    .hud {
      display: none;
    }
    .bar,
    .back {
      opacity: clamp(0, calc(1 - var(--p, 0) * 3), 1);
    }
  }
</style>
