<script lang="ts">
  import { untrack } from 'svelte'
  import { Button, Chip, GlowProgressBar, IconButton, InfoTip, Modal, Select, Sheet, Skeleton, mobile, toast } from '$lib/ui'
  import { api } from '$lib/api'
  import { live } from '$lib/live.svelte'
  import { session } from '$lib/session.svelte'
  import type { CivitaiImage, CivitaiModel, CivitaiVersion } from '$lib/types'
  import { models } from './store.svelte'
  import { fmtSize, paramsFromMeta, sanitize, thumbUrl } from './util'

  let {
    model,
    open = $bindable(false),
    initialVersion = null,
  }: { model: CivitaiModel | null; open: boolean; initialVersion?: number | null } = $props()

  let full = $state<CivitaiModel | null>(null)
  let versionId = $state(0)
  let images = $state<CivitaiImage[]>([])
  let imgCursor = $state<string | null>(null)
  let imgLoading = $state(false)
  let showMore = $state(false)
  let light = $state<CivitaiImage | null>(null)
  let lightOpen = $state(false)
  let busy = $state<Record<number, boolean>>({})
  let token = $state(true)

  const m = $derived(full ?? model)
  const version = $derived<CivitaiVersion | undefined>(m?.versions.find((v) => v.id === versionId) ?? m?.versions[0])
  const nsfw = $derived(live.settings?.showNsfw ?? false)
  const visible = $derived(images.filter((i) => nsfw || i.nsfwLevel <= 1))
  const missingMeta = $derived(visible.length > 0 && visible.every((i) => !i.meta?.prompt))
  const html = $derived(sanitize((version?.description || m?.description || '').trim()))
  const installedVersions = $derived(new Set(models.list.map((x) => x.civitai?.versionId)))

  $effect(() => {
    if (!open || !model) return
    full = null
    versionId = (initialVersion && model.versions.some((v) => v.id === initialVersion) ? initialVersion : model.versions[0]?.id) ?? 0
    showMore = false
    const id = model.id
    api
      .civitaiModel(id)
      .then((r) => {
        if (model?.id === id) full = r
      })
      .catch(() => {})
    api
      .settings()
      .then((s) => (token = !!s.civitaiToken))
      .catch(() => {})
  })

  async function loadImages(reset: boolean) {
    const v = version
    if (!v || imgLoading) return
    if (reset) {
      images = v.images
      imgCursor = null
    }
    imgLoading = true
    const vid = v.id
    try {
      const r = await api.civitaiImages(vid, reset ? undefined : (imgCursor ?? undefined))
      if (vid !== version?.id) return
      const have = new Set(reset ? [] : images.map((i) => i.id))
      images = reset ? r.items : [...images, ...r.items.filter((i) => !have.has(i.id))]
      imgCursor = r.nextCursor
    } catch {
    } finally {
      imgLoading = false
    }
  }

  $effect(() => {
    if (open && version?.id) untrack(() => void loadImages(true))
  })

  const dlFor = (fileName: string, vid: number) =>
    Object.values(live.downloads).find((d) => d.versionId === vid && (d.status === 'queued' || d.status === 'downloading') && (d.name === fileName || d.name.includes(fileName)))
    ?? Object.values(live.downloads).find((d) => d.versionId === vid && (d.status === 'queued' || d.status === 'downloading'))

  async function download(fileId: number) {
    if (!version) return
    busy[fileId] = true
    try {
      await api.download(version.id, fileId)
      toast.info('Download started')
    } catch (e) {
      toast.error('Download failed', { description: e instanceof Error ? e.message : undefined })
    } finally {
      busy[fileId] = false
    }
  }

  const copy = (t: string) => navigator.clipboard?.writeText(t).then(() => toast.info('Copied'))

  function usePrompt(i: CivitaiImage) {
    if (!i.meta?.prompt) return
    session.setPrompt(i.meta.prompt, i.meta.negativePrompt)
    toast.success('Prompt applied')
  }
  function useAll(i: CivitaiImage) {
    if (!i.meta) return
    session.applyParams(paramsFromMeta(i.meta, session.info?.samplers ?? []))
    toast.success('Params applied')
  }
  function openLight(i: CivitaiImage) {
    light = i
    lightOpen = true
  }
  function step(d: number) {
    if (!light) return
    const idx = visible.findIndex((i) => i.id === light!.id)
    const n = visible[idx + d]
    if (n) light = n
  }
  const paramLine = (i: CivitaiImage) =>
    [i.meta?.sampler, i.meta?.steps && `${i.meta.steps} steps`, i.meta?.cfgScale && `cfg ${i.meta.cfgScale}`, i.meta?.Size, i.meta?.seed && `seed ${i.meta.seed}`]
      .filter(Boolean)
      .join('  ')
