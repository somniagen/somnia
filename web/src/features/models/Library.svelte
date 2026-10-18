<script lang="ts">
  import { Button, Chip, EmptyState, GlowProgressBar, IconButton, Modal, SearchField, Segmented, Select, Skeleton, Surface, toast, tooltip } from '$lib/ui'
  import { api } from '$lib/api'
  import { session } from '$lib/session.svelte'
  import type { CivitaiModel, LocalModel, ModelKind } from '$lib/types'
  import CivitaiDetail from './CivitaiDetail.svelte'
  import { modelDefaults } from './defaults.svelte'
  import { models } from './store.svelte'
  import { fmtSize } from './util'

  const KINDS: { value: ModelKind; label: string }[] = [
    { value: 'checkpoint', label: 'Checkpoints' },
    { value: 'lora', label: 'LoRAs' },
    { value: 'upscaler', label: 'Upscalers' },
    { value: 'vae', label: 'VAE' },
    { value: 'detector', label: 'Detectors' },
    { value: 'text_encoder', label: 'Text encoders' },
    { value: 'embedding', label: 'Embeddings' },
  ]

  let kind = $state<ModelKind>('checkpoint')
  let fam = $state('all')
  let q = $state('')
  let sort = $state('name')
  let confirm = $state<LocalModel | null>(null)
  let confirmOpen = $state(false)
  let detail = $state<CivitaiModel | null>(null)
  let detailVersion = $state<number | null>(null)
  let detailOpen = $state(false)
  const idf = $derived(models.identify)

  $effect(() => modelDefaults.start())

  const counts = $derived.by(() => {
    const c: Record<string, number> = {}
    for (const m of models.list) c[m.kind] = (c[m.kind] ?? 0) + 1
    return c
  })
  const kinds = $derived(KINDS.map((k) => ({ value: k.value, label: counts[k.value] ? `${k.label} ${counts[k.value]}` : k.label })))
  const hasFamily = $derived(kind === 'checkpoint' || kind === 'lora')

  const shown = $derived.by(() => {
    const s = q.trim().toLowerCase()
    const out = models.list.filter(
      (m) =>
        m.kind === kind &&
        (!hasFamily || fam === 'all' || m.family === fam) &&
        (!s || m.name.toLowerCase().includes(s) || m.civitai?.trainedWords.some((w) => w.toLowerCase().includes(s))),
    )
    if (sort === 'name') out.sort((a, b) => a.name.localeCompare(b.name))
    else if (sort === 'newest') out.sort((a, b) => b.mtime - a.mtime)
    else out.sort((a, b) => b.size - a.size)
    return out
  })

  function use(m: LocalModel) {
    if (m.kind === 'checkpoint') {
      if (m.family) session.setFamily(m.family)
      session.update({ model: m.id })
      if (!modelDefaults.apply(m.id)) toast.success('Model set', { description: m.name })
    } else if (m.kind === 'lora') {
      if (m.family && m.family !== session.family) session.setFamily(m.family)
      session.addLora(m.id, modelDefaults.weight(m.id))
      models.touch(m.id)
      toast.success('LoRA added', { description: m.name })
    }
  }

  async function remove() {
    const m = confirm
    confirmOpen = false
    if (!m) return
    try {
      await api.deleteModel(m.id)
      await models.refresh()
      toast.success('Deleted', { description: m.name })
    } catch (e) {
      toast.error('Delete failed', { description: String(e instanceof Error ? e.message : e) })
    }
  }

  async function identify() {
    try {
      models.identify = await api.identify()
    } catch {
      toast.error('Identify failed')
    }
  }

  async function openUpdate(m: LocalModel) {
    const c = m.civitai
    if (!c?.updateVersionId) return
    try {
      detail = await api.civitaiModel(c.modelId)
      detailVersion = c.updateVersionId
      detailOpen = true
    } catch (e) {
      toast.error('Civitai unavailable', { description: String(e instanceof Error ? e.message : e) })
    }
  }

  const link = (m: LocalModel) =>
    m.civitai?.modelId ? `https://civitai.com/models/${m.civitai.modelId}${m.civitai.versionId ? `?modelVersionId=${m.civitai.versionId}` : ''}` : null
</script>

