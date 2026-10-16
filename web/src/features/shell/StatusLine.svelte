<script lang="ts">
  import { live } from '$lib/live.svelte'
  import { eta, statusText } from './status'

  let finished = $state(false)
  let expanded = $state(false)
  let timer: ReturnType<typeof setTimeout> | undefined

  $effect(() => {
    return live.on((m) => {
      if (m.type !== 'done') return
      finished = true
      clearTimeout(timer)
      timer = setTimeout(() => (finished = false), 2200)
    })
  })

  const running = $derived(!!live.current || !!live.running)
  const err = $derived(live.lastError)
  const queued = $derived(live.pending.length)
  const open = $derived(running || finished || !!err)
  const text = $derived(running ? statusText(live.current) : 'Done')
  const remain = $derived(running ? eta(live.current?.etaSec) : '')
</script>

<div class="sl" class:open class:run={running && !err} role="status" aria-live="polite">
  <div class="in">
    <div class="row" class:bad={!!err}>
      {#if err}
        <span class="icon">error</span>
        <button type="button" class="msg" class:expanded onclick={() => (expanded = !expanded)} title={err.message}>{err.message}</button>
        <button type="button" class="x" aria-label="Dismiss error" onclick={() => ((expanded = false), live.dismissError())}>
          <span class="icon">close</span>
        </button>
      {:else}
        <span class="dot" class:run={running}></span>
        <span class="txt">{text}</span>
        <span class="grow"></span>
        {#if remain}<span class="dim">{remain}</span>{/if}
        {#if queued > 0}<span class="dim">{queued} queued</span>{/if}
      {/if}
    </div>
  </div>
</div>

<style>
  .sl {
    flex: none;
    display: grid;
    grid-template-rows: 0fr;
    transition: grid-template-rows var(--dur) var(--ease);
    background: var(--grad-1);
    border-bottom: 1px solid transparent;
    position: relative;
    z-index: 11;
  }
  .sl.run {
    background: var(--stripes), var(--grad-1);
    background-size: 22.63px 22.63px, auto;
    animation: crawl 1.2s linear infinite;
  }
  @keyframes crawl {
    to {
      background-position: 22.63px 0, 0 0;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .sl.run {
      animation: none;
    }
  }
  .sl.open {
    grid-template-rows: 1fr;
    border-bottom-color: var(--hairline);
  }
  .in {
    overflow: hidden;
    min-height: 0;
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: 24px;
    padding: 4px var(--sp-3) 3px;
    font-size: var(--fs-xs);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .row.bad {
    background: var(--danger-soft);
    color: var(--danger);
    align-items: flex-start;
    padding-top: 5px;
  }
  .txt {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .dim {
    color: var(--text-muted);
    flex: none;
  }
  .grow {
    flex: 1;
  }
  .dot {
    flex: none;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--success);
  }
  .dot.run {
    background: var(--grad-accent-hi);
    animation: pulse 1.4s ease-in-out infinite;
  }
  @keyframes pulse {
    50% {
      opacity: 0.3;
    }
  }
  .icon {
    font-size: 15px;
    flex: none;
  }
  .msg {
    flex: 1;
    min-width: 0;
    padding: 0;
    border: 0;
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .msg.expanded {
    white-space: normal;
    word-break: break-word;
  }
  .x {
    flex: none;
    display: grid;
    place-items: center;
    width: 20px;
    height: 20px;
    margin: -2px 0;
    padding: 0;
    border: 0;
    border-radius: var(--r-sm);
    background: none;
    color: inherit;
    cursor: pointer;
  }
  .x:hover {
    background: var(--hover);
  }
  @media (pointer: coarse) {
    .x {
      width: 32px;
      height: 32px;
      margin: -8px -6px -8px 0;
    }
  }
</style>