</script>

<svelte:window
  onkeydown={(e) => {
    if (!lightOpen) return
    if (e.key === 'ArrowLeft') step(-1)
    else if (e.key === 'ArrowRight') step(1)
  }}
/>

<Sheet bind:open title={m?.name ?? ''} width={920} snaps={[0.92]}>
  {#if m && version}
    <div class="detail">
      <div class="head">
        <span class="by">{m.creator?.username ?? ''}</span>
        <a class="ext" href="https://civitai.com/models/{m.id}" target="_blank" rel="noopener noreferrer">
          <span class="icon">open_in_new</span>
        </a>
        <div class="grow"></div>
        <Select
          size="sm"
          items={m.versions.map((v) => ({ value: v.id, label: v.name, hint: v.baseModel }))}
          bind:value={versionId}
        />
      </div>

      {#if html}
        <div class="desc" class:clamped={!showMore}>{@html html}</div>
        <button type="button" class="more" onclick={() => (showMore = !showMore)}>{showMore ? 'Less' : 'More'}</button>
      {/if}

      {#if version.trainedWords.length}
        <div class="words">
          {#each version.trainedWords as w}<Chip label={w} onclick={() => copy(w)} />{/each}
          <IconButton
            icon="lock_add"
            label="Add as boilerplate"
            size="sm"
            onclick={() => {
              session.addBoilerplate(version.trainedWords.join(', '))
              toast.success('Added to prompt')
            }}
          />
        </div>
      {/if}

      <div class="files">
        {#each version.files as f, fi (fi)}
          {@const d = dlFor(f.name, version.id)}
          <div class="file">
            <div class="fm">
              <span class="fn" title={f.name}>{f.name}</span>
              <span class="fs">{fmtSize(f.sizeKB * 1000)}{f.fp ? ` / ${f.fp}` : ''}{f.format ? ` / ${f.format}` : ''}</span>
            </div>
            {#if d}
              <span class="pct">{d.total ? Math.round((d.received / d.total) * 100) : 0}%</span>
              <IconButton icon="close" label="Cancel" variant="danger" size="sm" onclick={() => api.cancelDownload(d.id)} />
              <GlowProgressBar class="fp" value={d.total ? d.received / d.total : null} fixed={false} height={3} />
            {:else if installedVersions.has(version.id) && f.primary}
              <span class="ok"><span class="icon">check</span></span>
            {:else}
              <Button size="sm" variant="primary" icon="download" loading={busy[f.id]} onclick={() => download(f.id)}>Get</Button>
            {/if}
          </div>
        {/each}
      </div>

      <div class="ex">
        <div class="exh">
          <span>Examples</span>
          {#if missingMeta && !token}
            <InfoTip text="Civitai hides example prompts without an API token. Add one in settings." />
          {/if}
        </div>
        <div class="gal">
          {#each visible as i, ii (ii)}
            <button type="button" class="thumb" onclick={() => openLight(i)}>
              {#if i.type === 'video'}
                <video src={i.url} muted loop playsinline preload="metadata"></video>
              {:else}
                <img src={thumbUrl(i.url, 300)} alt="" loading="lazy" />
              {/if}
              {#if i.meta?.prompt}<span class="has icon">notes</span>{/if}
            </button>
          {/each}
          {#if imgLoading}
            {#each Array(4) as _}<Skeleton height="180px" radius="var(--r-md)" />{/each}
          {/if}
        </div>
        {#if imgCursor && !imgLoading}
          <Button size="sm" onclick={() => loadImages(false)}>More</Button>
        {/if}
      </div>
    </div>
  {/if}
</Sheet>

<Modal bind:open={lightOpen} title="" width={1000}>
  {#if light}
    <div class="lb" class:stack={mobile.current}>
      <div class="lbi">
        {#if light.type === 'video'}
          <video src={light.url} controls loop autoplay muted playsinline></video>
        {:else}
          <img src={light.url} alt="" />
        {/if}
        <div class="nav">
          <IconButton icon="chevron_left" label="Previous" variant="default" onclick={() => step(-1)} />
          <IconButton icon="chevron_right" label="Next" variant="default" onclick={() => step(1)} />
        </div>
      </div>
      <div class="lbm">
        {#if light.meta?.prompt}
          <p class="pr">{light.meta.prompt}</p>
          {#if light.meta.negativePrompt}<p class="pr neg">{light.meta.negativePrompt}</p>{/if}
          <p class="pl">{paramLine(light)}</p>
          <div class="acts">
            <Button size="sm" variant="primary" icon="edit_note" onclick={() => usePrompt(light!)}>Use prompt</Button>
            <Button size="sm" icon="tune" onclick={() => useAll(light!)}>Use all params</Button>
            <IconButton icon="content_copy" label="Copy prompt" onclick={() => copy(light!.meta!.prompt!)} />
          </div>
        {:else}
          <p class="pl">No prompt available</p>
        {/if}
      </div>
    </div>
  {/if}
</Modal>

<style>
  .detail {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    min-width: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
  }
  .grow {
    flex: 1;
  }
  .by {
    color: var(--text-muted);
  }
  .ext {
    display: grid;
    color: var(--text-muted);
  }
  .ext:hover {
    color: var(--text);
  }
  .desc {
    color: var(--text-muted);
    font-size: var(--fs-sm);
    line-height: 1.5;
    overflow-wrap: anywhere;
  }
  .desc.clamped {
    max-height: 4.5em;
    overflow: hidden;
    mask-image: linear-gradient(#000 55%, transparent);
  }
  .desc :global(a) {
    color: var(--text);
    text-decoration: underline;
  }
  .desc :global(p) {
    margin: 0 0 0.5em;
  }
  .more {
    align-self: flex-start;
    padding: 0;
    border: 0;
    background: none;
    color: var(--text-muted);
    font: inherit;
    font-size: var(--fs-sm);
    cursor: pointer;
  }
  .more:hover {
    color: var(--text);
  }
  .words {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px;
  }
  .files {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
  }
  .file {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    padding: var(--sp-2) var(--sp-3);
    border: 1px solid var(--hairline);
    border-radius: var(--r-md);
    overflow: hidden;
  }
  .fm {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .fn {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--fs-sm);
  }
  .fs,
  .pct {
    color: var(--text-muted);
    font-size: var(--fs-xs);
  }
  .ok {
    display: grid;
    color: var(--success);
  }
  .file :global(.fp) {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
  }
  .exh {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    margin-bottom: var(--sp-2);
  }
  .gal {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: var(--sp-2);
    margin-bottom: var(--sp-2);
  }
  .thumb {
    position: relative;
    aspect-ratio: 3 / 4;
    padding: 0;
    border: 1px solid var(--hairline);
    border-radius: var(--r-md);
    background: var(--surface-3);
    overflow: hidden;
    cursor: pointer;
  }
  .thumb:active {
    transform: scale(0.98);
  }
  .thumb img,
  .thumb video {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .has {
    position: absolute;
    right: 4px;
    bottom: 4px;
    padding: 2px;
    border-radius: var(--r-sm);
    background: var(--scrim);
    color: var(--text);
    font-size: 16px;
  }
  .lb {
    display: grid;
    grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
    gap: var(--sp-4);
  }
  .lb.stack {
    grid-template-columns: 1fr;
  }
  .lb.stack .lbm {
    max-height: none;
    overflow: visible;
  }
  .lb.stack .lbi img,
  .lb.stack .lbi video {
    max-height: 55dvh;
  }
  .lbi {
    position: relative;
    display: grid;
    place-items: center;
    background: var(--surface-1);
    border-radius: var(--r-md);
    overflow: hidden;
  }
  .lbi img,
  .lbi video {
    max-width: 100%;
    max-height: 70vh;
    object-fit: contain;
  }
  .nav {
    position: absolute;
    inset: auto 0 8px 0;
    display: flex;
    justify-content: space-between;
    padding: 0 8px;
    pointer-events: none;
  }
  .nav :global(button) {
    pointer-events: auto;
  }
  .lbm {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    min-width: 0;
    max-height: 70vh;
    overflow-y: auto;
  }
  .pr {
    margin: 0;
    font-size: var(--fs-sm);
    line-height: 1.5;
    overflow-wrap: anywhere;
  }
  .neg {
    color: var(--text-muted);
  }
  .pl {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--fs-xs);
    white-space: pre-wrap;
  }
  .acts {
    display: flex;
    flex-wrap: wrap;
    gap: var(--sp-2);
  }
</style>
