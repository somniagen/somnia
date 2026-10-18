<script lang="ts">
  import { Button, EmptyState, IconButton, Menu, SearchField, Skeleton, toast, type MenuItem } from '$lib/ui'
  import { session } from '$lib/session.svelte'
  import { segmentsToText } from '$lib/session.svelte'
  import type { SavedPrompt } from '$lib/types'
  import { deletePrompt, library, refreshLibrary, renamePrompt, restorePrompt, saveCurrent } from './library.svelte'

  let { onload }: { onload?: (p: SavedPrompt) => void } = $props()

  let q = $state('')
  let name = $state('')
  let saving = $state(false)
  let editing = $state<string | null>(null)
  let editName = $state('')

  $effect(() => {
    if (!library.loaded && !library.loading) refreshLibrary().catch(() => toast.error('Could not load prompts'))
  })

  const shown = $derived.by(() => {
    const s = q.trim().toLowerCase()
    const list = [...library.items].sort((a, b) => b.updatedAt - a.updatedAt)
    if (!s) return list
    return list.filter((p) => p.name.toLowerCase().includes(s) || segmentsToText(p.positive).toLowerCase().includes(s))
  })

  async function save() {
    if (saving) return
    saving = true
    try {
      await saveCurrent(name || `Prompt ${library.items.length + 1}`)
      name = ''
    } catch (e) {
      toast.error('Could not save', { description: (e as Error).message })
    } finally {
      saving = false
    }
  }

  function startRename(p: SavedPrompt) {
    editing = p.id
    editName = p.name
  }
  async function commitRename(p: SavedPrompt) {
    if (editing !== p.id) return
    const n = editName.trim()
    editing = null
    if (!n || n === p.name) return
    try {
      await renamePrompt(p, n)
    } catch (e) {
      toast.error('Rename failed', { description: (e as Error).message })
    }
  }
  async function remove(p: SavedPrompt) {
    try {
      await deletePrompt(p)
      toast('Prompt deleted', { description: p.name, action: { label: 'Undo', run: () => restorePrompt(p) } })
    } catch (e) {
      toast.error('Delete failed', { description: (e as Error).message })
    }
  }

  function items(p: SavedPrompt): MenuItem[] {
    return [
      { label: 'Load', icon: 'input', onselect: () => onload?.(p) },
      { label: 'Rename', icon: 'edit', onselect: () => startRename(p) },
      { separator: true },
      { label: 'Delete', icon: 'delete', danger: true, onselect: () => remove(p) },
    ]
  }

  const preview = (p: SavedPrompt) => {
    const free = segmentsToText(p.positive.filter((s) => !s.locked))
    return free || segmentsToText(p.positive)
  }
  const lockedCount = (p: SavedPrompt) => p.positive.filter((s) => s.locked).length + p.negative.filter((s) => s.locked).length

  function focusEl(n: HTMLInputElement) {
    n.focus()
    n.select()
  }
</script>

<div class="lib">
  <form
    class="row"
    onsubmit={(e) => {
      e.preventDefault()
      save()
    }}
  >
    <input class="inp" bind:value={name} placeholder="Name" aria-label="Prompt name" />
    <Button size="sm" variant="primary" icon="bookmark_add" type="submit" loading={saving} disabled={!session.params}>Save</Button>
  </form>
  {#if library.items.length > 4}
    <SearchField size="sm" class="search" aria-label="Search prompts" bind:value={q} />
  {/if}

  <div class="list">
    {#if !library.loaded && library.loading}
      {#each [0, 1, 2] as i (i)}<Skeleton height="44px" radius="var(--r-md)" />{/each}
    {:else if !library.items.length}
      <EmptyState compact icon="bookmarks" title="No saved prompts" />
    {:else if !shown.length}
      <EmptyState compact icon="search_off" title="No matches" />
    {:else}
      {#each shown as p (p.id)}
        <div class="item">
          {#if editing === p.id}
            <input
              class="inp grow"
              bind:value={editName}
              aria-label="New name"
              use:focusEl
              onkeydown={(e) => {
                if (e.key === 'Enter') commitRename(p)
                else if (e.key === 'Escape') {
                  e.stopPropagation()
                  editing = null
                }
              }}
              onblur={() => commitRename(p)}
            />
          {:else}
            <button type="button" class="main" onclick={() => onload?.(p)} ondblclick={() => startRename(p)}>
              <span class="nm">
                {p.name}
                {#if p.family && p.family !== session.family}<span class="fam">{p.family}</span>{/if}
              </span>
              <span class="pv">
                {#if lockedCount(p)}<span class="icon lock" aria-label="Has boilerplate">lock</span>{/if}{preview(p) || '...'}
              </span>
            </button>
            <Menu items={items(p)} placement="bottom-end" label="Prompt actions">
              {#snippet trigger({ toggle, open })}
                <IconButton icon="more_horiz" label="More" size="sm" active={open} onclick={toggle} />
              {/snippet}
            </Menu>
          {/if}
        </div>
      {/each}
    {/if}
  </div>
</div>

<style>
  .lib {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    min-width: 0;
  }
  .row {
    display: flex;
    gap: var(--sp-2);
  }
  .inp {
    flex: 1;
    min-width: 0;
    height: var(--control-h-sm);
    padding: 0 8px;
    border: 0;
    border-radius: var(--r-sm);
    background: var(--surface-2);
    color: var(--text);
    font: inherit;
    font-size: var(--fs-sm);
    outline: none;
  }
  .inp:focus-visible {
    box-shadow: inset 0 0 0 1px var(--focus-line);
    background: var(--surface-3);
  }
  .inp::placeholder {
    color: var(--text-faint);
  }
  .list {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .item {
    display: flex;
    align-items: center;
    gap: 2px;
    border-radius: var(--r-md);
    transition: background var(--dur-fast) var(--ease);
  }
  .item:hover {
    background: var(--hover);
  }
  .grow {
    margin: 4px;
  }
  .main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 1px;
    padding: 6px 8px;
    border: 0;
    border-radius: var(--r-md);
    background: none;
    color: var(--text);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .main:active {
    background: var(--pressed);
  }
  .nm,
  .pv {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .nm {
    font-size: var(--fs-sm);
  }
  .fam {
    margin-left: 6px;
    color: var(--text-faint);
    font-size: var(--fs-xs);
  }
  .pv {
    color: var(--text-faint);
    font-size: var(--fs-xs);
  }
  .lock {
    font-size: 12px;
    margin-right: 3px;
    vertical-align: -2px;
  }
  @media (pointer: coarse) {
    .inp,
    .lib :global(.search) {
      height: var(--control-h);
    }
    .main {
      padding: 9px 8px;
    }
  }
</style>
