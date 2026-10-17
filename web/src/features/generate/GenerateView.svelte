<script lang="ts">
  import { MediaQuery } from 'svelte/reactivity'
  import Lightbox from '$features/gallery/Lightbox.svelte'
  import QueuePanel from '$features/queue/QueuePanel.svelte'
  import Recent from '$features/queue/Recent.svelte'
  import { boot } from '$features/shell/boot.svelte'
  import { api } from '$lib/api'
  import { live } from '$lib/live.svelte'
  import { session } from '$lib/session.svelte'
  import type { GalleryItem } from '$lib/types'
  import { Button, EmptyState, IconButton, Kbd, Menu, Sheet, Skeleton, mobile, reducedMotion, toast, type MenuItem } from '$lib/ui'
  import { addFile } from './actions.svelte'
  import ParamsPanel from './ParamsPanel.svelte'
  import Preview from './Preview.svelte'

  const wide = new MediaQuery('(min-width: 1240px)')

  let collapsed = $state(read('somnia.panel.collapsed') === '1')
  let queueOpen = $state(false)
  let shown = $state<GalleryItem | null>(null)
  let follow = $state(true)
  let busy = $state(false)
  let dragging = $state(false)
  let lightbox = $state<number | null>(null)
  let scroller = $state<HTMLDivElement>()
  let pv = $state(0)
  let raf = 0

  function read(k: string) {
    try {
      return localStorage.getItem(k)
    } catch {
      return null
    }
  }
  function toggleCollapsed() {
    collapsed = !collapsed
    try {
      localStorage.setItem('somnia.panel.collapsed', collapsed ? '1' : '0')
    } catch {}
  }

  const RANGE = 220

  function onscroll() {
    if (raf) return
    raf = requestAnimationFrame(() => {
      raf = 0
      pv = Math.min(1, Math.max(0, (scroller?.scrollTop ?? 0) / RANGE))
    })
  }
  function hdrClick(e: MouseEvent) {
    if (pv < 0.4) return
    e.stopPropagation()
    e.preventDefault()
    const el = scroller
    if (!el) return
    const from = el.scrollTop
    const t0 = performance.now()
    const D = reducedMotion.current ? 1 : 280
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / D)
      el.scrollTop = from * (1 - (1 - (1 - k) ** 3))
      if (k < 1) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  }

  const latest = $derived(live.recent[0] ?? null)
  const active = $derived(live.queue.filter((j) => j.status === 'queued' || j.status === 'running').length)
  const running = $derived(!!live.running || !!live.current)
  const ready = $derived(boot.state === 'ready' && !!session.params)

  $effect(() => {
    const id = latest?.id
    if (id) shown = live.recent[0]
    else shown = null
  })
  $effect(() => {
    void live.current?.jobId
    follow = true
  })

  const repeating = $derived(live.queue.some((j) => j.repeat))

  async function generate(count?: number, repeat = false) {
    if (busy || !ready) return
    if (!session.params?.model) return toast.error('Pick a model first')
    busy = true
    try {
      await session.generate(count, repeat)
      follow = true
      if (count && count > 1) toast.success(`Queued ${count}`)
    } catch (e) {
      toast.error('Could not queue', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      busy = false
    }
  }
  async function stopRepeat() {
    try {
      await api.stopRepeat()
      toast.success('Stops after this one')
    } catch (e) {
      toast.error('Could not stop', { description: e instanceof Error ? e.message : String(e) })
    }
  }
  const bulk = $derived<MenuItem[]>([
    ...[4, 10, 25, 50].map((n) => ({ label: `Queue ${n}`, icon: 'playlist_add', onselect: () => generate(n) })),
    { separator: true },
    repeating
      ? { label: 'Stop repeating', icon: 'stop_circle', danger: true, onselect: stopRepeat }
      : { label: 'Until stopped', icon: 'all_inclusive', onselect: () => generate(1, true) },
  ])

  async function cancel() {
    const j = live.running
    if (!j) return
    try {
      await api.cancel(j.id)
    } catch (e) {
      toast.error('Could not cancel', { description: e instanceof Error ? e.message : String(e) })
    }
  }
  function pick(it: GalleryItem) {
    shown = it
    follow = false
  }
  function removed() {
    shown = live.recent[0] ?? null
  }

  $effect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault()
        generate()
      }
    }
    let depth = 0
    const hasFiles = (e: DragEvent) => !!e.dataTransfer?.types.includes('Files')
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return
      depth++
      dragging = true
    }
    const leave = (e: DragEvent) => {
      if (!hasFiles(e)) return
      depth = Math.max(0, depth - 1)
      if (!depth) dragging = false
    }
    const over = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault()
    }
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth = 0
      dragging = false
      const f = Array.from(e.dataTransfer?.files ?? []).find((x) => x.type.startsWith('image/'))
      if (f) addFile(f)
    }
    const paste = (e: ClipboardEvent) => {
      if ((e.target as HTMLElement | null)?.closest('input, textarea, [contenteditable="true"]')) return
      const f = Array.from(e.clipboardData?.files ?? []).find((x) => x.type.startsWith('image/'))
      if (f) {
        e.preventDefault()
        addFile(f)
      }
    }
    addEventListener('keydown', key)
    addEventListener('dragenter', enter)
    addEventListener('dragleave', leave)
    addEventListener('dragover', over)
    addEventListener('drop', drop)
    addEventListener('paste', paste)
    return () => {
      removeEventListener('keydown', key)
      removeEventListener('dragenter', enter)
      removeEventListener('dragleave', leave)
      removeEventListener('dragover', over)
      removeEventListener('drop', drop)
      removeEventListener('paste', paste)
    }
  })
