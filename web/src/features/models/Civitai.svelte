<script lang="ts">
  import { EmptyState, Select, Skeleton, Surface, Segmented } from '$lib/ui'
  import { api } from '$lib/api'
  import { live } from '$lib/live.svelte'
  import type { CivitaiModel, CivitaiSearchQuery } from '$lib/types'
  import CivitaiDetail from './CivitaiDetail.svelte'
  import { models } from './store.svelte'
  import { fmtCount, thumbUrl } from './util'

  let q = $state('')
  let types = $state('LORA')
  let base = $state('')
  let sort = $state<NonNullable<CivitaiSearchQuery['sort']>>('Most Downloaded')
  let period = $state<NonNullable<CivitaiSearchQuery['period']>>('Month')

  let items = $state<CivitaiModel[]>([])
  let cursor = $state<string | null>(null)
  let loading = $state(false)
  let done = $state(false)
  let error = $state('')
  let detail = $state<CivitaiModel | null>(null)
  let detailOpen = $state(false)
  let sentinel = $state<HTMLDivElement>()
  let ctl: AbortController | null = null
  let gen = 0

  const nsfw = $derived(live.settings?.showNsfw ?? false)
  const installedIds = $derived(new Set(models.list.map((m) => m.civitai?.versionId).filter(Boolean)))

  async function load(reset: boolean) {
    if (reset) {
      ctl?.abort()
      items = []
      cursor = null
      done = false
      error = ''
    } else if (loading || done) return
    const my = ++gen
    ctl = new AbortController()
    loading = true
    try {
      const res = await api.civitaiSearch(
        { query: q.trim() || undefined, types, sort, period, baseModels: base || undefined, nsfw, cursor: cursor ?? undefined, limit: 24 },
        ctl.signal,
      )
      if (my !== gen) return
      items = reset ? res.items : [...items, ...res.items]
      cursor = res.nextCursor
      if (!res.nextCursor) done = true
    } catch (e) {
      if (my !== gen || (e instanceof DOMException && e.name === 'AbortError')) return
      error = e instanceof Error ? e.message : 'Failed'
      done = true
    } finally {
      if (my === gen) loading = false
    }
  }

  let timer: ReturnType<typeof setTimeout> | undefined
  let first = true
  $effect(() => {
    void [q, types, base, sort, period, nsfw]
    clearTimeout(timer)
    const wait = first ? 0 : 350
    first = false
    timer = setTimeout(() => load(true), wait)
    return () => clearTimeout(timer)
  })

  $effect(() => {
    if (!sentinel) return
    const io = new IntersectionObserver((e) => e[0].isIntersecting && load(false), { rootMargin: '600px' })
    io.observe(sentinel)
    return () => io.disconnect()
  })

  const preview = (m: CivitaiModel) => {
    const v = m.versions[0]
    const img = v?.images.find((i) => i.type === 'image' && (nsfw || i.nsfwLevel <= 1)) ?? v?.images.find((i) => i.type === 'image')
    return img ? thumbUrl(img.url) : null
  }
  const isInstalled = (m: CivitaiModel) => m.versions.some((v) => v.installed || installedIds.has(v.id))

  const TYPES = [
    { value: 'LORA', label: 'LoRA' },
    { value: 'Checkpoint', label: 'Checkpoint' },
    { value: 'VAE', label: 'VAE' },
    { value: 'Upscaler', label: 'Upscaler' },
    { value: 'TextualInversion', label: 'Embedding' },
  ]
  const BASES = [
    { value: '', label: 'Any base' },
    { value: 'Illustrious', label: 'Illustrious' },
    { value: 'Anima', label: 'Anima' },
    { value: 'NoobAI', label: 'NoobAI' },
    { value: 'Pony', label: 'Pony' },
    { value: 'SDXL 1.0', label: 'SDXL' },
  ]
</script>

