<script lang="ts">
  import { fade } from 'svelte/transition'
  import { download, reuse } from '$features/generate/actions.svelte'
  import ImageActions from '$features/generate/ImageActions.svelte'
  import SendTo from '$features/prompt/SendTo.svelte'
  import { promptOf } from '$features/prompt/send.svelte'
  import type { GalleryItem } from '$lib/types'
  import { BottomSheet, Button, Chip, IconButton, Menu, clamp, mobile, reducedMotion, toast, type MenuItem } from '$lib/ui'
  import { library } from './library.svelte'

  let {
    items,
    index = $bindable(0),
    onclose,
    onremoved,
    onmore,
    coverId,
    onsetcover,
    oncompare,
  }: {
    items: GalleryItem[]
    index: number
    onclose: () => void
    onremoved?: (item: GalleryItem) => void
    onmore?: () => void
    coverId?: string | null
    onsetcover?: (item: GalleryItem) => void
    oncompare?: (item: GalleryItem) => void
  } = $props()

  const PAD = 12
  const item = $derived(items[index])
  const p = $derived(item?.params ?? null)

  let view = $state<HTMLDivElement>()
  let strip = $state<HTMLDivElement>()
  let cw = $state(0)
  let ch = $state(0)
  let z = $state(1)
  let tx = $state(0)
  let ty = $state(0)
  let anim = $state(false)
  let dx = $state(0)
  let dragging = $state(false)
  let settle = $state(false)
  let panel = $state(read())
  let sheet = $state(false)
  let curId: string | undefined

  const dpr = typeof devicePixelRatio === 'number' ? devicePixelRatio : 1
  const fitOf = (it: GalleryItem | undefined) =>
    it ? Math.max(0.0001, Math.min((cw - PAD * 2) / it.width, (ch - PAD * 2) / it.height)) : 1
  const fit = $derived(fitOf(item))
  const zOne = $derived(Math.max(2, 1 / (fit * dpr)))
  const maxZ = $derived(Math.max(8, zOne * 4))
  const dur = $derived(reducedMotion.current ? 0 : 200)

  const slides = $derived(
    [-1, 0, 1].flatMap((o) => {
      const it = items[index + o]
      return it ? [{ it, off: o }] : []
    }),
  )

  function read() {
    try {
      return localStorage.getItem('somnia.lightbox.params') !== '0'
    } catch {
      return true
    }
  }
  function togglePanel() {
    if (mobile.current) {
      sheet = !sheet
      return
    }
    panel = !panel
    try {
      localStorage.setItem('somnia.lightbox.params', panel ? '1' : '0')
    } catch {}
  }

  function resetView(animate = false) {
    if (animate) pulse()
    z = 1
    tx = 0
    ty = 0
  }
  function pulse() {
    anim = true
    setTimeout(() => (anim = false), 260)
  }
  function limit() {
    if (!item) return
    const mw = Math.max(0, (item.width * fit * z - cw) / 2 + PAD)
    const mh = Math.max(0, (item.height * fit * z - ch) / 2 + PAD)
    tx = item.width * fit * z <= cw ? 0 : clamp(tx, -mw, mw)
    ty = item.height * fit * z <= ch ? 0 : clamp(ty, -mh, mh)
  }
  function zoomAt(px: number, py: number, nz: number) {
    nz = clamp(nz, 1, maxZ)
    const k = nz / z
    tx = px - (px - tx) * k
    ty = py - (py - ty) * k
    z = nz
    if (z < 1.001) return resetView()
    limit()
  }
  function rel(e: { clientX: number; clientY: number }) {
    const r = view!.getBoundingClientRect()
    return { x: e.clientX - r.left - r.width / 2, y: e.clientY - r.top - r.height / 2 }
  }
  function toggleZoom(x = 0, y = 0) {
    pulse()
    if (z > 1.05) resetView()
    else zoomAt(x, y, zOne)
  }

  let busy = false
  function go(d: number) {
    const n = index + d
    if (n < 0 || n >= items.length || busy) return
    busy = true
    settle = true
    dx = -d * cw
    setTimeout(
      () => {
        settle = false
        dx = 0
        setIndex(n)
        busy = false
      },
      reducedMotion.current ? 0 : 200,
    )
  }
  function jump(n: number) {
    if (n === index || busy) return
    if (Math.abs(n - index) === 1) return go(n - index)
    setIndex(n)
  }
  function setIndex(n: number) {
    index = n
    curId = items[n]?.id
    resetView()
    if (n >= items.length - 3) onmore?.()
  }

  $effect.pre(() => {
    const id = item?.id
    if (id === curId) return
    const at = items.findIndex((i) => i.id === curId)
    if (at >= 0 && at !== index && !busy) {
      index = at
      return
    }
    curId = id
    resetView()
  })

  $effect(() => {
    const n = index
    const el = strip?.children[n - winStart] as HTMLElement | undefined
    if (!el || !strip) return
    strip.scrollTo({ left: el.offsetLeft - strip.clientWidth / 2 + el.offsetWidth / 2, behavior: reducedMotion.current ? 'auto' : 'smooth' })
  })

  const winStart = $derived(Math.max(0, index - 60))
  const win = $derived(items.slice(winStart, index + 61))

  function removed() {
    const it = item
    if (!it) return
    onremoved?.(it)
    const len = items.length
    if (len === 0) return onclose()
    index = Math.min(index, len - 1)
    curId = items[index]?.id
    resetView()
  }

  $effect(() => {
    const key = (e: KeyboardEvent) => {
      if (sheet || (e.target as HTMLElement | null)?.closest('input, textarea')) return
      if (e.key === 'Escape') {
        e.stopPropagation()
        onclose()
      } else if (e.key === 'ArrowLeft') go(-1)
      else if (e.key === 'ArrowRight') go(1)
      else if (e.key === '+' || e.key === '=') (pulse(), zoomAt(0, 0, z * 1.5))
      else if (e.key === '-') (pulse(), zoomAt(0, 0, z / 1.5))
      else if (e.key === '0') resetView(true)
      else if (e.key === '1') toggleZoom()
      else if (e.key === 'i') togglePanel()
      else return
      if (e.key !== 'Escape') e.preventDefault()
    }
    addEventListener('keydown', key, true)
    const prev = document.documentElement.style.overflow
    document.documentElement.style.overflow = 'hidden'
    return () => {
      removeEventListener('keydown', key, true)
      document.documentElement.style.overflow = prev
    }
  })

  $effect(() => {
    const el = view
    if (!el) return
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      anim = false
      const { x, y } = rel(e)
      const k = e.ctrlKey ? 0.01 : 0.0018
      zoomAt(x, y, z * Math.exp(-e.deltaY * k))
    }
    el.addEventListener('wheel', wheel, { passive: false })
    return () => el.removeEventListener('wheel', wheel)
  })

  const ptrs = new Map<number, { x: number; y: number }>()
  let start = { x: 0, y: 0, tx: 0, ty: 0, t: 0, moved: false, swipe: false }
  let pinch: { d: number; z: number; ux: number; uy: number } | null = null
  let lastTap = { t: 0, x: 0, y: 0 }
  let vel = 0
  let downOnImg = false
  let lastMove = { x: 0, t: 0 }

  function down(e: PointerEvent) {
    if (e.pointerType === 'mouse' && e.button !== 0) return
    if (busy) return
    try {
      view!.setPointerCapture(e.pointerId)
    } catch {}
    downOnImg = !!(e.target as HTMLElement).closest('img, .nav')
    ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY })
    anim = false
    if (ptrs.size === 2) {
      const [a, b] = [...ptrs.values()]
      const m = rel({ clientX: (a.x + b.x) / 2, clientY: (a.y + b.y) / 2 })
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, z, ux: (m.x - tx) / z, uy: (m.y - ty) / z }
      start.moved = true
      dx = 0
      dragging = false
    } else if (ptrs.size === 1) rebase(e)
  }
  function rebase(e: { clientX: number; clientY: number }) {
    start = { x: e.clientX, y: e.clientY, tx, ty, t: performance.now(), moved: false, swipe: false }
    lastMove = { x: e.clientX, t: performance.now() }
    vel = 0
  }
  function move(e: PointerEvent) {
    const pt = ptrs.get(e.pointerId)
    if (!pt) return
    pt.x = e.clientX
    pt.y = e.clientY
    if (pinch && ptrs.size >= 2) {
      const [a, b] = [...ptrs.values()]
      const m = rel({ clientX: (a.x + b.x) / 2, clientY: (a.y + b.y) / 2 })
      const nz = clamp((pinch.z * (Math.hypot(a.x - b.x, a.y - b.y) || 1)) / pinch.d, 1, maxZ)
      z = nz
      tx = m.x - pinch.ux * nz
      ty = m.y - pinch.uy * nz
      limit()
      return
    }
    const mx = e.clientX - start.x
    const my = e.clientY - start.y
    if (!start.moved && Math.hypot(mx, my) > 6) {
      start.moved = true
      start.swipe = z <= 1.01 && Math.abs(mx) > Math.abs(my)
      if (start.swipe) dragging = true
    }
    if (!start.moved) return
    if (z > 1.01) {
      tx = start.tx + mx
      ty = start.ty + my
      limit()
    } else if (start.swipe) {
      const edge = (index === 0 && mx > 0) || (index >= items.length - 1 && mx < 0)
      dx = edge ? mx * 0.3 : mx
      const now = performance.now()
      vel = (e.clientX - lastMove.x) / Math.max(1, now - lastMove.t)
      lastMove = { x: e.clientX, t: now }
    }
  }
  function up(e: PointerEvent) {
    if (!ptrs.delete(e.pointerId)) return
    if (pinch) {
      if (ptrs.size < 2) pinch = null
      if (z < 1.02) resetView(true)
      const left = [...ptrs.values()][0]
      if (left) rebase({ clientX: left.x, clientY: left.y })
      start.moved = true
      return
    }
    if (dragging) {
      dragging = false
      const far = Math.abs(dx) > cw * 0.2 || Math.abs(vel) > 0.5
      const d = dx < 0 ? 1 : -1
      if (far && index + d >= 0 && index + d < items.length) {
        go(d)
      } else {
        settle = true
        dx = 0
        setTimeout(() => (settle = false), 220)
      }
      return
    }
    if (!start.moved && e.type === 'pointerup') tap(e)
  }
  function tap(e: PointerEvent) {
    const now = performance.now()
    const { x, y } = rel(e)
    const near = Math.hypot(x - lastTap.x, y - lastTap.y) < 30
    if (now - lastTap.t < 320 && near) {
      lastTap.t = 0
      toggleZoom(x, y)
    } else {
      lastTap = { t: now, x, y }
      if (e.pointerType === 'mouse' && z <= 1 && !downOnImg) onclose()
    }
  }

  async function copy(text: string, what: string) {
    try {
      await navigator.clipboard.writeText(text)
      toast.success(`${what} copied`)
    } catch {
      toast.error('Copy failed')
    }
  }

  const short = (id: string) => id.split(':').pop()?.replace(/\.(safetensors|ckpt|pt|pth)$/, '') ?? id
  const date = (t: number) => new Date(t * (t < 1e12 ? 1000 : 1)).toLocaleString()
  const pct = $derived(Math.round(z * fit * 100))

  $effect(() => {
    library.refresh()
  })
  const albumMenu = $derived<MenuItem[]>(
    item
      ? [
          ...library.albums
            .filter((a) => !item.albums?.includes(a.name))
            .map((a) => ({ label: a.name, icon: 'photo_album', onselect: () => library.add([item], a.name) })),
          ...(library.albums.some((a) => !item.albums?.includes(a.name)) ? [{ separator: true as const }] : []),
          { label: 'New album', icon: 'add', onselect: () => library.add([item]) },
        ]
      : [],
  )
