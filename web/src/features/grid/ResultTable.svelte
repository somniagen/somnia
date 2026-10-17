<script lang="ts">
  import { live } from '$lib/live.svelte'
  import type { GalleryItem, Grid, GridCell } from '$lib/types'
  import { Spinner, tooltip } from '$lib/ui'

  let { g, z, onopen }: { g: Grid; z: number; onopen: (items: GalleryItem[], index: number) => void } = $props()

  const ax = $derived(g.axes[0])
  const ay = $derived(g.axes[1] ?? null)
  const nx = $derived(ax.values.length)
  const ny = $derived(ay?.values.length ?? 1)
  const cells = $derived(g.cells.filter((c) => c.z === z).sort((a, b) => a.y - b.y || a.x - b.x))
  const done = $derived(cells.filter((c) => c.item).map((c) => c.item!))
  const aspect = $derived(`${g.base.width} / ${g.base.height}`)

  const running = (c: GridCell) => c.status === 'queued' && !!c.jobId && (live.running?.id === c.jobId || live.current?.jobId === c.jobId)
  const preview = (c: GridCell) => (live.current?.jobId === c.jobId ? live.preview : null)

  function open(c: GridCell) {
    const i = done.findIndex((it) => it.id === c.item?.id)
    if (i >= 0) onopen(done, i)
  }
</script>

<div class="wrap">
  <div class="tbl" class:noy={!ay} style="--nx: {nx}; --ar: {aspect}">
    {#if ay}
      <div class="corner" use:tooltip={`${ay.label} / ${ax.label}`}>
        <span>{ay.label}</span>
        <span class="icon">south_east</span>
        <span>{ax.label}</span>
      </div>
    {/if}
    {#each ax.values as v, i (i)}
      <div class="xh" use:tooltip={`${ax.label}: ${v.label}`}>{v.label}</div>
    {/each}
    {#each Array(ny) as _, y (y)}
      {#if ay}
        <div class="yh"><span>{ay.values[y].label}</span></div>
      {/if}
      {#each cells.filter((c) => c.y === y) as c (c.jobId ?? `${c.x}-${c.y}`)}
        {@const run = running(c)}
        {@const pv = run ? preview(c) : null}
        {#if c.item}
          <button class="cell img" onclick={() => open(c)} aria-label="Open {ax.label} {ax.values[c.x].label}{ay ? `, ${ay.label} ${ay.values[c.y].label}` : ''}">
            <img src={c.item.thumbUrl} alt="" loading="lazy" draggable="false" />
          </button>
        {:else if run}
          <div class="cell run">
            {#if pv}<img src={pv} alt="" draggable="false" />{:else}<Spinner size={18} />{/if}
            {#if live.current?.jobId === c.jobId}
              <div class="bar" style="width: {Math.round((live.current?.overall ?? 0) * 100)}%"></div>
            {/if}
          </div>
        {:else if c.status === 'error'}
          <div class="cell bad" use:tooltip={c.error ?? 'Failed'}><span class="icon">error</span></div>
        {:else if c.status === 'cancelled'}
          <div class="cell off" use:tooltip={'Cancelled'}><span class="icon">block</span></div>
        {:else}
          <div class="cell wait"></div>
        {/if}
      {/each}
    {/each}
  </div>
</div>

<style>
  .wrap {
    overflow: auto;
    height: 100%;
    overscroll-behavior: contain;
  }
  .tbl {
    --cw: 150px;
    --lw: 120px;
    display: grid;
    grid-template-columns: var(--lw) repeat(var(--nx), minmax(0, 1fr));
    gap: 4px;
    width: 100%;
    min-width: calc(var(--lw) + var(--nx) * (var(--cw) + 4px) + 2 * var(--sp-3));
    max-width: calc(var(--lw) + var(--nx) * 340px);
    padding: 0 var(--sp-3) var(--sp-3);
  }
  .tbl.noy {
    grid-template-columns: repeat(var(--nx), minmax(0, 1fr));
    --lw: 0px;
  }
  .corner,
  .xh {
    position: sticky;
    top: 0;
    z-index: 2;
    display: flex;
    align-items: flex-end;
    justify-content: center;
    min-height: 36px;
    padding: var(--sp-2) var(--sp-1);
    background: var(--bg);
    font-size: var(--fs-sm);
    font-variant-numeric: tabular-nums;
    text-align: center;
    overflow-wrap: anywhere;
  }
  .xh {
    max-height: 72px;
    overflow: hidden;
  }
  .corner {
    left: 0;
    z-index: 3;
    gap: 2px;
    align-items: center;
    color: var(--text-faint);
    font-size: var(--fs-xs);
  }
  .corner .icon {
    font-size: 14px;
  }
  .yh {
    position: sticky;
    left: 0;
    z-index: 1;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    padding: 0 var(--sp-2) 0 0;
    background: var(--bg);
    font-size: var(--fs-sm);
    font-variant-numeric: tabular-nums;
    text-align: right;
    overflow-wrap: anywhere;
  }
  .yh span {
    display: -webkit-box;
    -webkit-line-clamp: 6;
    line-clamp: 6;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .cell {
    position: relative;
    display: grid;
    place-items: center;
    aspect-ratio: var(--ar);
    padding: 0;
    border: 1px solid var(--hairline);
    border-radius: var(--r-md);
    background: var(--grad-1);
    overflow: hidden;
    color: var(--text-faint);
  }
  .cell img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .cell.img {
    cursor: zoom-in;
    transition: transform var(--dur-fast) var(--ease);
    animation: in var(--dur) var(--ease);
  }
  .cell.img:hover {
    border-color: var(--focus-line);
  }
  .cell.img:active {
    transform: scale(0.97);
  }
  @keyframes in {
    from {
      opacity: 0;
    }
  }
  .cell.run {
    border-color: var(--focus-line);
    box-shadow: 0 0 14px -4px var(--accent-glow);
    background: var(--stripes), var(--grad-2);
  }
  .bar {
    position: absolute;
    left: 0;
    bottom: 0;
    height: 2px;
    background: var(--grad-progress);
    box-shadow: 0 0 8px var(--accent-glow);
    transition: width var(--dur) var(--ease);
  }
  .cell.wait {
    background: var(--stripes), var(--grad-1);
  }
  .cell.bad {
    color: var(--danger);
    background: var(--danger-soft);
  }
  @media (max-width: 640px) {
    .tbl {
      --cw: 104px;
      --lw: 76px;
      padding: 0 var(--sp-2) var(--sp-2);
    }
    .corner span:not(.icon) {
      display: none;
    }
  }
</style>
