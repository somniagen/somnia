<script lang="ts">
  import type { Snippet } from 'svelte'
  import { live } from '$lib/live.svelte'
  import { GlowProgressBar, Toaster, mobile, toast, tooltip } from '$lib/ui'
  import Logo from './Logo.svelte'
  import StatusLine from './StatusLine.svelte'
  import { phaseValue } from './status'

  let { route, chrome = true, children }: { route: string; chrome?: boolean; children: Snippet } = $props()

  const nav = [
    { hash: '#/', icon: 'auto_awesome', label: 'Generate' },
    { hash: '#/inpaint', icon: 'format_paint', label: 'Inpaint' },
    { hash: '#/grid', icon: 'grid_view', label: 'Grid' },
    { hash: '#/gallery', icon: 'photo_library', label: 'Gallery' },
    { hash: '#/models', icon: 'deployed_code', label: 'Models' },
    { hash: '#/settings', icon: 'settings', label: 'Settings' },
  ]

  let flash = $state<'success' | 'error' | null>(null)
  let flashTimer: ReturnType<typeof setTimeout> | undefined

  const running = $derived(!!live.current || !!live.running)
  const cur = $derived(live.current)
  const value = $derived(phaseValue(cur))
  const status = $derived(running ? 'running' : (flash ?? 'idle'))
  const pct = $derived(running && cur && cur.phase !== 'load' ? Math.round(cur.overall * 100) : null)

  $effect(() => {
    document.title = pct !== null ? `${pct}% - Somnia` : running ? 'Loading - Somnia' : 'Somnia'
  })

  function setFlash(k: 'success' | 'error') {
    flash = k
    clearTimeout(flashTimer)
    flashTimer = setTimeout(() => (flash = null), 3000)
  }

  $effect(() => {
    const notified = new Set<string>()
    return live.on((m) => {
      if (m.type === 'gallery_item' && m.item.editedWith) {
        const fresh = m.item.createdAt === m.item.updatedAt
        toast.success(fresh ? `Edit from ${m.item.editedWith.name} added to the gallery` : `Gallery copy updated from ${m.item.editedWith.name}`)
      } else if (m.type === 'done') setFlash('success')
      else if (m.type === 'error') setFlash('error')
      else if (m.type === 'download') {
        const d = m.download
        const key = `${d.id}:${d.status}`
        if (notified.has(key)) return
        if (d.status === 'done') toast.success(`${d.name} downloaded`)
        else if (d.status === 'error') toast.error(`${d.name} failed`, { description: d.error ?? undefined })
        else return
        notified.add(key)
      }
    })
  })

  const active = (h: string) => (h === '#/' ? route === '#/' || route === '' || route === '#' : route.startsWith(h))
</script>

<GlowProgressBar {value} {status} fixed />
<Toaster />