<div class="lib">
  <div class="bar">
    <div class="seg"><Segmented items={kinds} bind:value={kind} size="sm" /></div>
    <div class="grow"></div>
    <IconButton icon="refresh" label="Rescan" onclick={() => models.rescan()} />
    <IconButton icon="fingerprint" label="Identify on Civitai" onclick={identify} disabled={idf.running} />
  </div>
  {#if idf.running}
    <div class="idf">
      <span class="icon">fingerprint</span>
      <span>Identifying {idf.done}/{idf.total}</span>
      <GlowProgressBar value={idf.total ? idf.done / idf.total : null} status="running" height={3} />
    </div>
  {/if}
  <div class="bar">
    <SearchField size="sm" class="search" bind:value={q} />
    {#if hasFamily}
      <Select
        size="sm"
        items={[
          { value: 'all', label: 'All families' },
          { value: 'illustrious', label: 'Illustrious' },
          { value: 'anima', label: 'Anima' },
        ]}
        bind:value={fam}
      />
    {/if}
    <Select
      size="sm"
      icon="sort"
      items={[
        { value: 'name', label: 'Name' },
        { value: 'newest', label: 'Newest' },
        { value: 'size', label: 'Size' },
      ]}
      bind:value={sort}
    />
  </div>

  {#if !models.loaded}
    <div class="grid">
      {#each Array(6) as _}<Skeleton height="260px" radius="var(--r-lg)" />{/each}
    </div>
  {:else if !shown.length}
    <EmptyState icon="deployed_code" title="Nothing here" description={q ? undefined : 'Add model folders in settings, or get some from Civitai.'} />
  {:else}
    <div class="grid">
      {#each shown as m (m.id)}
        {@const url = link(m)}
        <Surface level={1} padding="0" class="card">
          <div class="pv" class:tall={m.kind === 'checkpoint' || m.kind === 'lora'}>
            {#if m.previewUrl}
              <img src={m.previewUrl} alt="" loading="lazy" />
            {:else}
              <span class="icon big">deployed_code</span>
            {/if}
            {#if m.family}<span class="fam">{m.family}</span>{/if}
            {#if m.civitai?.updateVersionId}
              <button type="button" class="upd" use:tooltip={`Update: ${m.civitai.updateVersionName}`} aria-label="Update available" onclick={() => openUpdate(m)}>
                <span class="icon">upgrade</span>
              </button>
            {/if}
          </div>
          <div class="info">
            <div class="nm" title={m.name}>{m.name}</div>
            <div class="sub">
              <span>{fmtSize(m.size)}</span>
              {#if m.civitai?.baseModel && m.civitai.baseModel !== 'Unknown'}<span>{m.civitai.baseModel}</span>{/if}
            </div>
            {#if m.civitai?.trainedWords.length}
              <div class="words">
                {#each m.civitai.trainedWords.slice(0, 4) as w}
                  <Chip size="sm" label={w} onclick={() => navigator.clipboard?.writeText(w).then(() => toast.info('Copied'))} />
                {/each}
              </div>
            {/if}
            <div class="acts">
              {#if m.kind === 'checkpoint' || m.kind === 'lora'}
                <Button size="sm" variant="primary" icon={m.kind === 'lora' ? 'add' : 'check'} onclick={() => use(m)}>Use</Button>
              {/if}
              <div class="grow"></div>
              {#if url}<a class="ib" href={url} target="_blank" rel="noopener noreferrer" aria-label="Open on Civitai"><span class="icon">open_in_new</span></a>{/if}
              <IconButton
                icon="delete"
                label="Delete"
                size="sm"
                variant="danger"
                onclick={() => {
                  confirm = m
                  confirmOpen = true
                }}
              />
            </div>
          </div>
        </Surface>
      {/each}
    </div>
  {/if}
</div>

<Modal bind:open={confirmOpen} title="Delete model" width={400}>
  <p class="cm">{confirm?.name}</p>
  {#snippet footer()}
    <Button onclick={() => (confirmOpen = false)}>Cancel</Button>
    <Button variant="danger" icon="delete" onclick={remove}>Delete</Button>
  {/snippet}
</Modal>

<CivitaiDetail model={detail} initialVersion={detailVersion} bind:open={detailOpen} />

<style>
  .bar :global(.search) {
    flex: 1;
    min-width: 140px;
  }
  .lib {
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
  .grow {
    flex: 1;
  }
  .seg {
    min-width: 0;
    max-width: 100%;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 140px), 1fr));
    gap: var(--sp-3);
  }
  :global(.card) {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .pv {
    position: relative;
    display: grid;
    place-items: center;
    aspect-ratio: 16 / 9;
    background: var(--surface-3);
    color: var(--text-faint);
    overflow: hidden;
  }
  .pv.tall {
    aspect-ratio: 4 / 5;
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
  .fam {
    position: absolute;
    top: 6px;
    left: 6px;
    padding: 2px 6px;
    border-radius: var(--r-sm);
    background: var(--scrim);
    color: var(--text);
    font-size: var(--fs-xs);
  }
  .upd {
    position: absolute;
    top: 6px;
    right: 6px;
    display: grid;
    place-items: center;
    width: 24px;
    height: 24px;
    padding: 0;
    border: 0;
    border-radius: var(--r-sm);
    background: var(--scrim);
    color: var(--success);
    cursor: pointer;
  }
  .upd:hover {
    color: var(--text);
  }
  .upd .icon {
    font-size: 18px;
  }
  .idf {
    display: grid;
    grid-template-columns: auto auto 1fr;
    align-items: center;
    gap: var(--sp-2);
    color: var(--text-muted);
    font-size: var(--fs-xs);
  }
  .idf .icon {
    font-size: 16px;
  }
  .info {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: var(--sp-2) var(--sp-3) var(--sp-3);
  }
  .nm {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--fs-md);
  }
  .sub {
    display: flex;
    gap: var(--sp-2);
    color: var(--text-muted);
    font-size: var(--fs-xs);
  }
  .words {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .acts {
    display: flex;
    align-items: center;
    gap: 2px;
    margin-top: 4px;
  }
  .ib {
    display: grid;
    place-items: center;
    width: var(--control-h-sm);
    height: var(--control-h-sm);
    border-radius: var(--r-sm);
    color: var(--text-muted);
  }
  .ib:hover {
    background: var(--hover);
    color: var(--text);
  }
  .cm {
    margin: 0;
    word-break: break-all;
  }
</style>
