<script lang="ts">
  import { untrack } from 'svelte'
  import { actions, openInpaint, removeImage } from '$features/generate/actions.svelte'
  import { api } from '$lib/api'
  import { live } from '$lib/live.svelte'
  import type { GalleryItem } from '$lib/types'
  import { Button, EmptyState, IconButton, ImageTile, Select, Skeleton, mobile, toast, tooltip } from '$lib/ui'
  import Logo from '$features/shell/Logo.svelte'
  import Lightbox from './Lightbox.svelte'

  let all = $state<GalleryItem[]>([])
  let cursor = $state<string | null>(null)
  let loading = $state(false)
  let done = $state(false)
  let failed = $state('')
  let first = $state(true)
  let selecting = $state(false)
  let selected = $state<Set<string>>(new Set())
  let open = $state<number | null>(null)
  let confirmDel = $state(false)
  let sentinel = $state<HTMLDivElement>()
  let width = $state(0)
  let stack = $state<{ root: string; items: GalleryItem[]; loading: boolean } | null>(null)
  let stale = false
  let q = $state('')
  let sort = $state<'newest' | 'oldest' | 'model'>('newest')
  let model = $state('')
  let models = $state<{ id: string; count: number }[]>([])
  let gen = 0
  let qTimer: ReturnType<typeof setTimeout> | undefined

  const filtered = $derived(!!q.trim() || !!model || sort !== 'newest')
  const sorts = [
    { value: 'newest' as const, label: 'Newest', icon: 'south' },
    { value: 'oldest' as const, label: 'Oldest', icon: 'north' },
    { value: 'model' as const, label: 'By model', icon: 'deployed_code' },
  ]
  const shortModel = (id: string) => id.replace(/^[a-z_]+:/, '').replace(/^.*[\\/]/, '').replace(/\.(safetensors|ckpt|gguf)$/, '')
  const modelItems = $derived([
    { value: '', label: 'All models' },
    ...models.map((m) => ({ value: m.id, label: shortModel(m.id), hint: String(m.count) })),
  ])

  $effect(() => {
    api.galleryModels().then((m) => (models = m), () => {})
  })

  function setQuery(v: string) {
    q = v
    clearTimeout(qTimer)
    qTimer = setTimeout(reload, 250)
  }
  function clearFilters() {
    q = ''
    model = ''
    sort = 'newest'
    reload()
  }

  const roots = $derived(all.filter((i) => !actions.deleted.has(i.id)))
  const stackItems = $derived(stack ? stack.items.filter((i) => !actions.deleted.has(i.id)) : [])
  const items = $derived(stack ? stackItems : roots)

  // fills columns in order (shortest column first) so reading order stays row-major
  const gap = $derived(mobile.current ? 8 : 12)
  const cols = $derived.by(() => {
    const min = mobile.current ? 150 : 200
    const n = Math.max(2, Math.floor((width + gap) / (min + gap)) || 2)
    const out: { it: GalleryItem; i: number }[][] = Array.from({ length: n }, () => [])
    const h = new Array(n).fill(0)
    items.forEach((it, i) => {
      let k = 0
      for (let c = 1; c < n; c++) if (h[c] < h[k] - 0.01) k = c
      out[k].push({ it, i })
      h[k] += it.height / it.width + 0.04
    })
    return out
  })

  async function more() {
    if (loading || done) return
    loading = true
    failed = ''
    const g = gen
    try {
      const r = await api.gallery(cursor ?? undefined, 60, { q: q.trim() || undefined, model: model || undefined, sort })
      // a newer search started while this page was loading
      if (g !== gen) return
      const seen = new Set(all.map((i) => i.id))
      all = [...all, ...r.items.filter((i) => !seen.has(i.id))]
      cursor = r.nextCursor
      if (!r.nextCursor) done = true
    } catch (e) {
      if (g === gen) failed = e instanceof Error ? e.message : String(e)
    } finally {
      if (g === gen) {
        loading = false
        first = false
      }
    }
  }

  function reload() {
    gen++
    loading = false
    all = []
    cursor = null
    done = false
    first = true
    more()
  }

  $effect(() => {
    untrack(more)
  })

  $effect(() => {
    if (!sentinel) return
    const io = new IntersectionObserver((e) => e[0].isIntersecting && !failed && !stack && more(), { rootMargin: '600px' })
    io.observe(sentinel)
    return () => io.disconnect()
  })

  $effect(() => {
    const recent = live.recent
    // filtered and re-sorted views are refreshed by the next search instead
    if (!recent.length || untrack(() => first || filtered)) return
    untrack(() => {
      const seen = new Set(all.map((i) => i.id))
      let next = all
      for (const it of [...recent].reverse()) {
        if (seen.has(it.id)) {
          // re-saved from an external editor: same id, new file
          const at = next.findIndex((r) => r.id === it.id)
          if (at >= 0 && next[at].url !== it.url) next = next.map((r, k) => (k === at ? { ...r, ...it } : r))
          if (stack?.items.some((s) => s.id === it.id && s.url !== it.url)) stack.items = stack.items.map((s) => (s.id === it.id ? it : s))
          continue
        }
        seen.add(it.id)
        if (it.stackId) {
          const at = next.findIndex((r) => r.id === it.stackId)
          if (at < 0) {
            if (stack?.root === it.stackId && !stack.items.some((s) => s.id === it.id)) stack.items = [...stack.items, it]
            continue
          }
          if (stack?.root === it.stackId && !stack.items.some((s) => s.id === it.id)) stack.items = [...stack.items, it]
          const root = { ...next[at], stackCount: (next[at].stackCount ?? 0) + 1, stackCover: it.thumbUrl }
          next = [root, ...next.slice(0, at), ...next.slice(at + 1)]
        } else next = [it, ...next]
      }
      if (next !== all) all = next
    })
  })

  async function openStack(it: GalleryItem) {
    stack = { root: it.id, items: [it], loading: true }
    try {
      const s = await api.stack(it.id)
      if (stack?.root === it.id) stack = { root: it.id, items: s, loading: false }
    } catch (e) {
      toast.error('Could not load stack', { description: e instanceof Error ? e.message : String(e) })
      stack = null
    }
  }
  function closeStack() {
    stack = null
    open = null
    exitSelect()
    if (stale) {
      stale = false
      reload()
    }
  }

  function toggle(id: string) {
    const s = new Set(selected)
    s.has(id) ? s.delete(id) : s.add(id)
    selected = s
  }
  function exitSelect() {
    selecting = false
    selected = new Set()
    confirmDel = false
  }
  async function delSelected() {
    if (!confirmDel) {
      confirmDel = true
      setTimeout(() => (confirmDel = false), 3000)
      return
    }
    confirmDel = false
    const targets = items.filter((i) => selected.has(i.id))
    let n = 0
    for (const it of targets) if (await removeImage(it)) n++
    toast.success(`Deleted ${n} image${n === 1 ? '' : 's'}`)
    if (stack || targets.some((t) => t.stackCount)) stale = true
    exitSelect()
    if (!stack && stale) {
      stale = false
      reload()
    }
  }
  function click(i: number, it: GalleryItem) {
    if (selecting) toggle(it.id)
    else if (!stack && it.stackCount) openStack(it)
    else open = i
  }

  $effect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || open !== null) return
      if (selecting) exitSelect()
      else if (stack) closeStack()
    }
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  })
</script>

