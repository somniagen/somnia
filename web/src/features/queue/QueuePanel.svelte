<script lang="ts">
  import { api } from '$lib/api'
  import { live } from '$lib/live.svelte'
  import type { Job } from '$lib/types'
  import { Button, EmptyState, GlowProgressBar, IconButton, coarse, toast } from '$lib/ui'

  let { title = true }: { title?: boolean } = $props()

  const jobs = $derived(live.queue.filter((j) => j.status === 'queued' || j.status === 'running'))
  const running = $derived(jobs.find((j) => j.status === 'running'))
  const queued = $derived(jobs.filter((j) => j.status === 'queued'))

  let dragId = $state<string | null>(null)
  let overId = $state<string | null>(null)

  async function cancel(j: Job) {
    try {
      await api.cancel(j.id)
    } catch (e) {
      toast.error('Could not cancel', { description: e instanceof Error ? e.message : String(e) })
    }
  }
  async function clear() {
    try {
      await api.clearQueue()
    } catch (e) {
      toast.error('Could not clear', { description: e instanceof Error ? e.message : String(e) })
    }
  }
  async function drop(target: string) {
    const from = dragId
    dragId = overId = null
    if (!from || from === target) return
    const ids = queued.map((j) => j.id)
    ids.splice(ids.indexOf(from), 1)
    ids.splice(ids.indexOf(target), 0, from)
    try {
      await api.reorder(ids)
    } catch (e) {
      toast.error('Reorder failed', { description: e instanceof Error ? e.message : String(e) })
    }
  }
  const snippet = (j: Job) => j.params.prompt.replace(/\s+/g, ' ').trim() || 'Empty prompt'
</script>

<div class="queue">
  <div class="head">
    {#if title}<span class="title">Queue</span>{/if}
    {#if jobs.length}<span class="count">{jobs.length}</span>{/if}
    <span class="grow"></span>
    {#if queued.length}
      <Button size="sm" variant="ghost" icon="playlist_remove" class="clr" onclick={clear}>Clear</Button>
    {/if}
  </div>

  {#if !jobs.length}
    <EmptyState compact icon="queue" title="Queue is empty" />
  {:else}
    <ul>
      {#if running}
        <li class="job run">
          <div class="row">
            {#if live.preview}<img class="th" src={live.preview} alt="" />{:else}<div class="th ph"></div>{/if}
            <div class="txt">
              <div class="p">{snippet(running)}</div>
              <div class="m">{running.params.width}x{running.params.height} / {running.params.steps} steps / {Math.round((live.current?.overall ?? 0) * 100)}%</div>
            </div>
            <IconButton icon="stop_circle" label="Cancel" variant="danger" size="sm" onclick={() => cancel(running)} />
          </div>
          <GlowProgressBar
            fixed={false}
            height={2}
            status="running"
            value={live.current && live.current.phase !== 'load' ? live.current.overall : null}
            label="Job progress"
          />
        </li>
      {/if}
      {#each queued as j (j.id)}
        <li
          class="job"
          class:drag={dragId === j.id}
          class:over={overId === j.id && dragId !== j.id}
          draggable={!coarse.current}
          ondragstart={(e) => {
            dragId = j.id
            e.dataTransfer?.setData('text/plain', j.id)
            if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
          }}
          ondragover={(e) => {
            if (!dragId) return
            e.preventDefault()
            overId = j.id
          }}
          ondrop={(e) => {
            e.preventDefault()
            drop(j.id)
          }}
          ondragend={() => (dragId = overId = null)}
        >
          <div class="row">
            {#if !coarse.current}<span class="icon grip">drag_indicator</span>{/if}
            <div class="txt">
              <div class="p">{snippet(j)}</div>
              <div class="m">{j.params.width}x{j.params.height} / {j.params.steps} steps</div>
            </div>
            <IconButton icon="close" label="Remove" size="sm" class="rm" onclick={() => cancel(j)} />
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .queue {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    min-height: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: 32px;
  }
  .title {
    font-weight: 600;
  }
  .count {
    font-size: var(--fs-xs);
    padding: 1px 7px;
    border-radius: var(--r-sm);
    background: var(--surface-3);
    color: var(--text-muted);
  }
  .grow {
    flex: 1;
  }
  :global(.clr) {
    color: var(--danger) !important;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    overflow: auto;
  }
  .job {
    border: 1px solid var(--hairline);
    border-radius: var(--r-md);
    background: var(--surface-1);
    padding: var(--sp-2);
    overflow: hidden;
    position: relative;
    transition:
      opacity var(--dur) var(--ease),
      border-color var(--dur) var(--ease);
  }
  .job.run {
    background: var(--surface-2);
  }
  .job.drag {
    opacity: 0.4;
  }
  .job.over {
    border-color: var(--accent);
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
  }
  .th {
    flex: none;
    width: 40px;
    height: 40px;
    border-radius: var(--r-sm);
    object-fit: cover;
    background: var(--surface-3);
  }
  .grip {
    flex: none;
    font-size: 18px;
    color: var(--text-faint);
    cursor: grab;
  }
  .txt {
    flex: 1;
    min-width: 0;
  }
  .p {
    font-size: var(--fs-sm);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .m {
    font-size: var(--fs-xs);
    color: var(--text-faint);
    font-variant-numeric: tabular-nums;
  }
  .job :global(.rm:hover) {
    color: var(--danger);
  }
  .job.run :global(.gpb) {
    margin-top: var(--sp-2);
    position: relative;
  }
</style>