</script>

{#snippet details()}
  {#if p && item}
    <div class="dl">
      <div class="sec">
        <div class="sh">
          <span>Prompt</span>
          <IconButton icon="content_copy" label="Copy prompt" size="sm" onclick={() => copy(p.prompt, 'Prompt')} />
        </div>
        <div class="txt">{p.prompt || '-'}</div>
      </div>
      {#if p.negative}
        <div class="sec">
          <div class="sh">
            <span>Negative</span>
            <IconButton icon="content_copy" label="Copy negative" size="sm" onclick={() => copy(p.negative, 'Negative')} />
          </div>
          <div class="txt faint">{p.negative}</div>
        </div>
      {/if}
      <div class="grid">
        <div><span>Model</span>{short(p.model)}</div>
        <div><span>Size</span>{item.width}x{item.height}</div>
        <div><span>Seed</span>{item.seed}</div>
        <div><span>Steps</span>{p.steps}</div>
        <div><span>CFG</span>{p.cfg}</div>
        <div><span>Sampler</span>{p.sampler} / {p.scheduler}</div>
      </div>
      {#if p.loras.length}
        <div class="sec">
          <div class="sh"><span>LoRAs</span></div>
          {#each p.loras as l}<div class="lora">{short(l.id)} <span class="w">{l.weight}</span></div>{/each}
        </div>
      {/if}
      <div class="flags">
        {#if p.secondPass.enabled}<span>Second pass</span>{/if}
        {#each p.detailers.filter((d) => d.enabled) as _}<span>Detailer</span>{/each}
        {#if p.upscale.enabled}<span>Upscale</span>{/if}
        {#if p.pag.enabled}<span>PAG</span>{/if}
      </div>
      {#if item.editedWith}
        <div class="edited"><span class="icon">edit</span>Edited in {item.editedWith.name}</div>
      {/if}
      <div class="albums">
        {#each item.albums ?? [] as a (a)}
          <Chip label={a} size="sm" removable onremove={() => library.remove([item], a)} />
        {/each}
        <Menu items={albumMenu}>
          {#snippet trigger({ toggle })}
            <Button size="sm" variant="ghost" icon="photo_album" onclick={toggle}>{item.albums?.length ? 'Add' : 'Add to album'}</Button>
          {/snippet}
        </Menu>
      </div>
      <div class="date">{date(item.createdAt)}</div>
      <div class="btns">
        <Button variant="primary" icon="history" full onclick={() => (reuse(item), (sheet = false), onclose())}>Reuse params</Button>
        <Button icon="download" onclick={() => download(item)}>Save</Button>
        <SendTo get={() => promptOf(p)} only={['inpaint', 'grid']} after={() => ((sheet = false), onclose())} size="md" />
      </div>
    </div>
  {/if}
{/snippet}

<div class="lb" transition:fade={{ duration: dur }} role="dialog" aria-modal="true" aria-label="Image viewer">
  <div class="stage">
    <div class="top">
      <span class="pos">{index + 1} / {items.length}</span>
      {#if z > 1.01}<span class="zoom">{pct}%</span>{/if}
      <span class="grow"></span>
      {#if item && !mobile.current}<ImageActions {item} onremoved={removed} onnavigate={onclose} />{/if}
      {#if item}
        <IconButton
          icon="favorite"
          label={item.favorite ? 'Unfavorite' : 'Favorite'}
          active={!!item.favorite}
          onclick={() => library.favorite([item], !item.favorite)}
        />
      {/if}
      {#if item && oncompare && !mobile.current}
        <IconButton icon="compare" label="Compare with..." onclick={() => oncompare(item)} />
      {/if}
      {#if item && onsetcover}
        <IconButton
          icon={item.id === coverId ? 'bookmark_added' : 'bookmark_add'}
          label={item.id === coverId ? 'Stack cover' : 'Set as stack cover'}
          active={item.id === coverId}
          onclick={() => item.id !== coverId && onsetcover(item)}
        />
      {/if}
      <IconButton
        icon={z > 1.05 ? 'zoom_out_map' : 'zoom_in'}
        label={z > 1.05 ? 'Fit to screen' : 'Zoom to 1:1'}
        onclick={() => toggleZoom()}
      />
      {#if p}
        <IconButton
          icon={mobile.current ? 'info' : panel ? 'right_panel_close' : 'right_panel_open'}
          label="Details"
          active={mobile.current ? sheet : panel}
          onclick={togglePanel}
        />
      {/if}
      <IconButton icon="close" label="Close" onclick={onclose} />
    </div>

    <div
      class="view"
      class:grab={z > 1.01}
      role="presentation"
      bind:this={view}
      bind:clientWidth={cw}
      bind:clientHeight={ch}
      onpointerdown={down}
      onpointermove={move}
      onpointerup={up}
      onpointercancel={up}
    >
      <div class="track" style="transform: translate3d({dx}px, 0, 0); transition: {settle && !dragging ? `transform ${dur}ms var(--ease)` : 'none'}">
        {#each slides as s (s.it.id)}
          {@const cur = s.off === 0}
          {@const f = fitOf(s.it)}
          <div class="slide" style="transform: translate3d({s.off * 100}%, 0, 0)">
            <img
              src={s.it.url}
              alt=""
              draggable="false"
              class:alpha={s.it.alpha}
              style="width: {s.it.width * f}px; height: {s.it.height * f}px; transform: translate3d({cur ? tx : 0}px, {cur ? ty : 0}px, 0) scale({cur ? z : 1}); transition: {anim && cur ? `transform ${dur + 40}ms var(--ease)` : 'none'}"
            />
          </div>
        {/each}
      </div>
      {#if !mobile.current}
        <button class="nav l" type="button" aria-label="Previous" disabled={index === 0} onclick={() => go(-1)}><span class="icon">chevron_left</span></button>
        <button class="nav r" type="button" aria-label="Next" disabled={index >= items.length - 1} onclick={() => go(1)}><span class="icon">chevron_right</span></button>
      {/if}
    </div>

    {#if items.length > 1}
      <div class="film" bind:this={strip}>
        {#each win as it, i (it.id)}
          <button type="button" class="th" class:cur={winStart + i === index} aria-label="Show image {winStart + i + 1}" onclick={() => jump(winStart + i)}>
            <img src={it.thumbUrl} alt="" loading="lazy" draggable="false" class:alpha={it.alpha} />
          </button>
        {/each}
      </div>
    {/if}

    {#if item && mobile.current}
      <div class="mbar"><ImageActions {item} onremoved={removed} onnavigate={onclose} /></div>
    {/if}
  </div>

  {#if !mobile.current}
    <aside class="info" class:closed={!panel || !p}>
      <div class="inner">{@render details()}</div>
    </aside>
  {/if}
</div>

{#if mobile.current}
  <BottomSheet bind:open={sheet} title="Details" snaps={[0.55, 0.92]}>
    {@render details()}
  </BottomSheet>
{/if}

<style>
  .lb {
    position: fixed;
    inset: 0;
    z-index: var(--z-modal);
    display: flex;
    background: var(--bg);
    overscroll-behavior: contain;
  }
  .stage {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    position: relative;
  }
  .top {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    padding: var(--sp-2) var(--sp-3);
    padding-top: calc(var(--sp-2) + env(safe-area-inset-top));
  }
  .pos,
  .zoom {
    font-size: var(--fs-sm);
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }
  .zoom {
    padding: 1px 6px;
    border-radius: var(--r-sm);
    background: var(--surface-3);
  }
  .grow {
    flex: 1;
  }
  .view {
    flex: 1;
    min-height: 0;
    position: relative;
    overflow: hidden;
    touch-action: none;
    user-select: none;
    cursor: zoom-in;
  }
  .view.grab {
    cursor: grab;
  }
  .view.grab:active {
    cursor: grabbing;
  }
  .track {
    position: absolute;
    inset: 0;
  }
  .slide {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
  }
  .slide img {
    display: block;
    max-width: none;
    border-radius: var(--r-md);
    transform-origin: center;
    user-select: none;
    -webkit-user-drag: none;
  }
  img.alpha {
    background: var(--checker);
  }
  .albums {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .nav {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    width: 44px;
    height: 64px;
    border: 1px solid var(--hairline);
    border-radius: var(--r-md);
    background: var(--scrim);
    color: var(--text);
    cursor: pointer;
    display: grid;
    place-items: center;
    transition: opacity var(--dur) var(--ease);
  }
  .nav:disabled {
    opacity: 0;
    pointer-events: none;
  }
  .nav.l {
    left: var(--sp-3);
  }
  .nav.r {
    right: var(--sp-3);
  }
  .film {
    flex: none;
    display: flex;
    gap: 6px;
    padding: var(--sp-2) var(--sp-3);
    overflow-x: auto;
    overscroll-behavior: contain;
  }
  .th {
    flex: none;
    width: 44px;
    height: 56px;
    padding: 0;
    border: 0;
    border-radius: var(--r-sm);
    overflow: hidden;
    background: var(--surface-2);
    cursor: pointer;
    opacity: 0.55;
    outline: 2px solid transparent;
    outline-offset: 1px;
    transition:
      opacity var(--dur-fast) var(--ease),
      outline-color var(--dur-fast) var(--ease),
      transform var(--dur-fast) var(--ease);
  }
  .th:hover {
    opacity: 0.9;
  }
  .th:active {
    transform: scale(0.94);
  }
  .th.cur {
    opacity: 1;
    outline-color: var(--accent);
  }
  .th img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .mbar {
    flex: none;
    display: flex;
    justify-content: center;
    padding: 2px var(--sp-3) calc(var(--sp-2) + env(safe-area-inset-bottom));
  }
  .info {
    flex: none;
    width: 340px;
    border-left: 1px solid var(--hairline);
    background: var(--surface-1);
    overflow: hidden;
    transition:
      width var(--dur) var(--ease),
      opacity var(--dur) var(--ease);
  }
  .info.closed {
    width: 0;
    opacity: 0;
    border-left-color: transparent;
  }
  .inner {
    width: 340px;
    height: 100%;
    overflow-y: auto;
    padding: var(--sp-4);
  }
  .dl {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
  }
  .sh {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: var(--fs-sm);
    color: var(--text-muted);
    font-weight: 500;
    min-height: 28px;
  }
  .txt {
    font-size: var(--fs-sm);
    line-height: 1.5;
    word-break: break-word;
    max-height: 200px;
    overflow-y: auto;
    user-select: text;
  }
  .faint {
    color: var(--text-muted);
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--sp-3);
    font-size: var(--fs-sm);
    font-variant-numeric: tabular-nums;
  }
  .grid > div {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .grid span {
    display: block;
    font-size: var(--fs-xs);
    color: var(--text-faint);
  }
  .lora {
    font-size: var(--fs-sm);
  }
  .w {
    color: var(--text-muted);
    margin-left: 6px;
    font-variant-numeric: tabular-nums;
  }
  .flags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .flags span {
    font-size: var(--fs-xs);
    padding: 2px 8px;
    border-radius: var(--r-sm);
    background: var(--surface-3);
    color: var(--text-muted);
  }
  .date {
    font-size: var(--fs-xs);
    color: var(--text-faint);
  }
  .btns {
    display: flex;
    gap: var(--sp-2);
  }
  .edited {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--text-muted);
    font-size: var(--fs-sm);
  }
  .edited .icon {
    font-size: 16px;
  }
</style>
