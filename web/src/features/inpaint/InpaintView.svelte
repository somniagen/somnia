<script lang="ts">
  import OpenInEditor from '$features/editors/OpenInEditor.svelte'
  import ModelSelect from '$features/models/ModelSelect.svelte'
  import PromptEditor from '$features/prompt/PromptEditor.svelte'
  import PromptLibrary from '$features/prompt/PromptLibrary.svelte'
  import SendTo from '$features/prompt/SendTo.svelte'
  import { boot } from '$features/shell/boot.svelte'
  import Logo from '$features/shell/Logo.svelte'
  import { live } from '$lib/live.svelte'
  import { session } from '$lib/session.svelte'
  import type { GalleryItem, SavedPrompt } from '$lib/types'
  import { Button, Dropzone, EmptyState, Field, IconButton, ImageTile, NumberField, SeedField, Segmented, Sheet, Slider, Spinner, Toggle, mobile, toast, tooltip } from '$lib/ui'
  import Inpainter from './Inpainter.svelte'
  import type { Rect } from './mask'
  import { studio } from './studio.svelte'

  let editor = $state<ReturnType<typeof Inpainter>>()
  let bounds = $state<Rect | null>(null)
  let busy = $state(false)
  let compare = $state(false)
  let lastSeed = $state(Math.floor(Math.random() * 4294967295))
  let library = $state(false)

  const b = $derived(studio.base)
  const o = $derived(studio.opts)
  const fam = $derived(studio.family)
  const p = $derived(session.byFamily[fam] ?? null)
  const info = $derived(session.presets?.families[fam] ?? null)
  const original = $derived(studio.versions[0] ?? null)
  const fills = [
    { value: 'original' as const, label: 'Original' },
    { value: 'noise' as const, label: 'Noise' },
    { value: 'blur' as const, label: 'Blur' },
  ]
  const families = [
    { value: 'illustrious' as const, label: 'Illustrious' },
    { value: 'anima' as const, label: 'Anima' },
  ]

  // the part of the image the sampler actually sees (matches backend masked_inpaint)
  const region = $derived.by((): Rect | null => {
    if (!b || !bounds) return null
    if (!o.onlyMasked) return { x0: 0, y0: 0, x1: b.width, y1: b.height }
    const pad = o.padding
    return {
      x0: Math.max(0, bounds.x0 - pad),
      y0: Math.max(0, bounds.y0 - pad),
      x1: Math.min(b.width, bounds.x1 + pad),
      y1: Math.min(b.height, bounds.y1 + pad),
    }
  })
  const renderSize = $derived.by(() => {
    if (!region) return null
    const bw = region.x1 - region.x0
    const bh = region.y1 - region.y0
    if (!o.onlyMasked) return [bw, bh]
    const s = 1024 / Math.sqrt(bw * bh)
    return [Math.max(64, Math.round((bw * s) / 8) * 8), Math.max(64, Math.round((bh * s) / 8) * 8)]
  })

  const mine = $derived(studio.pending.find((j) => j.id === live.current?.jobId) ?? null)
  const livePreview = $derived(mine && live.preview ? live.preview : null)
  const queued = $derived(studio.pending.length)

  async function generate() {
    if (busy || !editor || !b) return
    if (!p?.model) return toast.error('Pick a model first')
    busy = true
    try {
      const maskId = await editor.exportMask()
      if (!maskId) return
      await studio.queue(maskId, region)
    } catch (e) {
      toast.error('Could not queue', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      busy = false
    }
  }

  function loadPrompt(s: SavedPrompt) {
    studio.positive = $state.snapshot(s.positive)
    studio.negative = $state.snapshot(s.negative)
    library = false
  }

  async function pickFile(f: File) {
    try {
      await studio.openFile(f)
    } catch (e) {
      toast.error('Upload failed', { description: e instanceof Error ? e.message : String(e) })
    }
  }
  async function pick(it: GalleryItem) {
    try {
      await studio.open(it)
    } catch (e) {
      toast.error('Could not open image', { description: e instanceof Error ? e.message : String(e) })
    }
  }

  $effect(() => {
    const key = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') (e.preventDefault(), generate())
        return
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault()
        generate()
      } else if (e.key === '\\' && !e.repeat) compare = true
    }
    const keyup = (e: KeyboardEvent) => {
      if (e.key === '\\') compare = false
    }
    addEventListener('keydown', key)
    addEventListener('keyup', keyup)
    return () => {
      removeEventListener('keydown', key)
      removeEventListener('keyup', keyup)
    }
  })

  const pctFmt = (v: number) => `${Math.round(v * 100)}%`
  const pxFmt = (v: number) => `${v}px`