<div class="app">
<StatusLine />
<div class="body" class:free={!chrome}>
{#if chrome}
  <div class="shell" class:m={mobile.current}>
    {#if !mobile.current}
      <nav class="rail" aria-label="Main">
        <div class="logo"><Logo size={28} /></div>
        <div class="items">
          {#each nav as n}
            <a href={n.hash} class="nb" class:on={active(n.hash)} aria-label={n.label} aria-current={active(n.hash) ? 'page' : undefined} use:tooltip={{ text: n.label, placement: 'right' }}>
              <span class="icon" class:fill={active(n.hash)}>{n.icon}</span>
            </a>
          {/each}
        </div>
        <span class="grow"></span>
        <div class="conn" class:off={!live.connected} use:tooltip={live.connected ? 'Connected' : 'Reconnecting'} role="status" aria-label={live.connected ? 'Connected' : 'Reconnecting'}></div>
      </nav>
    {/if}
    <main>{@render children()}</main>
    {#if mobile.current}
      <nav class="tabs" aria-label="Main" style="--n: {nav.length}">
        {#each nav as n}
          <a href={n.hash} class="tb" class:on={active(n.hash)} aria-current={active(n.hash) ? 'page' : undefined}>
            <span class="icon" class:fill={active(n.hash)}>{n.icon}</span>
            <span class="tl">{n.label}</span>
          </a>
        {/each}
      </nav>
      {#if !live.connected}<div class="offdot" role="status" aria-label="Reconnecting"></div>{/if}
    {/if}
  </div>
{:else}
  {@render children()}
{/if}
</div>
</div>

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100dvh;
    overflow: hidden;
    padding-top: env(safe-area-inset-top);
  }
  /* solid strip under the translucent ios status bar */
  .app::before {
    content: '';
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: env(safe-area-inset-top);
    background: var(--bg);
    z-index: var(--z-progress);
    pointer-events: none;
  }
  .body {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .body.free {
    display: block;
    overflow: auto;
  }
  .shell {
    flex: 1;
    min-height: 0;
    display: flex;
    overflow: hidden;
  }
  .shell.m {
    flex-direction: column;
  }
  main {
    flex: 1;
    min-width: 0;
    min-height: 0;
    position: relative;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .rail {
    flex: none;
    width: 56px;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: var(--sp-3) 0;
    gap: var(--sp-4);
    background: var(--grad-1);
    border-right: 1px solid var(--hairline);
  }
  .logo {
    display: grid;
    place-items: center;
    height: 36px;
    color: var(--text);
  }
  .items {
    display: flex;
    flex-direction: column;
    gap: var(--sp-1);
  }
  .nb {
    position: relative;
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    border-radius: var(--r-md);
    color: var(--text-muted);
    text-decoration: none;
    transition:
      background-color var(--dur-fast) var(--ease),
      color var(--dur-fast) var(--ease),
      transform var(--dur-fast) var(--ease);
  }
  .nb:hover {
    background: var(--hover);
    color: var(--text);
  }
  .nb:active {
    transform: scale(0.92);
    background: var(--pressed);
  }
  .nb.on {
    background: var(--accent-soft);
    color: var(--accent-strong);
  }
  .nb.on::before {
    content: '';
    position: absolute;
    left: -8px;
    top: 10px;
    bottom: 10px;
    width: 3px;
    border-radius: 0 2px 2px 0;
    background: var(--grad-accent-hi);
  }
  .icon.fill {
    font-variation-settings: 'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24;
  }
  .grow {
    flex: 1;
  }
  .conn {
    width: 8px;
    height: 8px;
    margin-bottom: var(--sp-2);
    border-radius: 50%;
    background: var(--success);
    transition: background-color var(--dur) var(--ease);
  }
  .conn.off {
    background: var(--danger);
    animation: blink 1.2s ease-in-out infinite;
  }
  @keyframes blink {
    50% {
      opacity: 0.35;
    }
  }
  .tabs {
    flex: none;
    display: grid;
    grid-template-columns: repeat(var(--n, 5), minmax(0, 1fr));
    height: calc(56px + env(safe-area-inset-bottom));
    padding-bottom: env(safe-area-inset-bottom);
    background: var(--grad-1);
    border-top: 1px solid var(--hairline);
    position: relative;
    z-index: 10;
  }
  .tb {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    color: var(--text-muted);
    text-decoration: none;
    transition:
      color var(--dur-fast) var(--ease),
      background-color var(--dur-fast) var(--ease);
  }
  .tb:active {
    background: var(--pressed);
  }
  .tb.on {
    color: var(--accent-strong);
  }
  .tl {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 11px;
  }
  @media (max-width: 360px) {
    .tl {
      font-size: 10px;
    }
  }
  .offdot {
    position: fixed;
    top: calc(8px + env(safe-area-inset-top));
    right: 8px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--danger);
    z-index: var(--z-progress);
    animation: blink 1.2s ease-in-out infinite;
  }
</style>