<div class="gal">
  <header>
    {#if stack}
      <IconButton icon="arrow_back" label="Back to gallery" onclick={closeStack} />
      <h1>Stack</h1>
      <span class="cnt">{stackItems.length}</span>
    {:else}
      {#if mobile.current}<Logo size={22} />{/if}
      <h1>Gallery</h1>
    {/if}
    <span class="grow"></span>
    {#if selecting}
      <span class="cnt">{selected.size} selected</span>
      <Button variant="danger" icon={confirmDel ? 'delete_forever' : 'delete'} disabled={!selected.size} onclick={delSelected}>
        {confirmDel ? 'Confirm' : 'Delete'}
      </Button>
      <Button variant="default" onclick={exitSelect}>Done</Button>
    {:else if items.length}
      {#if stack && stackItems.length}
        <Button icon="brush" onclick={() => openInpaint(stackItems[stackItems.length - 1])}>Inpaint</Button>
      {/if}
      <IconButton icon="checklist" label="Select" onclick={() => (selecting = true)} />
    {/if}
  </header>
  {#if !stack && !selecting && (all.length || filtered)}
    <div class="tools">
      <label class="search">
        <span class="icon">search</span>
        <input
          type="search"
          placeholder="Tags, model, lora, seed"
          aria-label="Search gallery"
          value={q}
          oninput={(e) => setQuery(e.currentTarget.value)}
          spellcheck="false"
          autocomplete="off"
        />
        {#if q}
          <button type="button" class="clr" aria-label="Clear search" onclick={() => setQuery('')}><span class="icon">close</span></button>
        {/if}
      </label>
      <Select items={modelItems} bind:value={() => model, (v) => ((model = v), reload())} label="Model" size="sm" class="msel" />
      <Select items={sorts} bind:value={() => sort, (v) => ((sort = v), reload())} label="Sort" size="sm" class="ssel" />
    </div>
  {/if}

  <div class="scroll" bind:clientWidth={width}>
    {#if first}
      <div class="mason" style="--gap: {gap}px">
        {#each Array(Math.max(2, Math.floor(width / 212) || 2)) as _, c}
          <div class="col">
            {#each Array(4) as _, i}
              <Skeleton height="{[220, 300, 260, 340, 240][(i + c) % 5]}px" radius="var(--r-md)" />
            {/each}
          </div>
        {/each}
      </div>
    {:else if failed && !items.length}
      <EmptyState icon="cloud_off" title="Could not load" description={failed}>
        <Button icon="refresh" onclick={more}>Retry</Button>
      </EmptyState>
    {:else if !items.length && !stack?.loading && filtered && !stack}
      <EmptyState icon="search_off" title="No matches" description="Try fewer terms or another model.">
        <Button icon="filter_alt_off" onclick={clearFilters}>Clear filters</Button>
      </EmptyState>
    {:else if !items.length && !stack?.loading}
      <EmptyState icon="photo_library" title="No images yet" description="Generated images land here.">
        <Button variant="primary" icon="auto_awesome" onclick={() => (location.hash = '#/')}>Generate</Button>
      </EmptyState>
    {:else}
      <div class="mason" style="--gap: {gap}px">
        {#each cols as col, c (c)}
          <div class="col">
            {#each col as { it, i } (it.id)}
              {@const n = stack ? 0 : (it.stackCount ?? 0)}
              <div class="cell" class:stacked={n > 0}>
                <ImageTile
                  src={n && it.stackCover ? it.stackCover : it.thumbUrl}
                  aspect={it.width / it.height}
                  selectable={selecting}
                  selected={selected.has(it.id)}
                  onselect={() => toggle(it.id)}
                  onclick={() => click(i, it)}
                  alt={n ? 'Inpaint stack' : 'Generated image'}
                >
                  {#snippet badge()}
                    {#if it.editedWith}
                      <span class="sb" use:tooltip={`Edited in ${it.editedWith.name}`}>
                        <img src={api.editorIconUrl(it.editedWith.id)} alt="" onerror={(e) => ((e.currentTarget as HTMLImageElement).style.display = 'none')} />
                        <span class="icon">edit</span>
                      </span>
                    {/if}
                    {#if n}
                      <span class="sb"><span class="icon">layers</span>{n + 1}</span>
                    {:else if stack && it.stackId && !it.editedWith}
                      <span class="sb"><span class="icon">brush</span>{stackItems.indexOf(it)}</span>
                    {:else if stack}
                      <span class="sb">Original</span>
                    {/if}
                  {/snippet}
                </ImageTile>
              </div>
            {/each}
          </div>
        {/each}
      </div>
      {#if failed}
        <div class="more"><Button icon="refresh" onclick={more}>Retry</Button></div>
      {/if}
    {/if}
    <div bind:this={sentinel} class="sent"></div>
    {#if (loading && !first) || stack?.loading}<div class="more"><Skeleton width="120px" height="8px" /></div>{/if}
  </div>
</div>

{#if open !== null && items.length}
  <Lightbox {items} bind:index={open} onclose={() => (open = null)} onmore={stack ? undefined : more} />
{/if}

<style>
  .gal {
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  header {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    padding: var(--sp-3) var(--sp-4);
    min-height: 56px;
  }
  h1 {
    margin: 0;
    font-size: var(--fs-lg);
    font-weight: 600;
  }
  .grow {
    flex: 1;
  }
  .cnt {
    font-size: var(--fs-sm);
    color: var(--text-muted);
    margin-right: var(--sp-2);
  }
  .scroll {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 0 var(--sp-4) var(--sp-5);
  }
  .mason {
    display: flex;
    align-items: flex-start;
    gap: var(--gap);
  }
  .col {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: var(--gap);
  }
  .cell {
    position: relative;
  }
  .cell.stacked {
    margin-top: 8px;
  }
  .cell.stacked::before,
  .cell.stacked::after {
    content: '';
    position: absolute;
    left: 10px;
    right: 10px;
    top: -8px;
    height: 20px;
    border-radius: var(--r-md) var(--r-md) 0 0;
    border: 1px solid var(--hairline);
    background: var(--grad-3);
    z-index: 0;
  }
  .cell.stacked::after {
    left: 5px;
    right: 5px;
    top: -4px;
    background: var(--grad-4);
  }
  .cell :global(.tile) {
    z-index: 1;
  }
  .sb {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    height: 22px;
    padding: 0 7px 0 5px;
    border-radius: var(--r-sm);
    background: var(--scrim);
    border: 1px solid var(--hairline);
    color: var(--text);
    font-size: var(--fs-xs);
    font-variant-numeric: tabular-nums;
    backdrop-filter: blur(6px);
  }
  .sb .icon {
    font-size: 15px;
  }
  .sb img {
    width: 14px;
    height: 14px;
    object-fit: contain;
  }
  .sb img + .icon {
    display: none;
  }
  .sent {
    height: 1px;
  }
  .more {
    display: flex;
    justify-content: center;
    padding: var(--sp-4);
  }
  @media (max-width: 640px) {
    .scroll {
      padding: 0 var(--sp-2) var(--sp-5);
    }
  }
  .tools {
    flex: none;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--sp-2);
    padding: 0 var(--sp-4) var(--sp-3);
  }
  .search {
    flex: 1 1 260px;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    height: var(--control-h-sm);
    padding: 0 4px 0 var(--sp-2);
    border-radius: var(--r-sm);
    background: var(--grad-2);
    box-shadow: inset 0 1px 2px rgb(0 0 0 / 0.35);
    color: var(--text-muted);
    cursor: text;
  }
  .search:focus-within {
    box-shadow: var(--focus-ring);
  }
  .search .icon {
    font-size: 18px;
  }
  .search input {
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
  .search input::-webkit-search-cancel-button {
    display: none;
  }
  .clr {
    display: grid;
    place-items: center;
    width: 22px;
    height: 22px;
    padding: 0;
    border: 0;
    border-radius: var(--r-sm);
    background: none;
    color: var(--text-muted);
    cursor: pointer;
  }
  .clr:hover {
    background: var(--hover);
    color: var(--text);
  }
  .clr .icon {
    font-size: 16px;
  }
  .tools :global(.msel) {
    flex: 0 1 200px;
    min-width: 120px;
  }
  .tools :global(.ssel) {
    flex: 0 0 130px;
  }
  @media (max-width: 640px) {
    .tools {
      padding: 0 var(--sp-2) var(--sp-2);
    }
    .search {
      flex-basis: 100%;
    }
    .tools :global(.msel),
    .tools :global(.ssel) {
      flex: 1 1 0;
    }
  }
</style>