</script>

{#snippet settings()}
  <section>
    <Segmented items={families} bind:value={studio.family} full size="sm" />
    {#if p}<ModelSelect kind="checkpoint" family={fam} bind:value={p.model} />{/if}
    {#key fam}
      <div class="phead">
        <span class="lbl">Prompt</span>
        <span class="pact">
          <SendTo from="inpaint" />
          <IconButton icon="bookmarks" label="Saved prompts" size="sm" onclick={() => (library = true)} />
        </span>
      </div>
      <PromptEditor kind="positive" family={fam} loras={p?.loras} placeholder="What goes in the masked area" bind:segments={studio.positive} />
      <PromptEditor kind="negative" family={fam} placeholder="Negative prompt" bind:segments={studio.negative} />
    {/key}
  </section>
  <section>
    <Field label="Denoise" info="How much the masked area changes. 0.4 to 0.7 keeps the composition, 0.9+ replaces it.">
      {#snippet children(id)}
        <Slider {id} label="Denoise" bind:value={o.denoise} min={0} max={1} step={0.01} defaultValue={0.6} editable />
      {/snippet}
    </Field>
    <Field label="Masked content" info="What fills the masked area before denoising. Noise helps when replacing things.">
      {#snippet children()}
        <Segmented items={fills} bind:value={o.fill} full size="sm" />
      {/snippet}
    </Field>
    <Toggle bind:checked={o.onlyMasked} label="Only masked area" size="sm" />
    {#if o.onlyMasked}
      <Field label="Context" info="Pixels around the mask rendered with it. More context blends better, less gives more detail.">
        {#snippet children(id)}
          <Slider {id} label="Context" bind:value={o.padding} min={0} max={256} step={4} defaultValue={32} editable format={pxFmt} />
        {/snippet}
      </Field>
    {/if}
    <Field label="Blend" info="Blur radius used to merge the result into the image.">
      {#snippet children(id)}
        <Slider {id} label="Blend" bind:value={o.maskBlur} min={0} max={64} step={1} defaultValue={4} editable format={pxFmt} />
      {/snippet}
    </Field>
    {#if region && renderSize}
      <button class="region" onclick={() => region && editor?.focusRect(region)} use:tooltip={'Zoom to the render area'}>
        <span class="icon">crop_free</span>
        <span>{region.x1 - region.x0} x {region.y1 - region.y0}</span>
        {#if o.onlyMasked}<span class="dim">renders at {renderSize[0]} x {renderSize[1]}</span>{/if}
      </button>
    {/if}
  </section>
  <section>
    <div class="two">
      <Field label="Steps">
        {#snippet children(id)}
          <NumberField {id} value={o.steps ?? p?.steps ?? 28} onchange={(v: number) => (o.steps = v)} min={1} max={80} step={1} />
        {/snippet}
      </Field>
      <Field label="CFG">
        {#snippet children(id)}
          <NumberField {id} value={o.cfg ?? p?.cfg ?? 5} onchange={(v: number) => (o.cfg = v)} min={1} max={20} step={0.5} />
        {/snippet}
      </Field>
    </div>
    <Field label="Seed" info="Unlocked picks a new seed every run.">
      {#snippet children(id)}
        <SeedField
          {id}
          bind:value={() => (o.seed >= 0 ? o.seed : lastSeed), (v) => ((lastSeed = v), (o.seed = v))}
          bind:locked={() => o.seed >= 0, (l) => (o.seed = l ? lastSeed : -1)}
        />
      {/snippet}
    </Field>
    <div class="two">
      <Field label="Runs" info="Queued variations, each filed into this stack.">
        {#snippet children(id)}<NumberField {id} bind:value={o.count} min={1} max={16} step={1} icon="playlist_add" />{/snippet}
      </Field>
      <div class="det">
        <Toggle bind:checked={o.detailers} label="Detailers" size="sm" />
      </div>
    </div>
  </section>
{/snippet}

{#snippet bar()}
  {#if original && b && original.url !== b.item?.url}
    <button
      class="cmp"
      class:on={compare}
      onpointerdown={() => (compare = true)}
      onpointerup={() => (compare = false)}
      onpointerleave={() => (compare = false)}
      use:tooltip={'Hold to see the original (\\)'}
    >
      <span class="icon">compare</span>
    </button>
  {/if}
  {#if b}<OpenInEditor url={b.url} galleryId={b.item?.id} compact={mobile.current} />{/if}
  {#if queued}
    <IconButton icon="stop_circle" label="Cancel all inpaints" variant="danger" onclick={() => studio.cancelAll()} />
  {/if}
  <IconButton icon="close" label="Close image" onclick={() => studio.close()} />
  <Button variant="primary" icon="brush" loading={busy} disabled={!p?.model} onclick={generate}>
    {queued ? `Inpaint (${queued})` : 'Inpaint'}
  </Button>
{/snippet}

{#snippet stage(scale: number)}
  {#if compare && original}
    <img class="over" src={original.url} alt="" draggable="false" />
  {/if}
  {#if livePreview && mine}
    {@const r = mine.region}
    {#if r}
      <img class="live" src={livePreview} alt="" style="left: {r.x0}px; top: {r.y0}px; width: {r.x1 - r.x0}px; height: {r.y1 - r.y0}px" />
    {/if}
  {/if}
  {#if region && o.onlyMasked && !compare}
    <div
      class="area"
      class:busy={!!mine}
      style="left: {region.x0}px; top: {region.y0}px; width: {region.x1 - region.x0}px; height: {region.y1 - region.y0}px; --s: {1 / scale}"
    ></div>
  {/if}
{/snippet}

<div class="iv">
  {#if b}
    <div class="ed">
      {#key `${b.width}x${b.height}`}
        <Inpainter
          bind:this={editor}
          embedded
          imageId={b.uploadId ?? ''}
          imageUrl={b.url}
          width={b.width}
          height={b.height}
          {settings}
          {bar}
          {stage}
          onbounds={(r) => (bounds = r)}
        />
      {/key}
    </div>
    {#if studio.versions.length || studio.pending.length}
      <div class="strip" aria-label="Versions">
        {#each studio.versions as v, i (v.id)}
          <button class="ver" class:on={b.item?.id === v.id} onclick={() => studio.use(v)} use:tooltip={i === 0 ? 'Original' : `Version ${i}`}>
            <img src={v.thumbUrl} alt="" />
            <span class="n">{i === 0 ? 'Orig' : i}</span>
          </button>
        {/each}
        {#each studio.pending as j (j.id)}
          <div class="ver wait" class:run={live.current?.jobId === j.id}>
            {#if live.current?.jobId === j.id && livePreview}
              <img src={livePreview} alt="" />
            {:else}
              <Spinner size={16} />
            {/if}
            <button class="x" aria-label="Cancel" use:tooltip={'Cancel'} onclick={() => studio.cancel(j.id)}>
              <span class="icon">close</span>
            </button>
          </div>
        {/each}
      </div>
    {/if}
  {:else}
    <div class="empty">
      <header>
        {#if mobile.current}<Logo size={22} />{/if}
        <h1>Inpaint</h1>
      </header>
      <div class="pick">
        {#if boot.state !== 'ready' || studio.loading}
          <div class="wait"><Spinner size={20} /></div>
        {:else}
          <Dropzone title="Drop an image" hint="or paste, or pick a recent one below" icon="add_photo_alternate" paste onfiles={(f) => pickFile(f[0])} />
          {#if live.recent.length}
            <div class="recent">
              {#each live.recent.slice(0, 12) as it (it.id)}
                <ImageTile src={it.thumbUrl} aspect={1} onclick={() => pick(it)} alt="Recent image" />
              {/each}
            </div>
          {:else}
            <EmptyState compact icon="photo_library" title="No images yet">
              <Button onclick={() => (location.hash = '#/gallery')}>Open gallery</Button>
            </EmptyState>
          {/if}
        {/if}
      </div>
    </div>
  {/if}
</div>

<Sheet bind:open={library} title="Saved prompts" width={520}>
  <PromptLibrary onload={loadPrompt} />
</Sheet>

<style>
  .iv {
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .ed {
    position: relative;
    flex: 1;
    min-height: 0;
  }
  .phead {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .pact {
    display: flex;
    gap: var(--sp-1);
  }
  .lbl {
    font-size: var(--fs-sm);
    color: var(--text-muted);
    font-weight: 500;
  }
  section {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    padding: var(--sp-4);
    border-bottom: 1px solid var(--hairline);
  }
  .two {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--sp-3);
    align-items: end;
  }
  .det {
    display: flex;
    align-items: center;
    height: var(--control-h);
  }
  .region {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    height: var(--control-h-sm);
    padding: 0 var(--sp-2);
    border: 0;
    border-radius: var(--r-sm);
    background: var(--grad-2);
    color: var(--text);
    font: inherit;
    font-size: var(--fs-sm);
    font-variant-numeric: tabular-nums;
    cursor: pointer;
  }
  .region:hover {
    background: var(--grad-3);
  }
  .region .icon {
    font-size: 18px;
    color: var(--text-muted);
  }
  .dim {
    margin-left: auto;
    color: var(--text-muted);
    font-size: var(--fs-xs);
  }
  .cmp {
    display: grid;
    place-items: center;
    width: var(--control-h);
    height: var(--control-h);
    border: 0;
    border-radius: var(--r-md);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    touch-action: none;
  }
  .cmp:hover {
    background: var(--hover);
    color: var(--text);
  }
  .cmp.on {
    background: var(--accent-soft);
    color: var(--accent-strong);
  }
  .over {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
  }
  .live {
    position: absolute;
    pointer-events: none;
    object-fit: fill;
    outline: 1px solid var(--accent-glow);
  }
  .area {
    position: absolute;
    pointer-events: none;
    outline: calc(1.5px * var(--s)) dashed var(--accent);
    outline-offset: 0;
    box-shadow: 0 0 0 100000px rgb(0 0 0 / 0.28);
  }
  .area.busy {
    outline-style: solid;
    outline-color: var(--accent-strong);
    box-shadow:
      0 0 0 100000px rgb(0 0 0 / 0.4),
      0 0 calc(18px * var(--s)) calc(2px * var(--s)) var(--accent-glow);
    animation: breathe 1.4s ease-in-out infinite;
  }
  @keyframes breathe {
    50% {
      outline-color: var(--accent);
    }
  }
  .strip {
    flex: none;
    display: flex;
    gap: var(--sp-2);
    padding: var(--sp-2) var(--sp-3);
    overflow-x: auto;
    border-top: 1px solid var(--hairline);
    background: var(--grad-1);
  }
  .ver {
    position: relative;
    flex: none;
    display: grid;
    place-items: center;
    width: 64px;
    height: 64px;
    padding: 0;
    border: 1px solid var(--hairline);
    border-radius: var(--r-md);
    background: var(--grad-2);
    overflow: hidden;
    cursor: pointer;
    transition: transform var(--dur-fast) var(--ease);
  }
  .ver:active {
    transform: scale(0.95);
  }
  .ver img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .ver.on {
    box-shadow:
      0 0 0 2px var(--bg),
      0 0 0 3px var(--accent);
  }
  .ver.wait {
    cursor: default;
  }
  .x {
    position: absolute;
    top: 3px;
    right: 3px;
    display: grid;
    place-items: center;
    width: 20px;
    height: 20px;
    padding: 0;
    border: 0;
    border-radius: var(--r-sm);
    background: var(--scrim);
    color: var(--text);
    cursor: pointer;
    opacity: 0;
    transition: opacity var(--dur-fast) var(--ease);
  }
  .x .icon {
    font-size: 15px;
  }
  .ver:hover .x,
  .x:focus-visible {
    opacity: 1;
  }
  .x:hover {
    background: var(--danger);
  }
  @media (pointer: coarse) {
    .x {
      opacity: 1;
    }
  }
  .ver.run {
    box-shadow: 0 0 12px -2px var(--accent-glow);
  }
  .n {
    position: absolute;
    left: 3px;
    bottom: 3px;
    padding: 0 4px;
    border-radius: var(--r-sm);
    background: var(--scrim);
    font-size: 10px;
    line-height: 16px;
    font-variant-numeric: tabular-nums;
  }
  .empty {
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
  }
  .empty header {
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
  .pick {
    width: 100%;
    max-width: 760px;
    margin: 0 auto;
    padding: var(--sp-4);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--sp-4);
  }
  .pick > :global(*) {
    width: 100%;
  }
  .pick > .wait {
    width: auto;
    padding: var(--sp-6) 0;
  }
  .recent {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
    gap: var(--sp-2);
  }
  @media (max-width: 640px) {
    .pick {
      padding: var(--sp-2);
    }
    .ver {
      width: 52px;
      height: 52px;
    }
  }
</style>