</script>

{#snippet genButtons()}
  <div class="gb">
    {#if running}
      <Button variant="danger" icon="stop" onclick={cancel} aria-label="Cancel current">Cancel</Button>
    {/if}
    <Button variant="primary" icon="auto_awesome" full loading={busy} disabled={!ready} onclick={() => generate()} class="go">
      Generate
      {#if active > 0}<span class="badge">{active}</span>{/if}
      {#if !mobile.current}<Kbd>Ctrl Enter</Kbd>{/if}
    </Button>
    {@render bulkMenu()}
  </div>
{/snippet}

{#snippet bulkMenu()}
  <Menu items={bulk} placement="top-end" label="Queue many">
    {#snippet trigger({ toggle, open })}
      <IconButton
        icon={repeating ? 'all_inclusive' : 'playlist_add'}
        label={repeating ? 'Repeating' : 'Queue many'}
        variant="default"
        class="bulk"
        active={open || repeating}
        disabled={!ready}
        onclick={toggle}
      />
    {/snippet}
  </Menu>
{/snippet}

{#snippet queueBody(recent: boolean)}
  <div class="qs">
    <QueuePanel title={!recent} />
    {#if recent && live.recent.length}
      <div class="rh">Recent</div>
      <Recent grid selectedId={shown?.id} onselect={(i) => (pick(i), (queueOpen = false))} />
    {/if}
  </div>
{/snippet}

{#snippet panel()}
  {#if boot.state === 'error'}
    <EmptyState icon="cloud_off" title="Could not load" description={boot.error}>
      <Button icon="refresh" onclick={() => boot.load()}>Retry</Button>
    </EmptyState>
  {:else if !ready}
    <div class="skel">
      <Skeleton height="34px" />
      <Skeleton height="34px" />
      <Skeleton height="120px" />
      <Skeleton height="80px" />
      <Skeleton height="34px" />
      <Skeleton height="34px" />
    </div>
  {:else}
    <ParamsPanel />
  {/if}
{/snippet}

{#if mobile.current}
  <div class="gen m">
    <div class="hdr" style="--p: {pv}" onclickcapture={hdrClick} role="presentation">
      <div class="pv">
        <Preview item={shown} live={follow} onopen={() => (lightbox = Math.max(0, live.recent.findIndex((i) => i.id === shown?.id)))} onbacktolive={() => (follow = true)} />
        <button type="button" class="qbtn" onclick={() => (queueOpen = true)} aria-label="Queue">
          <span class="icon">queue</span>
          {#if active}<span class="qn">{active}</span>{/if}
        </button>
      </div>
    </div>
    <div class="mscroll" bind:this={scroller} {onscroll}>{@render panel()}</div>
    <div class="mfoot">{@render genButtons()}</div>
  </div>
{:else}
  <div class="gen">
    <aside class="panel" class:collapsed>
      <div class="scroll">{@render panel()}</div>
      <div class="foot">{@render genButtons()}</div>
    </aside>
    <section class="main">
      <div class="tools">
        <IconButton
          icon={collapsed ? 'left_panel_open' : 'left_panel_close'}
          label={collapsed ? 'Show parameters' : 'Hide parameters'}
          variant="default"
          onclick={toggleCollapsed}
        />
        {#if collapsed}
          <Button variant="primary" icon="auto_awesome" loading={busy} disabled={!ready} onclick={() => generate()}>
            Generate{#if active > 0}<span class="badge">{active}</span>{/if}
          </Button>
          {@render bulkMenu()}
        {/if}
        <span class="grow"></span>
        {#if !wide.current}
          <button type="button" class="qbtn d" onclick={() => (queueOpen = true)} aria-label="Queue">
            <span class="icon">queue</span>
            {#if active}<span class="qn">{active}</span>{/if}
          </button>
        {/if}
      </div>
      <div class="pv">
        <Preview item={shown} live={follow} onopen={() => (lightbox = Math.max(0, live.recent.findIndex((i) => i.id === shown?.id)))} onbacktolive={() => (follow = true)} />
      </div>
      <div class="rec">
        <Recent selectedId={shown?.id} onselect={pick} />
      </div>
    </section>
    {#if wide.current}
      <aside class="queue">{@render queueBody(false)}</aside>
    {/if}
  </div>
{/if}

<Sheet bind:open={queueOpen} title="Queue" width={420} snaps={[0.55, 0.92]}>
  {@render queueBody(true)}
</Sheet>

{#if lightbox !== null && live.recent.length}
  <Lightbox items={live.recent} bind:index={lightbox} onclose={() => (lightbox = null)} onremoved={removed} />
{/if}

{#if dragging}
  <div class="drop">
    <div class="dbox"><span class="icon">add_photo_alternate</span>Drop to use as input</div>
  </div>
{/if}

<style>
  .gen {
    display: flex;
    height: 100%;
    min-height: 0;
  }
  .panel {
    flex: none;
    width: 390px;
    display: flex;
    flex-direction: column;
    min-height: 0;
    border-right: 1px solid var(--hairline);
    background: var(--bg);
    transition:
      width var(--dur) var(--ease),
      margin var(--dur) var(--ease),
      opacity var(--dur) var(--ease);
    overflow: hidden;
  }
  .panel.collapsed {
    width: 0;
    opacity: 0;
    border-right-color: transparent;
    pointer-events: none;
  }
  .scroll {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: var(--sp-4);
    width: 390px;
  }
  .foot {
    flex: none;
    width: 390px;
    padding: var(--sp-3) var(--sp-4);
    border-top: 1px solid var(--hairline);
    background: var(--bg);
  }
  .gb {
    display: flex;
    gap: var(--sp-2);
  }
  .gb :global(.go) {
    flex: 1;
  }
  .gb :global(.go:not(:disabled)) {
    height: 42px;
    font-weight: 600;
  }
  .gb :global(.bulk) {
    height: 42px;
    width: 42px;
  }
  .badge {
    min-width: 20px;
    padding: 0 6px;
    margin-left: 4px;
    border-radius: var(--r-sm);
    background: var(--text-on-accent);
    color: var(--accent-strong);
    font-size: var(--fs-xs);
    line-height: 20px;
    text-align: center;
    font-variant-numeric: tabular-nums;
  }
  .main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    position: relative;
  }
  .tools {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    padding: var(--sp-3) var(--sp-3) 0;
    min-height: 44px;
  }
  .grow {
    flex: 1;
  }
  .pv {
    flex: 1;
    min-height: 0;
    position: relative;
  }
  .rec {
    flex: none;
    padding: 0 var(--sp-4) var(--sp-3);
    min-height: 0;
  }
  .queue {
    flex: none;
    width: 290px;
    border-left: 1px solid var(--hairline);
    padding: var(--sp-3);
    overflow-y: auto;
  }
  .qs {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
  }
  .rh {
    font-weight: 600;
    margin-top: var(--sp-2);
  }
  .qbtn {
    position: relative;
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    border-radius: var(--r-md);
    border: 1px solid var(--hairline);
    background: var(--scrim);
    color: var(--text);
    cursor: pointer;
    backdrop-filter: blur(6px);
    transition: transform var(--dur-fast) var(--ease);
  }
  .qbtn:active {
    transform: scale(0.94);
  }
  .qbtn.d {
    background: var(--surface-3);
  }
  .qn {
    position: absolute;
    top: -6px;
    right: -6px;
    min-width: 18px;
    padding: 0 5px;
    border-radius: var(--r-sm);
    background: var(--accent-strong);
    color: var(--text-on-accent);
    font-size: 11px;
    line-height: 18px;
    font-weight: 600;
    text-align: center;
  }
  .skel {
    display: flex;
    flex-direction: column;
    gap: var(--sp-4);
  }
  .drop {
    position: fixed;
    inset: 0;
    z-index: var(--z-modal);
    display: grid;
    place-items: center;
    background: var(--scrim);
    pointer-events: none;
  }
  .dbox {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    padding: var(--sp-5) var(--sp-6);
    border: 1px dashed var(--accent);
    border-radius: var(--r-lg);
    background: var(--surface-2);
    font-size: var(--fs-lg);
  }
  .gen.m {
    flex-direction: column;
  }
  .hdr {
    --full: min(44dvh, 105vw);
    --compact: 76px;
    flex: none;
    height: calc(var(--full) + (var(--compact) - var(--full)) * var(--p, 0));
    overflow: hidden;
    border-bottom: 1px solid var(--hairline);
    background: var(--bg);
    cursor: default;
  }
  .m .pv {
    height: 100%;
  }
  .m .qbtn {
    position: absolute;
    top: var(--sp-3);
    right: var(--sp-3);
    opacity: clamp(0.5, calc(1 - var(--p, 0)), 1);
  }
  .mscroll {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overflow-anchor: none;
    overscroll-behavior: contain;
    padding: var(--sp-4);
  }
  .mfoot {
    flex: none;
    padding: var(--sp-2) var(--sp-4);
    border-top: 1px solid var(--hairline);
    background: var(--bg);
  }
</style>
