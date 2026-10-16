<script lang="ts">
  import { live } from '$lib/live.svelte'
  import type { GalleryItem } from '$lib/types'
  import { ImageTile } from '$lib/ui'

  let {
    selectedId = null,
    onselect,
    grid = false,
  }: { selectedId?: string | null; onselect: (i: GalleryItem) => void; grid?: boolean } = $props()
</script>

{#if live.recent.length}
  <div class={['strip', { grid }]}>
    {#each live.recent as it (it.id)}
      <button type="button" class={['it', { sel: it.id === selectedId }]} onclick={() => onselect(it)} aria-label="Show image">
        <ImageTile src={it.thumbUrl} aspect={it.width / it.height} fit="cover" />
      </button>
    {/each}
  </div>
{/if}

<style>
  .strip {
    display: flex;
    gap: var(--sp-2);
    overflow-x: auto;
    padding: 2px;
    scroll-snap-type: x proximity;
  }
  .strip.grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
    overflow: visible;
  }
  .it {
    flex: none;
    height: 72px;
    padding: 0;
    border: 0;
    background: none;
    border-radius: var(--r-md);
    cursor: pointer;
    scroll-snap-align: start;
    outline: 2px solid transparent;
    outline-offset: 1px;
    transition:
      outline-color var(--dur-fast) var(--ease),
      transform var(--dur-fast) var(--ease);
  }
  .grid .it {
    height: auto;
  }
  .it:active {
    transform: scale(0.96);
  }
  .it.sel {
    outline-color: var(--accent);
  }
  .it :global(.tile) {
    height: 100%;
    width: auto;
  }
  .grid .it :global(.tile) {
    width: 100%;
    height: auto;
  }
</style>
