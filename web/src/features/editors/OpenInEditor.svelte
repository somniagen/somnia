<script lang="ts">
  import { api } from '$lib/api'
  import { editors } from '$lib/editors.svelte'
  import { Spinner, toast, tooltip } from '$lib/ui'

  // url is an /outputs/ or /files/uploads/ image; galleryId links saved edits to it; compact shows only the app icon
  let {
    url,
    galleryId,
    compact = false,
    label,
    ghost = false,
    class: klass,
  }: {
    url: string
    galleryId?: string | null
    compact?: boolean
    // button text instead of "Open in {editor}"; the editor name moves to the tooltip
    label?: string
    ghost?: boolean
    class?: string
  } = $props()

  let busy = $state(false)
  let iconOk = $state(true)
  const ed = $derived(editors.current)

  $effect(() => {
    editors.load()
  })
  $effect(() => {
    void ed?.id
    iconOk = true
  })

  async function open() {
    if (!ed || busy) return
    busy = true
    try {
      await api.openInEditor(url, ed.id, galleryId ?? undefined)
      toast.success(`Opening in ${ed.name}`, { description: 'Edits a copy. Saving adds it to the gallery.' })
    } catch (e) {
      toast.error(`Could not open ${ed.name}`, { description: e instanceof Error ? e.message : String(e) })
    } finally {
      // editors take a moment to come up, keep the button calm meanwhile
      setTimeout(() => (busy = false), 1200)
    }
  }
</script>

{#if ed}
  <button
    type="button"
    class={['oie', klass, { compact, ghost }]}
    disabled={busy}
    aria-label="Open in {ed.name}"
    use:tooltip={compact || label ? `Open in ${ed.name}` : null}
    onclick={open}
  >
    {#if busy}
      <Spinner size={16} />
    {:else if iconOk}
      <img src={api.editorIconUrl(ed.id)} alt="" width="18" height="18" onerror={() => (iconOk = false)} />
    {:else}
      <span class="icon">open_in_new</span>
    {/if}
    {#if !compact}<span class="lbl">{label ?? `Open in ${ed.name}`}</span>{/if}
  </button>
{/if}

<style>
  .oie {
    display: inline-flex;
    align-items: center;
    gap: var(--sp-2);
    height: var(--control-h);
    padding: 0 12px 0 9px;
    border: 0;
    border-radius: var(--r-md);
    background: var(--grad-3);
    box-shadow: var(--sheen), var(--shadow-1);
    color: var(--text);
    font: inherit;
    font-size: var(--fs-sm);
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
    transition: transform var(--dur-fast) var(--ease);
  }
  .oie:hover:not(:disabled) {
    background: var(--grad-4);
  }
  .oie:active:not(:disabled) {
    transform: scale(0.97);
  }
  .ghost {
    background: transparent;
    box-shadow: none;
    color: var(--text-muted);
  }
  .ghost:hover:not(:disabled) {
    background: var(--hover);
    color: var(--text);
  }
  .oie:disabled {
    cursor: default;
  }
  .compact {
    width: var(--control-h);
    padding: 0;
    justify-content: center;
  }
  img {
    width: 18px;
    height: 18px;
    object-fit: contain;
    flex: none;
  }
  .icon {
    font-size: 18px;
    color: var(--text-muted);
  }
</style>
