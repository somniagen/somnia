<script lang="ts">
  import { Button, GlowProgressBar, IconButton, InfoTip, Select, Sheet, Skeleton, Toggle, toast } from '$lib/ui'
  import { api } from '$lib/api'
  import { live } from '$lib/live.svelte'
  import type { HfCategory, HfFile, HfRepo, HfRepoDetail } from '$lib/types'
  import { HF_CATEGORIES, categoryKind, fileCategory } from './hf'
  import { fmtCount, fmtSize } from './util'

  let { repo, category = '', open = $bindable(false) }: { repo: HfRepo | null; category?: HfCategory; open: boolean } = $props()

  let full = $state<HfRepoDetail | null>(null)
  let error = $state('')
  let showAll = $state(false)
  let showMore = $state(false)
  let busy = $state<Record<string, boolean>>({})
  // per file kind overrides, keyed by path
  let picks = $state<Record<string, HfCategory>>({})

  $effect(() => {
    if (!open || !repo) return
    full = null
    error = ''
    showAll = false
    showMore = false
    picks = {}
    const id = repo.id
    api
      .hfRepo(id, category)
      .then((r) => {
        if (repo?.id === id) full = r
      })
      .catch((e) => {
        if (repo?.id === id) error = e instanceof Error ? e.message : 'Failed'
      })
  })

  const pick = (f: HfFile) => picks[f.path] ?? fileCategory(f)
  const files = $derived.by(() => {
    const all = full?.files ?? []
    if (showAll) return all
    const want = category
    return all.filter((f) => f.kind && (!want || fileCategory(f) === want))
  })
  const hidden = $derived((full?.files.length ?? 0) - files.length)
  const readme = $derived(
    (full?.readme ?? '')
      .replace(/<[^>]+>/g, '')
      .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim(),
  )

  const dlFor = (path: string) =>
    Object.values(live.downloads).find(
      (d) => d.source === 'hf' && d.repo === full?.id && d.file === path && (d.status === 'queued' || d.status === 'downloading'),
    )
  const finished = $derived(
    new Set(Object.values(live.downloads).filter((d) => d.source === 'hf' && d.repo === full?.id && d.status === 'done').map((d) => d.file)),
  )

  async function download(f: HfFile) {
    if (!full) return
    const k = categoryKind(pick(f))
    if (!k) return
    busy[f.path] = true
    try {
      await api.hfDownload(full.id, { path: f.path, size: f.size, ...k })
      toast.info('Download started')
    } catch (e) {
      toast.error('Download failed', { description: e instanceof Error ? e.message : undefined })
    } finally {
      busy[f.path] = false
    }
  }

  const KIND_ITEMS: { value: HfCategory; label: string }[] = [{ value: '', label: 'Type?' }, ...HF_CATEGORIES.filter((c) => c.value)]
</script>

<Sheet bind:open title={repo?.id ?? ''} width={820} snaps={[0.92]}>
  {#if repo}
    <div class="detail">
      <div class="head">
        <span class="st"><span class="icon">download</span>{fmtCount(full?.downloads ?? repo.downloads)}</span>
        <span class="st"><span class="icon">favorite</span>{fmtCount(full?.likes ?? repo.likes)}</span>
        {#if repo.gated}
          <span class="st warn"><span class="icon">lock</span>Gated</span>
          <InfoTip text="Accept the license on huggingface.co and add a Hugging Face token in settings to download." />
        {/if}
        <a class="ext" href="https://huggingface.co/{repo.id}" target="_blank" rel="noopener noreferrer" aria-label="Open on Hugging Face">
          <span class="icon">open_in_new</span>
        </a>
        <span class="grow"></span>
        {#if full && (hidden > 0 || showAll)}
          <Toggle size="sm" label="All files" bind:checked={showAll} />
        {/if}
      </div>

      {#if error}
        <div class="err">{error}</div>
      {:else if !full}
        <div class="files">
          {#each Array(3) as _}<Skeleton height="52px" radius="var(--r-md)" />{/each}
        </div>
      {:else}
        <div class="files">
          {#each files as f (f.path)}
            {@const d = dlFor(f.path)}
            {@const c = pick(f)}
            <div class="file">
              <div class="fm">
                <span class="fn" title={f.path}>{f.path}</span>
                <span class="fs">{fmtSize(f.size)}</span>
              </div>
              {#if d}
                <span class="pct">{d.total ? Math.round((d.received / d.total) * 100) : 0}%</span>
                <IconButton icon="close" label="Cancel" variant="danger" size="sm" onclick={() => api.cancelDownload(d.id)} />
                <GlowProgressBar class="fp" value={d.total ? d.received / d.total : null} fixed={false} height={3} />
              {:else if f.installed || finished.has(f.path)}
                <span class="ok" aria-label="Installed"><span class="icon">check</span></span>
              {:else}
                <Select size="sm" items={KIND_ITEMS} value={c} onchange={(v: HfCategory) => (picks[f.path] = v)} />
                <Button size="sm" variant="primary" icon="download" disabled={!c} loading={busy[f.path]} onclick={() => download(f)}>Get</Button>
              {/if}
            </div>
          {:else}
            <div class="none">No {category ? HF_CATEGORIES.find((x) => x.value === category)?.label : 'model'} files</div>
          {/each}
        </div>

        {#if readme}
          <div class="desc" class:clamped={!showMore}>{readme}</div>
          <button type="button" class="more" onclick={() => (showMore = !showMore)}>{showMore ? 'Less' : 'More'}</button>
        {/if}
      {/if}
    </div>
  {/if}
</Sheet>

<style>
  .detail {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    flex-wrap: wrap;
    color: var(--text-muted);
    font-size: var(--fs-sm);
  }
  .grow {
    flex: 1;
  }
  .st {
    display: inline-flex;
    align-items: center;
    gap: 3px;
  }
  .st .icon {
    font-size: 16px;
  }
  .warn {
    color: var(--warning);
  }
  .ext {
    display: grid;
    color: var(--text-muted);
  }
  .ext:hover {
    color: var(--text);
  }
  .err,
  .none {
    color: var(--text-muted);
    font-size: var(--fs-sm);
  }
  .err {
    color: var(--danger);
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
    direction: rtl;
    text-align: left;
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
  .desc {
    color: var(--text-muted);
    font-size: var(--fs-sm);
    line-height: 1.5;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .desc.clamped {
    max-height: 9em;
    overflow: hidden;
    mask-image: linear-gradient(#000 55%, transparent);
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
</style>
