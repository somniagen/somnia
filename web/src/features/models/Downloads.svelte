<script lang="ts">
  import { GlowProgressBar, IconButton, toast } from '$lib/ui'
  import { api } from '$lib/api'
  import { live } from '$lib/live.svelte'
  import { fmtSize } from './util'

  const seen = new Map<string, string>()
  $effect(() =>
    live.on((m) => {
      if (m.type !== 'download') return
      const d = m.download
      const prev = seen.get(d.id)
      seen.set(d.id, d.status)
      if (prev === d.status) return
      if (d.status === 'error') toast.error(d.name, { description: d.error ?? undefined })
      else if (d.status === 'done') toast.success('Downloaded', { description: d.name })
    }),
  )

  const active = $derived(Object.values(live.downloads).filter((d) => d.status === 'queued' || d.status === 'downloading'))
</script>

{#if active.length}
  <div class="strip">
    {#each active as d (d.id)}
      <div class="dl">
        <div class="top">
          <span class="icon">download</span>
          <span class="nm">{d.name}</span>
          <span class="st">
            {#if d.status === 'queued'}Queued{:else}{fmtSize(d.received)} / {fmtSize(d.total)}{#if d.speed > 0}&nbsp;&middot;&nbsp;{fmtSize(d.speed)}/s{/if}{/if}
          </span>
          <IconButton icon="close" label="Cancel" size="sm" variant="danger" onclick={() => api.cancelDownload(d.id)} />
        </div>
        <GlowProgressBar value={d.total ? d.received / d.total : null} status="running" fixed={false} height={3} />
      </div>
    {/each}
  </div>
{/if}

<style>
  .strip {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    padding: var(--sp-2) var(--sp-3);
    border: 1px solid var(--hairline);
    border-radius: var(--r-md);
    background: var(--surface-1);
  }
  .dl {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .top {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    font-size: var(--fs-sm);
  }
  .nm {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .st {
    color: var(--text-muted);
    font-size: var(--fs-xs);
    white-space: nowrap;
  }
  .icon {
    color: var(--text-muted);
  }
</style>
