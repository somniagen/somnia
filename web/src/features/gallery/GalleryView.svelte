<script lang="ts">
  import { untrack } from 'svelte'
  import { fly } from 'svelte/transition'
  import { actions, openInpaint, removeBackground, removeImage } from '$features/generate/actions.svelte'
  import { api } from '$lib/api'
  import { live } from '$lib/live.svelte'
  import type { GalleryItem } from '$lib/types'
  import { Button, EmptyState, IconButton, ImageTile, Menu, SearchField, Select, Skeleton, coarse, mobile, reducedMotion, toast, tooltip, type MenuItem } from '$lib/ui'
  import Logo from '$features/shell/Logo.svelte'
  import AlbumName from './AlbumName.svelte'
  import Compare from './Compare.svelte'
  import Lightbox from './Lightbox.svelte'
  import { library } from './library.svelte'

  let all = $state<GalleryItem[]>([])
  let cursor = $state<string | null>(null)
  let loading = $state(false)
  let done = $state(false)
  let failed = $state('')
  let first = $state(true)
  let picking = $state(false)
  let selected = $state<Set<string>>(new Set())
  const selecting = $derived(picking || selected.size > 0)
  let anchor: string | null = null
  let saving = $state(false)
  let scroller = $state<HTMLDivElement>()
  let band = $state<{ x: number; y: number; w: number; h: number } | null>(null)
  let open = $state<number | null>(null)
  let confirmDel = $state(false)
  let sentinel = $state<HTMLDivElement>()
  let width = $state(0)
  let stack = $state<{ root: string; items: GalleryItem[]; loading: boolean; cover: string | null } | null>(null)
  let stale = false
  let q = $state('')
  let sort = $state<'newest' | 'oldest' | 'model'>('newest')
  let model = $state('')
  let models = $state<{ id: string; count: number }[]>([])
  let favOnly = $state(false)
  let album = $state('')
  let comparing = $state<[GalleryItem, GalleryItem] | null>(null)
  let compareFrom = $state<GalleryItem | null>(null)
  let cutting = $state(false)
  let gen = 0
  let qTimer: ReturnType<typeof setTimeout> | undefined

  const filtered = $derived(!!q.trim() || !!model || sort !== 'newest' || favOnly || !!album)
  const albumItems = $derived([
    { value: '', label: 'All images', icon: 'photo_library' },
    ...library.albums.map((a) => ({ value: a.name, label: a.name, icon: 'photo_album', hint: String(a.count) })),
  ])
  const albumActions = $derived<MenuItem[]>([
    { label: 'Rename album', icon: 'edit', onselect: renameAlbum },
    { label: 'Delete album', icon: 'delete', danger: true, onselect: deleteAlbum },
  ])
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
    library.refresh()
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
    favOnly = false
    album = ''
    reload()
  }
  async function renameAlbum() {
    const name = await library.rename(album)
    if (name) {
      album = name
      reload()
    }
  }
  async function deleteAlbum() {
    if (await library.drop(album)) {
      album = ''
      reload()
    }
  }

  const roots = $derived(all.filter((i) => !actions.deleted.has(i.id)))
  const stackItems = $derived(stack ? stack.items.filter((i) => !actions.deleted.has(i.id)) : [])
  const items = $derived(stack ? stackItems : roots)
  // stacks show their cover: its aspect in the grid and the cover itself in the lightbox
  const face = (it: GalleryItem) =>
    !stack && it.stackCount && it.stackCoverItem && !actions.deleted.has(it.stackCoverItem.id) ? it.stackCoverItem : it
  const viewed = $derived(stack ? items : items.map(face))

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
      const f = face(it)
      h[k] += f.height / f.width + 0.04
    })
    return out
  })

  async function more() {
    if (loading || done) return
    loading = true
    failed = ''
    const g = gen
    try {
      const r = await api.gallery(cursor ?? undefined, 60, {
        q: q.trim() || undefined,
        model: model || undefined,
        sort,
        fav: favOnly ? 1 : undefined,
        album: album || undefined,
      })
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
    selected = new Set()
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
          const prev = next[at]
          const root = { ...prev, stackCount: (prev.stackCount ?? 0) + 1, ...(prev.coverId ? {} : { stackCover: it.thumbUrl, stackCoverId: it.id, stackCoverAlpha: !!it.alpha, stackCoverItem: it }) }
          if (stack?.root === it.stackId && !prev.coverId) stack.cover = it.id
          next = next.map((r, k) => (k === at ? root : r))
        } else next = [it, ...next]
      }
      if (next !== all) all = next
    })
  })

  async function openStack(it: GalleryItem) {
    const cover = it.stackCoverId ?? null
    stack = { root: it.id, items: [it], loading: true, cover }
    try {
      const s = await api.stack(it.id)
      if (stack?.root === it.id) stack = { root: it.id, items: s, loading: false, cover }
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
    anchor = id
  }
  function range(id: string) {
    const ids = items.map((i) => i.id)
    const a = ids.indexOf(anchor ?? id)
    const b = ids.indexOf(id)
    if (a < 0 || b < 0) return toggle(id)
    selected = new Set([...selected, ...ids.slice(Math.min(a, b), Math.max(a, b) + 1)])
  }
  function selectAll() {
    selected = new Set(items.map((i) => i.id))
  }
  function exitSelect() {
    picking = false
    selected = new Set()
    anchor = null
    confirmDel = false
  }

  // a selected stack exports only its cover
  async function downloadSelected() {
    const ids = items.filter((i) => selected.has(i.id)).map((i) => (!stack && i.stackCount ? (i.stackCoverId ?? i.id) : i.id))
    if (!ids.length || saving) return
    saving = true
    try {
      const { name, blob } = await api.downloadImages(ids)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = name
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 30000)
    } catch (e) {
      toast.error('Download failed', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      saving = false
    }
  }

  async function setCover(it: GalleryItem) {
    try {
      const root = await api.setCover(it.id)
      all = all.map((r) => (r.id === root.id ? { ...r, ...root } : r))
      if (stack?.root === root.id) stack.cover = root.stackCoverId ?? it.id
      toast.success('Stack cover set')
    } catch (e) {
      toast.error('Could not set cover', { description: e instanceof Error ? e.message : String(e) })
    }
  }

  // rubber band selection for mice, long press for touch
  let suppressUntil = 0
  let drag: {
    x0: number
    y0: number
    cx: number
    cy: number
    active: boolean
    base: Set<string>
    xor: boolean
    onTile: boolean
    rects: { id: string; l: number; t: number; r: number; b: number }[]
    raf: number
  } | null = null
  let press: { x: number; y: number; timer: ReturnType<typeof setTimeout>; fired: boolean } | null = null

  function content(cx: number, cy: number) {
    const r = scroller!.getBoundingClientRect()
    return { x: cx - r.left + scroller!.scrollLeft, y: cy - r.top + scroller!.scrollTop }
  }

  function down(e: PointerEvent) {
    const t = e.target as HTMLElement
    if (!scroller || t.closest('button, input, a')) return
    const cell = t.closest<HTMLElement>('.cell[data-id]')
    if (e.pointerType !== 'mouse') {
      if (!cell) return
      const id = cell.dataset.id!
      pressEnd()
      press = {
        x: e.clientX,
        y: e.clientY,
        fired: false,
        timer: setTimeout(() => {
          if (!press) return
          press.fired = true
          picking = true
          if (!selected.has(id)) toggle(id)
          navigator.vibrate?.(12)
        }, 450),
      }
      return
    }
    if (e.button !== 0) return
    e.preventDefault()
    const p = content(e.clientX, e.clientY)
    const add = e.shiftKey || e.ctrlKey || e.metaKey
    drag = {
      x0: p.x,
      y0: p.y,
      cx: e.clientX,
      cy: e.clientY,
      active: false,
      base: add ? new Set(selected) : new Set(),
      xor: e.ctrlKey || e.metaKey,
      onTile: !!cell,
      rects: [],
      raf: 0,
    }
    addEventListener('pointermove', dragMove)
    addEventListener('pointerup', dragUp)
    addEventListener('pointercancel', dragUp)
  }

  function pressMove(e: PointerEvent) {
    if (press && !press.fired && Math.hypot(e.clientX - press.x, e.clientY - press.y) > 10) pressEnd()
  }
  function pressEnd() {
    if (!press) return
    clearTimeout(press.timer)
    if (press.fired) suppressUntil = performance.now() + 400
    press = null
  }

  function dragMove(e: PointerEvent) {
    if (!drag) return
    drag.cx = e.clientX
    drag.cy = e.clientY
    if (!drag.active) {
      const p = content(e.clientX, e.clientY)
      if (Math.hypot(p.x - drag.x0, p.y - drag.y0) < 6) return
      drag.active = true
      const o = content(0, 0)
      drag.rects = [...scroller!.querySelectorAll<HTMLElement>('.cell[data-id]')].map((el) => {
        const r = el.getBoundingClientRect()
        return { id: el.dataset.id!, l: r.left + o.x, t: r.top + o.y, r: r.right + o.x, b: r.bottom + o.y }
      })
      tick()
    }
    paint()
  }
  function paint() {
    if (!drag) return
    const p = content(drag.cx, drag.cy)
    const x = Math.min(p.x, drag.x0)
    const y = Math.min(p.y, drag.y0)
    const w = Math.abs(p.x - drag.x0)
    const h = Math.abs(p.y - drag.y0)
    band = { x, y, w, h }
    const next = new Set(drag.base)
    for (const r of drag.rects) {
      if (r.r < x || r.l > x + w || r.b < y || r.t > y + h) continue
      if (drag.xor && drag.base.has(r.id)) next.delete(r.id)
      else next.add(r.id)
    }
    if (next.size !== selected.size || [...next].some((id) => !selected.has(id))) selected = next
  }
  // scrolls while the pointer is near the top or bottom edge
  function tick() {
    if (!drag?.active || !scroller) return
    const r = scroller.getBoundingClientRect()
    const edge = 48
    const d = drag.cy < r.top + edge ? drag.cy - r.top - edge : drag.cy > r.bottom - edge ? drag.cy - r.bottom + edge : 0
    if (d) {
      scroller.scrollTop += d / 3
      paint()
    }
    drag.raf = requestAnimationFrame(tick)
  }
  function dragUp(e: PointerEvent) {
    removeEventListener('pointermove', dragMove)
    removeEventListener('pointerup', dragUp)
    removeEventListener('pointercancel', dragUp)
    const d = drag
    drag = null
    band = null
    if (!d) return
    cancelAnimationFrame(d.raf)
    if (d.active) suppressUntil = performance.now() + 400
    else if (!d.onTile && e.type === 'pointerup' && selecting) exitSelect()
  }
  $effect(() => () => {
    removeEventListener('pointermove', dragMove)
    removeEventListener('pointerup', dragUp)
    removeEventListener('pointercancel', dragUp)
    pressEnd()
  })
  const picked = $derived(items.filter((i) => selected.has(i.id)))
  const allFav = $derived(picked.length > 0 && picked.every((i) => i.favorite))
  const addMenu = $derived<MenuItem[]>([
    ...library.albums.map((a) => ({ label: a.name, icon: 'photo_album', onselect: () => library.add(picked, a.name) })),
    ...(library.albums.length ? [{ separator: true as const }] : []),
    { label: 'New album', icon: 'add', onselect: () => library.add(picked) },
  ])

  async function favSelected() {
    const on = !allFav
    await library.favorite(picked, on)
    if (favOnly && !on) reload()
  }
  async function unalbumSelected() {
    await library.remove(picked, album)
    reload()
  }
  async function cutSelected() {
    if (cutting) return
    cutting = true
    let n = 0
    for (const it of picked) if (await removeBackground(it)) n++
    cutting = false
    if (!n) return
    toast.success(`Removed ${n} background${n === 1 ? '' : 's'}`, { description: 'Saved in the same stacks' })
    exitSelect()
    if (stack) {
      const root = stack.root
      api.stack(root).then((s) => stack?.root === root && (stack.items = s), () => {})
    } else reload()
  }
  function compareSelected() {
    if (picked.length === 2) comparing = [picked[0], picked[1]]
  }
  // the lightbox picks the first image, the next tile click the second
  function startCompare(it: GalleryItem) {
    open = null
    compareFrom = it
    toast.info('Pick an image to compare with', { duration: 4000 })
  }
  function toggleFav(it: GalleryItem) {
    return library.favorite([it], !it.favorite)
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
  function click(i: number, it: GalleryItem, e: MouseEvent) {
    if (performance.now() < suppressUntil) return
    if (compareFrom) {
      if (compareFrom.id !== it.id) comparing = [compareFrom, it]
      compareFrom = null
      return
    }
    if (e.shiftKey) range(it.id)
    else if (selecting || e.ctrlKey || e.metaKey) toggle(it.id)
    else if (!stack && it.stackCount) openStack(it)
    else open = i
  }

  $effect(() => {
    const key = (e: KeyboardEvent) => {
      if (open !== null) return
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a' && !(e.target as HTMLElement | null)?.closest('input, textarea')) {
        e.preventDefault()
        selectAll()
        return
      }
      if (e.key !== 'Escape') return
      if (compareFrom) compareFrom = null
      else if (selecting) exitSelect()
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
    {#if items.length}
      {#if stack && stackItems.length}
        <Button icon="brush" onclick={() => openInpaint(stackItems[stackItems.length - 1])}>Inpaint</Button>
      {/if}
      <IconButton icon="checklist" label="Select" active={selecting} onclick={() => (selecting ? exitSelect() : (picking = true))} />
    {/if}
  </header>
  {#if !stack && (all.length || filtered)}
    <div class="tools">
      <SearchField
        size="sm"
        class="search"
        placeholder="Tags, model, lora, seed"
        aria-label="Search gallery"
        bind:value={() => q, setQuery}
      />
      <Select items={modelItems} bind:value={() => model, (v) => ((model = v), reload())} label="Model" size="sm" class="msel" />
      <Select items={sorts} bind:value={() => sort, (v) => ((sort = v), reload())} label="Sort" size="sm" class="ssel" />
      {#if library.albums.length || album}
        <Select items={albumItems} bind:value={() => album, (v) => ((album = v), reload())} label="Album" size="sm" class="asel" />
      {/if}
      {#if album}
        <Menu items={albumActions} placement="bottom-end">
          {#snippet trigger({ toggle })}
            <IconButton icon="more_vert" label="Album options" size="sm" onclick={toggle} />
          {/snippet}
        </Menu>
      {/if}
      <IconButton icon="favorite" label={favOnly ? 'Show all' : 'Favorites'} size="sm" active={favOnly} onclick={() => ((favOnly = !favOnly), reload())} />
    </div>
  {/if}

  <div
    class="scroll"
    class:banding={!!band}
    class:sel={selecting}
    class:picking={!!compareFrom}
    role="presentation"
    bind:this={scroller}
    bind:clientWidth={width}
    onpointerdown={down}
    onpointermove={pressMove}
    onpointerup={pressEnd}
    onpointercancel={pressEnd}
    oncontextmenu={(e) => coarse.current && (e.target as HTMLElement).closest('.cell') && e.preventDefault()}
  >
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
              {@const isCover = !!stack && stack.cover === it.id}
              {@const f = face(it)}
              <div class="cell" class:stacked={n > 0} data-id={it.id}>
                <ImageTile
                  src={f.thumbUrl}
                  aspect={f.width / f.height}
                  selectable={selecting || !coarse.current}
                  selected={selected.has(it.id)}
                  checker={!!f.alpha}
                  onselect={() => toggle(it.id)}
                  onclick={(e) => click(i, it, e)}
                  alt={n ? 'Inpaint stack' : 'Generated image'}
                >
                  {#if stack && !isCover && !selecting && !coarse.current}
                    <span class="cov">
                      <IconButton icon="bookmark_add" label="Set as cover" size="sm" onclick={(e) => (e.stopPropagation(), setCover(it))} />
                    </span>
                  {/if}
                  {#if !selecting && (it.favorite || !coarse.current)}
                    <button
                      type="button"
                      class="fav"
                      class:on={it.favorite}
                      aria-label={it.favorite ? 'Unfavorite' : 'Favorite'}
                      aria-pressed={!!it.favorite}
                      onclick={(e) => (e.stopPropagation(), toggleFav(it))}
                    >
                      <span class="icon">favorite</span>
                    </button>
                  {/if}
                  {#snippet badge()}
                    {#if isCover}
                      <span class="sb" use:tooltip={'Stack cover'}><span class="icon fill">bookmark</span></span>
                    {/if}
                    {#if it.editedWith}
                      <span class="sb" use:tooltip={`Edited in ${it.editedWith.name}`}>
                        <img src={api.editorIconUrl(it.editedWith.id)} alt="" onerror={(e) => ((e.currentTarget as HTMLImageElement).style.display = 'none')} />
                        <span class="icon">edit</span>
                      </span>
                    {/if}
                    {#if n}
                      <span class="sb"><span class="icon">layers</span>{n + 1}</span>
                    {:else if stack && it.alpha}
                      <span class="sb" use:tooltip={'Background removed'}><span class="icon">background_replace</span></span>
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
    {#if band}<div class="band" style="left: {band.x}px; top: {band.y}px; width: {band.w}px; height: {band.h}px"></div>{/if}
  </div>

  {#if selecting}
    <div class="selbar" role="toolbar" aria-label="Selection" transition:fly={{ y: 16, duration: reducedMotion.current ? 0 : 180 }}>
      <span class="num">{selected.size}</span>
      <IconButton icon="select_all" label="Select all (Ctrl+A)" onclick={selectAll} />
      {#if stack && selected.size === 1}
        {@const one = stackItems.find((i) => selected.has(i.id))}
        {#if one}
          <IconButton icon={stack.cover === one.id ? 'bookmark_added' : 'bookmark_add'} label="Set as cover" active={stack.cover === one.id} onclick={() => setCover(one)} />
        {/if}
      {/if}
      <IconButton icon="favorite" label={allFav ? 'Unfavorite' : 'Favorite'} active={allFav} disabled={!selected.size} onclick={favSelected} />
      <Menu items={addMenu} placement="top-start">
        {#snippet trigger({ toggle })}
          <IconButton icon="photo_album" label="Add to album" disabled={!selected.size} onclick={toggle} />
        {/snippet}
      </Menu>
      {#if album && !stack}
        <IconButton icon="bookmark_remove" label="Remove from album" disabled={!selected.size} onclick={unalbumSelected} />
      {/if}
      <IconButton
        icon={cutting ? 'progress_activity' : 'background_replace'}
        label={cutting ? 'Removing backgrounds' : 'Remove background'}
        class={cutting ? 'spin' : undefined}
        disabled={!selected.size || cutting}
        onclick={cutSelected}
      />
      {#if selected.size === 2}
        <IconButton icon="compare" label="Compare" onclick={compareSelected} />
      {/if}
      <IconButton icon={saving ? 'progress_activity' : 'download'} label={selected.size > 1 ? 'Download as zip' : 'Download'} disabled={!selected.size || saving} onclick={downloadSelected} />
      <IconButton
        icon={confirmDel ? 'delete_forever' : 'delete'}
        label={confirmDel ? 'Click again to delete' : 'Delete'}
        variant={confirmDel ? 'danger' : 'ghost'}
        disabled={!selected.size}
        onclick={delSelected}
      />
      <span class="sep"></span>
      <IconButton icon="close" label="Clear selection (Esc)" onclick={exitSelect} />
    </div>
  {/if}
</div>

{#if open !== null && items.length}
  <Lightbox
    items={viewed}
    bind:index={open}
    onclose={() => (open = null)}
    onmore={stack ? undefined : more}
    coverId={stack?.cover}
    onsetcover={stack ? setCover : undefined}
    oncompare={startCompare}
  />
{/if}

{#if comparing}
  <Compare a={comparing[0]} b={comparing[1]} onclose={() => (comparing = null)} />
{/if}

<AlbumName />

<style>
  .gal {
    position: relative;
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .scroll {
    position: relative;
  }
  .scroll.banding {
    user-select: none;
  }
  .scroll.sel {
    padding-bottom: 80px;
  }
  .scroll.banding :global(.tile) {
    pointer-events: none;
  }
  .band {
    position: absolute;
    z-index: 2;
    border: 1px solid var(--accent);
    border-radius: var(--r-sm);
    background: var(--accent-soft);
    pointer-events: none;
  }
  .cell {
    -webkit-touch-callout: none;
    -webkit-user-select: none;
    user-select: none;
  }
  .cov {
    position: absolute;
    left: 6px;
    bottom: 6px;
    z-index: 2;
    border-radius: var(--r-sm);
    background: var(--scrim);
    opacity: 0;
    transition: opacity var(--dur-fast) var(--ease);
  }
  .cell:hover .cov,
  .cov:focus-within {
    opacity: 1;
  }
  .fav {
    position: absolute;
    right: 6px;
    bottom: 6px;
    z-index: 2;
    display: grid;
    place-items: center;
    width: 28px;
    height: 28px;
    padding: 0;
    border: 1px solid var(--hairline);
    border-radius: var(--r-sm);
    background: var(--scrim);
    color: var(--text);
    cursor: pointer;
    backdrop-filter: blur(6px);
    opacity: 0;
    transition:
      opacity var(--dur-fast) var(--ease),
      transform var(--dur-fast) var(--ease);
  }
  .fav .icon {
    font-size: 17px;
  }
  .fav.on .icon {
    font-variation-settings: 'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24;
  }
  .cell:hover .fav,
  .fav:focus-visible,
  .fav.on {
    opacity: 1;
  }
  .fav:hover {
    background: var(--grad-4);
  }
  .fav:active {
    transform: scale(0.9);
  }
  .selbar :global(.spin .icon) {
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .picking :global(.tile) {
    cursor: crosshair;
  }
  .fill {
    font-variation-settings: 'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24;
  }
  .selbar {
    position: absolute;
    left: 0;
    right: 0;
    width: fit-content;
    max-width: calc(100% - var(--sp-4));
    flex-wrap: wrap;
    justify-content: center;
    margin: 0 auto;
    bottom: var(--sp-4);
    z-index: 5;
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 4px;
    border: 1px solid var(--hairline);
    border-radius: var(--r-md);
    background: var(--grad-3);
    box-shadow: var(--sheen), var(--shadow-3);
  }
  .num {
    min-width: 32px;
    padding: 0 var(--sp-2);
    text-align: center;
    font-size: var(--fs-sm);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .sep {
    width: 1px;
    height: 20px;
    margin: 0 2px;
    background: var(--hairline);
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
  .tools :global(.search) {
    flex: 1 1 260px;
  }
  .tools :global(.msel) {
    flex: 0 1 200px;
    min-width: 120px;
  }
  .tools :global(.ssel) {
    flex: 0 0 130px;
  }
  .tools :global(.asel) {
    flex: 0 1 180px;
    min-width: 120px;
  }
  @media (max-width: 640px) {
    .tools {
      padding: 0 var(--sp-2) var(--sp-2);
    }
    .tools :global(.search) {
      flex-basis: 100%;
    }
    .tools :global(.msel),
    .tools :global(.ssel),
    .tools :global(.asel) {
      flex: 1 1 0;
    }
  }
</style>
