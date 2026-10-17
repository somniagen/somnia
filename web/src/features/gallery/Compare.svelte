<script lang="ts">
  import { fade } from 'svelte/transition'
  import type { GalleryItem, GenParams } from '$lib/types'
  import { BottomSheet, IconButton, Segmented, clamp, mobile, reducedMotion } from '$lib/ui'

  let { a: first, b: second, onclose }: { a: GalleryItem; b: GalleryItem; onclose: () => void } = $props()

  const PAD = 12
  let swapped = $state(false)
  const a = $derived(swapped ? second : first)
  const b = $derived(swapped ? first : second)

  let mode = $state<'slider' | 'side'>('slider')
  let pos = $state(0.5)
  let z = $state(1)
  let tx = $state(0)
  let ty = $state(0)
  let anim = $state(false)
  let panel = $state(true)
  let sheet = $state(false)
  let stage = $state<HTMLDivElement>()
  let cw = $state(0)
  let ch = $state(0)
  const dur = $derived(reducedMotion.current ? 0 : 200)

  const side = $derived(mode === 'side')
  const gap = 8
  const pw = $derived(side ? Math.max(1, (cw - gap) / 2) : cw)
  const f = $derived(Math.max(0.0001, Math.min((pw - PAD * 2) / a.width, (ch - PAD * 2) / a.height)))
  const dw = $derived(a.width * f)
  const dh = $derived(a.height * f)
  const maxZ = $derived(Math.max(8, 4 / f))
  // divider position on screen, relative to the stage center
  const divX = $derived(tx + (pos * dw - dw / 2) * z)

  function pulse() {
    anim = true
    setTimeout(() => (anim = false), 260)
  }
  function reset(animate = false) {
    if (animate) pulse()
    z = 1
    tx = 0
    ty = 0
  }
  function limit() {
    const mw = Math.max(0, (dw * z - pw) / 2 + PAD)
    const mh = Math.max(0, (dh * z - ch) / 2 + PAD)
    tx = clamp(tx, -mw, mw)
    ty = clamp(ty, -mh, mh)
  }
  function zoomAt(px: number, py: number, nz: number) {
    nz = clamp(nz, 1, maxZ)
    const k = nz / z
    tx = px - (px - tx) * k
    ty = py - (py - ty) * k
    z = nz
    if (z < 1.001) return reset()
    limit()
  }
  // pointer position relative to the center of the pane it is over
  function rel(e: { clientX: number; clientY: number }) {
    const r = stage!.getBoundingClientRect()
    let x = e.clientX - r.left
    if (side && x > pw + gap / 2) x -= pw + gap
    return { x: x - pw / 2, y: e.clientY - r.top - r.height / 2 }
  }
  function setDivider(e: { clientX: number; clientY: number }) {
    const { x } = rel(e)
    pos = clamp(((x - tx) / z + dw / 2) / dw, 0, 1)
  }

  $effect(() => {
    const el = stage
    if (!el) return
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      anim = false
      const { x, y } = rel(e)
      zoomAt(x, y, z * Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0018)))
    }
    el.addEventListener('wheel', wheel, { passive: false })
    return () => el.removeEventListener('wheel', wheel)
  })

  const ptrs = new Map<number, { x: number; y: number }>()
  let drag: 'divider' | 'pan' | null = null
  let start = { x: 0, y: 0, tx: 0, ty: 0, moved: false }
  let pinch: { d: number; z: number; ux: number; uy: number } | null = null
  let lastTap = 0

  function down(e: PointerEvent) {
    if (e.pointerType === 'mouse' && e.button !== 0) return
    try {
      stage!.setPointerCapture(e.pointerId)
    } catch {}
    ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY })
    anim = false
    if (ptrs.size === 2) {
      const [p, q] = [...ptrs.values()]
      const m = rel({ clientX: (p.x + q.x) / 2, clientY: (p.y + q.y) / 2 })
      pinch = { d: Math.hypot(p.x - q.x, p.y - q.y) || 1, z, ux: (m.x - tx) / z, uy: (m.y - ty) / z }
      drag = null
      return
    }
    start = { x: e.clientX, y: e.clientY, tx, ty, moved: false }
    const onHandle = !!(e.target as HTMLElement).closest('.divider')
    drag = !side && (onHandle || z <= 1.01) ? 'divider' : 'pan'
    if (drag === 'divider' && !onHandle) setDivider(e)
  }
  function move(e: PointerEvent) {
    const pt = ptrs.get(e.pointerId)
    if (!pt) return
    pt.x = e.clientX
    pt.y = e.clientY
    if (pinch && ptrs.size >= 2) {
      const [p, q] = [...ptrs.values()]
      const m = rel({ clientX: (p.x + q.x) / 2, clientY: (p.y + q.y) / 2 })
      z = clamp((pinch.z * (Math.hypot(p.x - q.x, p.y - q.y) || 1)) / pinch.d, 1, maxZ)
      tx = m.x - pinch.ux * z
      ty = m.y - pinch.uy * z
      limit()
      return
    }
    if (Math.hypot(e.clientX - start.x, e.clientY - start.y) > 4) start.moved = true
    if (drag === 'divider') setDivider(e)
    else if (drag === 'pan' && z > 1.01) {
      tx = start.tx + e.clientX - start.x
      ty = start.ty + e.clientY - start.y
      limit()
    }
  }
  function up(e: PointerEvent) {
    if (!ptrs.delete(e.pointerId)) return
    if (pinch) {
      if (ptrs.size < 2) pinch = null
      if (z < 1.02) reset(true)
      drag = null
      return
    }
    drag = null
    if (start.moved || e.type !== 'pointerup') return
    const now = performance.now()
    if (now - lastTap < 320) {
      lastTap = 0
      pulse()
      const { x, y } = rel(e)
      if (z > 1.05) reset()
      else zoomAt(x, y, Math.max(2, 1 / f))
    } else lastTap = now
  }

  $effect(() => {
    const key = (e: KeyboardEvent) => {
      if (sheet) return
      if (e.key === 'Escape') {
        e.stopPropagation()
        onclose()
      } else if (e.key === 'ArrowLeft') pos = clamp(pos - 0.05, 0, 1)
      else if (e.key === 'ArrowRight') pos = clamp(pos + 0.05, 0, 1)
      else if (e.key === 'x') swapped = !swapped
      else if (e.key === 'm') mode = side ? 'slider' : 'side'
      else if (e.key === '0') reset(true)
      else if (e.key === 'i') panel = !panel
      else return
      e.preventDefault()
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
    void mode
    reset()
  })

  type Row = { label: string; a: string; b: string }
  type Tag = { t: string; k: 'same' | 'add' | 'del' }

  const short = (id: string | null | undefined) => (id ? (id.split(':').pop()?.replace(/^.*[\\/]/, '').replace(/\.(safetensors|ckpt|gguf|pt|pth)$/, '') ?? id) : '-')
  const norm = (t: string) => t.toLowerCase().replace(/_/g, ' ').replace(/\s+/g, ' ').trim()
  const split = (s: string | undefined) =>
    (s ?? '')
      .split(/,|\n/)
      .map((t) => t.trim())
      .filter(Boolean)

  function tagDiff(x: string | undefined, y: string | undefined): Tag[] | null {
    if ((x ?? '').trim() === (y ?? '').trim()) return null
    const ta = split(x)
    const tb = split(y)
    const sa = new Set(ta.map(norm))
    const sb = new Set(tb.map(norm))
    return [...tb.map((t) => ({ t, k: sa.has(norm(t)) ? ('same' as const) : ('add' as const) })), ...ta.filter((t) => !sb.has(norm(t))).map((t) => ({ t, k: 'del' as const }))]
  }

  function rows(x: GalleryItem, y: GalleryItem): Row[] {
    const out: Row[] = []
    const add = (label: string, va: unknown, vb: unknown) => {
      const sa = va === undefined || va === null || va === '' ? '-' : String(va)
      const sb = vb === undefined || vb === null || vb === '' ? '-' : String(vb)
      if (sa !== sb) out.push({ label, a: sa, b: sb })
    }
    add('Size', `${x.width}x${x.height}`, `${y.width}x${y.height}`)
    add('Seed', x.seed, y.seed)
    const pa: Partial<GenParams> = x.params ?? {}
    const pb: Partial<GenParams> = y.params ?? {}
    const loras = (p: Partial<GenParams>) => (p.loras ?? []).map((l) => `${short(l.id)} ${l.weight}`).join(', ')
    const sp = (p: Partial<GenParams>) => (p.secondPass?.enabled ? `${p.secondPass.scale}x / ${p.secondPass.denoise}` : 'Off')
    const up = (p: Partial<GenParams>) => (p.upscale?.enabled ? `${p.upscale.scale}x ${short(p.upscale.upscaler)}` : 'Off')
    const det = (p: Partial<GenParams>) => (p.detailers ?? []).filter((d) => d.enabled).length || 'Off'
    add('Model', short(pa.model), short(pb.model))
    add('Steps', pa.steps, pb.steps)
    add('CFG', pa.cfg, pb.cfg)
    add('Sampler', pa.sampler, pb.sampler)
    add('Scheduler', pa.scheduler, pb.scheduler)
    add('Clip skip', pa.clipSkip, pb.clipSkip)
    add('LoRAs', loras(pa), loras(pb))
    add('PAG', pa.pag?.enabled ? pa.pag.scale : 'Off', pb.pag?.enabled ? pb.pag.scale : 'Off')
    add('Second pass', sp(pa), sp(pb))
    add('Detailers', det(pa), det(pb))
    add('Upscale', up(pa), up(pb))
    add('Denoise', pa.init?.denoise, pb.init?.denoise)
    add('Edited in', x.editedWith?.name, y.editedWith?.name)
    return out
  }

  const diff = $derived(rows(a, b))
  const pDiff = $derived(tagDiff(a.params?.prompt, b.params?.prompt))
  const nDiff = $derived(tagDiff(a.params?.negative, b.params?.negative))
  const same = $derived(!diff.length && !pDiff && !nDiff)
  const tf = $derived(`transform: translate3d(${tx}px, ${ty}px, 0) scale(${z}); transition: ${anim ? `transform ${dur + 40}ms var(--ease)` : 'none'}`)
</script>

{#snippet tags(list: Tag[])}
  <div class="tags">
    {#each list as t, i (i)}<span class={t.k}>{t.t}</span>{/each}
  </div>
{/snippet}

{#snippet details()}
  <div class="dl">
    <div class="ab"><span class="lbl">A</span><span class="icon">arrow_forward</span><span class="lbl">B</span></div>
    {#if same}
      <div class="same"><span class="icon">check</span>Same params</div>
    {/if}
    {#if pDiff}
      <div class="sec"><div class="sh">Prompt</div>{@render tags(pDiff)}</div>
    {/if}
    {#if nDiff}
      <div class="sec"><div class="sh">Negative</div>{@render tags(nDiff)}</div>
    {/if}
    {#if diff.length}
      <div class="rows">
        {#each diff as r (r.label)}
          <div class="row">
            <span class="k">{r.label}</span>
            <span class="v del">{r.a}</span>
            <span class="icon arr">arrow_forward</span>
            <span class="v add">{r.b}</span>
          </div>
        {/each}
      </div>
    {/if}
  </div>
{/snippet}

{#snippet img(it: GalleryItem)}
  <img src={it.url} alt="" draggable="false" class:alpha={it.alpha} />
{/snippet}

<div class="cmp" transition:fade={{ duration: dur }} role="dialog" aria-modal="true" aria-label="Compare images">
  <div class="main">
    <div class="top">
      <Segmented
        items={[
          { value: 'slider' as const, label: 'Slider', icon: 'compare' },
          { value: 'side' as const, label: 'Side by side', icon: 'view_column_2' },
        ]}
        bind:value={mode}
        size="sm"
        iconOnly={mobile.current}
      />
      <IconButton icon="swap_horiz" label="Swap (X)" onclick={() => (swapped = !swapped)} />
      {#if z > 1.01}<IconButton icon="zoom_out_map" label="Fit (0)" onclick={() => reset(true)} />{/if}
      <span class="grow"></span>
      <IconButton
        icon={mobile.current ? 'info' : panel ? 'right_panel_close' : 'right_panel_open'}
        label="Differences"
        active={mobile.current ? sheet : panel}
        onclick={() => (mobile.current ? (sheet = !sheet) : (panel = !panel))}
      />
      <IconButton icon="close" label="Close" onclick={onclose} />
    </div>

    <div
      class="stage"
      class:side
      class:grab={z > 1.01}
      role="presentation"
      bind:this={stage}
      bind:clientWidth={cw}
      bind:clientHeight={ch}
      onpointerdown={down}
      onpointermove={move}
      onpointerup={up}
      onpointercancel={up}
    >
      {#if side}
        {#each [a, b] as it, k (k)}
          <div class="pane">
            <div class="frame" style="width: {dw}px; height: {dh}px; {tf}">{@render img(it)}</div>
            <span class="tag">{k ? 'B' : 'A'}</span>
          </div>
        {/each}
      {:else}
        <div class="pane">
          <div class="frame" style="width: {dw}px; height: {dh}px; {tf}">
            {@render img(a)}
            <div class="clip" style="clip-path: inset(0 0 0 {pos * 100}%)">{@render img(b)}</div>
          </div>
          <div class="divider" style="transform: translateX({divX}px)">
            <span class="knob"><span class="icon">unfold_more</span></span>
          </div>
          <span class="tag">A</span>
          <span class="tag r">B</span>
        </div>
      {/if}
    </div>
  </div>

  {#if !mobile.current}
    <aside class="info" class:closed={!panel}>
      <div class="inner">{@render details()}</div>
    </aside>
  {/if}
</div>

{#if mobile.current}
  <BottomSheet bind:open={sheet} title="Differences" snaps={[0.5, 0.9]}>
    {@render details()}
  </BottomSheet>
{/if}

<style>
  .cmp {
    position: fixed;
    inset: 0;
    z-index: var(--z-modal);
    display: flex;
    background: var(--bg);
    overscroll-behavior: contain;
  }
  .main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .top {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    padding: var(--sp-2) var(--sp-3);
    padding-top: calc(var(--sp-2) + env(safe-area-inset-top));
  }
  .grow {
    flex: 1;
  }
  .stage {
    flex: 1;
    min-height: 0;
    position: relative;
    display: flex;
    gap: 8px;
    overflow: hidden;
    touch-action: none;
    user-select: none;
    cursor: ew-resize;
    padding-bottom: env(safe-area-inset-bottom);
  }
  .stage.side,
  .stage.grab {
    cursor: grab;
  }
  .stage.side:not(.grab) {
    cursor: zoom-in;
  }
  .pane {
    position: relative;
    flex: 1;
    min-width: 0;
    display: grid;
    place-items: center;
    overflow: hidden;
  }
  .side .pane {
    border-radius: var(--r-md);
    background: var(--surface-1);
  }
  .frame {
    position: relative;
    flex: none;
    transform-origin: center;
  }
  .frame img,
  .clip {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }
  .frame img {
    display: block;
    object-fit: contain;
    -webkit-user-drag: none;
  }
  img.alpha {
    background: var(--checker);
  }
  .divider {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 50%;
    width: 2px;
    margin-left: -1px;
    background: var(--accent);
    box-shadow: 0 0 10px var(--accent-glow);
    cursor: ew-resize;
  }
  .divider::before {
    content: '';
    position: absolute;
    inset: 0 -12px;
  }
  .knob {
    position: absolute;
    top: 50%;
    left: 50%;
    display: grid;
    place-items: center;
    width: 32px;
    height: 32px;
    transform: translate(-50%, -50%) rotate(90deg);
    border-radius: var(--r-md);
    background: var(--grad-accent);
    box-shadow: var(--sheen-strong), var(--shadow-2);
    color: var(--text-on-accent);
  }
  .tag {
    position: absolute;
    top: var(--sp-2);
    left: var(--sp-2);
    padding: 1px 8px;
    border: 1px solid var(--hairline);
    border-radius: var(--r-sm);
    background: var(--scrim);
    font-size: var(--fs-xs);
    font-weight: 600;
    pointer-events: none;
  }
  .tag.r {
    left: auto;
    right: var(--sp-2);
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
    gap: var(--sp-4);
  }
  .ab {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    color: var(--text-muted);
  }
  .ab .icon {
    font-size: 16px;
  }
  .lbl {
    padding: 0 8px;
    border-radius: var(--r-sm);
    background: var(--surface-3);
    color: var(--text);
    font-size: var(--fs-xs);
    font-weight: 600;
  }
  .same {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--success);
    font-size: var(--fs-sm);
  }
  .same .icon {
    font-size: 18px;
  }
  .sh {
    margin-bottom: 6px;
    font-size: var(--fs-sm);
    font-weight: 500;
    color: var(--text-muted);
  }
  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    font-size: var(--fs-xs);
    user-select: text;
  }
  .tags span {
    padding: 1px 6px;
    border-radius: var(--r-sm);
    background: var(--surface-2);
    color: var(--text-faint);
  }
  .tags .add {
    background: var(--success-soft);
    color: var(--success);
  }
  .tags .del {
    background: var(--danger-soft);
    color: var(--danger);
    text-decoration: line-through;
  }
  .rows {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
  }
  .row {
    display: grid;
    grid-template-columns: 84px minmax(0, 1fr) auto minmax(0, 1fr);
    align-items: baseline;
    gap: 6px;
    font-size: var(--fs-sm);
    font-variant-numeric: tabular-nums;
  }
  .k {
    font-size: var(--fs-xs);
    color: var(--text-faint);
  }
  .v {
    overflow-wrap: anywhere;
  }
  .v.del {
    color: var(--danger);
  }
  .v.add {
    color: var(--success);
  }
  .arr {
    font-size: 14px;
    color: var(--text-faint);
  }
</style>