<div class="cv">
  <div class="bar">
    <div class="search">
      <span class="icon">search</span>
      <input type="text" placeholder="Search Civitai" aria-label="Search Civitai" bind:value={q} />
    </div>
  </div>
  <div class="bar">
    <div class="seg"><Segmented items={TYPES} bind:value={types} size="sm" /></div>
  </div>
  <div class="bar">
    <Select size="sm" items={BASES} bind:value={base} />
    <Select
      size="sm"
      icon="sort"
      items={[
        { value: 'Most Downloaded', label: 'Downloads' },
        { value: 'Highest Rated', label: 'Rating' },
        { value: 'Newest', label: 'Newest' },
      ]}
      bind:value={sort}
    />
    <Select
      size="sm"
      icon="schedule"
      items={[
        { value: 'Day', label: 'Day' },
        { value: 'Week', label: 'Week' },
        { value: 'Month', label: 'Month' },
        { value: 'Year', label: 'Year' },
        { value: 'AllTime', label: 'All time' },
      ]}
      bind:value={period}
    />
  </div>

  {#if error && !items.length}
    <EmptyState icon="cloud_off" title="Civitai unreachable" description={error} />
  {:else if !items.length && !loading}
    <EmptyState icon="search_off" title="No results" />
  {:else}
    <div class="grid">
      {#each items as m (m.id)}
        {@const img = preview(m)}
        <Surface
          level={1}
          padding="0"
          interactive
          class="ccard"
          onclick={() => {
            detail = m
            detailOpen = true
          }}
        >
          <div class="pv">
            {#if img}<img src={img} alt="" loading="lazy" />{:else}<span class="icon big">image</span>{/if}
            {#if isInstalled(m)}<span class="inst"><span class="icon">check</span></span>{/if}
          </div>
          <div class="info">
            <div class="nm" title={m.name}>{m.name}</div>
            <div class="sub">
              <span class="by">{m.creator?.username ?? ''}</span>
              <span class="st"><span class="icon">download</span>{fmtCount(m.stats.downloadCount)}</span>
              <span class="st"><span class="icon">thumb_up</span>{fmtCount(m.stats.thumbsUpCount)}</span>
            </div>
          </div>
        </Surface>
      {/each}
      {#if loading}
        {#each Array(6) as _}<Skeleton height="280px" radius="var(--r-lg)" />{/each}
      {/if}
    </div>
    <div bind:this={sentinel} class="sentinel"></div>
  {/if}
</div>

<CivitaiDetail model={detail} bind:open={detailOpen} />

<style>
  .cv {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
  }
  .bar {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    flex-wrap: wrap;
  }
  .seg {
    min-width: 0;
    max-width: 100%;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .search {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    flex: 1;
    height: var(--control-h);
    padding: 0 var(--sp-3);
    border-radius: var(--r-md);
    background: var(--surface-2);
    color: var(--text-muted);
  }
  .search input {
    flex: 1;
    min-width: 0;
    border: 0;
    outline: 0;
    background: none;
    color: var(--text);
    font: inherit;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 140px), 1fr));
    gap: var(--sp-3);
  }
  :global(.ccard) {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    cursor: pointer;
  }
  .pv {
    position: relative;
    display: grid;
    place-items: center;
    aspect-ratio: 3 / 4;
    background: var(--surface-3);
    color: var(--text-faint);
    overflow: hidden;
  }
  .pv img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .big {
    font-size: 40px;
  }
  .inst {
    position: absolute;
    top: 6px;
    right: 6px;
    display: grid;
    place-items: center;
    width: 24px;
    height: 24px;
    border-radius: var(--r-sm);
    background: var(--success);
    color: var(--text-on-accent);
  }
  .inst .icon {
    font-size: 18px;
  }
  .info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--sp-2) var(--sp-3) var(--sp-3);
  }
  .nm {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sub {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    color: var(--text-muted);
    font-size: var(--fs-xs);
  }
  .by {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .st {
    display: inline-flex;
    align-items: center;
    gap: 2px;
  }
  .st .icon {
    font-size: 14px;
  }
  .sentinel {
    height: 1px;
  }
</style>
