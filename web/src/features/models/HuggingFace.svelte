<script lang="ts">
  import { EmptyState, Segmented, Select, Skeleton, Surface } from '$lib/ui'
  import { api } from '$lib/api'
  import type { HfCategory, HfRepo, HfSearchQuery } from '$lib/types'
  import HfDetail from './HfDetail.svelte'
  import { HF_CATEGORIES, hfKindLabel } from './hf'
  import { fmtCount } from './util'

  let q = $state('')
  let category = $state<HfCategory>('')
  let sort = $state<NonNullable<HfSearchQuery['sort']>>('downloads')

  let items = $state<HfRepo[]>([])
  let cursor = $state<string | null>(null)
  let loading = $state(false)
  let done = $state(false)
  let error = $state('')
  let detail = $state<HfRepo | null>(null)
  let detailOpen = $state(false)
  let sentinel = $state<HTMLDivElement>()
  let ctl: AbortController | null = null
  let gen = 0

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
      const res = await api.hfSearch({ query: q.trim() || undefined, category, sort, cursor: cursor ?? undefined, limit: 24 }, ctl.signal)
      if (my !== gen) return
      const have = new Set(reset ? [] : items.map((i) => i.id))
      items = reset ? res.items : [...items, ...res.items.filter((i) => !have.has(i.id))]
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
    void [q, category, sort]
    clearTimeout(timer)
    const wait = first ? 0 : 400
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

  const ago = (iso: string | null) => {
    if (!iso) return ''
    const d = (Date.now() - Date.parse(iso)) / 864e5
    if (d < 1) return 'today'
    if (d < 30) return `${Math.floor(d)}d`
    if (d < 365) return `${Math.floor(d / 30)}mo`
    return `${Math.floor(d / 365)}y`
  }
</script>

<div class="hf">
  <div class="bar">
    <div class="search">
      <span class="icon">search</span>
      <input type="search" placeholder="Search Hugging Face" aria-label="Search Hugging Face" bind:value={q} />
    </div>
    <Select
      size="sm"
      icon="sort"
      items={[
        { value: 'downloads', label: 'Downloads' },
        { value: 'likes', label: 'Likes' },
        { value: 'trendingScore', label: 'Trending' },
        { value: 'lastModified', label: 'Updated' },
      ]}
      bind:value={sort}
    />
  </div>
  <div class="bar">
    <div class="seg"><Segmented items={HF_CATEGORIES} bind:value={category} size="sm" /></div>
  </div>

  {#if error && !items.length}
    <EmptyState icon="cloud_off" title="Hugging Face unreachable" description={error} />
  {:else if !items.length && !loading}
    <EmptyState icon="search_off" title="No matching files" />
  {:else}
    <div class="list">
      {#each items as r (r.id)}
        <Surface
          level={1}
          padding="var(--sp-2) var(--sp-3)"
          interactive
          class="hrow"
          onclick={() => {
            detail = r
            detailOpen = true
          }}
        >
          <span class="icon av">{r.gated ? 'lock' : 'deployed_code'}</span>
          <div class="main">
            <div class="nm" title={r.id}><span class="au">{r.author}/</span>{r.id.slice(r.author.length + 1)}</div>
            <div class="kinds">
              {#each r.kinds as k}<span class="kind" class:hit={category && hfKindLabel(category) === hfKindLabel(k)}>{hfKindLabel(k)}</span>{/each}
            </div>
          </div>
          <div class="stats">
            <span class="st"><span class="icon">download</span>{fmtCount(r.downloads)}</span>
            <span class="st"><span class="icon">favorite</span>{fmtCount(r.likes)}</span>
            <span class="st dim">{ago(r.lastModified)}</span>
          </div>
        </Surface>
      {/each}
      {#if loading}
        {#each Array(6) as _}<Skeleton height="58px" radius="var(--r-md)" />{/each}
      {/if}
    </div>
    <div bind:this={sentinel} class="sentinel"></div>
  {/if}
</div>

<HfDetail repo={detail} {category} bind:open={detailOpen} />

<style>
  .hf {
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
    min-width: 200px;
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
  .search input::-webkit-search-cancel-button {
    display: none;
  }
  .list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 380px), 1fr));
    gap: var(--sp-2);
  }
  :global(.hrow) {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    min-height: 58px;
    cursor: pointer;
  }
  .av {
    display: grid;
    place-items: center;
    flex: none;
    width: 36px;
    height: 36px;
    border-radius: var(--r-md);
    background: var(--grad-3);
    box-shadow: var(--sheen);
    color: var(--text-muted);
    font-size: 20px;
  }
  .main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .nm {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .au {
    color: var(--text-muted);
  }
  .kinds {
    display: flex;
    gap: 4px;
    overflow: hidden;
  }
  .kind {
    flex: none;
    padding: 0 6px;
    border-radius: var(--r-sm);
    background: var(--surface-3);
    color: var(--text-muted);
    font-size: var(--fs-xs);
    line-height: 18px;
  }
  .kind.hit {
    color: var(--text);
  }
  .stats {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;
    flex: none;
    color: var(--text-muted);
    font-size: var(--fs-xs);
  }
  .st {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    font-variant-numeric: tabular-nums;
  }
  .st .icon {
    font-size: 14px;
  }
  .dim {
    color: var(--text-faint);
  }
  .sentinel {
    height: 1px;
  }
</style>
