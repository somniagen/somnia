<script lang="ts">
  import { BottomSheet, Button, Chip, IconButton, Menu, Modal, Slider, EmptyState, mobile, type MenuItem } from '$lib/ui'
  import type { Family, LoraRef, LocalModel } from '$lib/types'
  import { modelDefaults } from './defaults.svelte'
  import { models } from './store.svelte'

  let { family, loras = $bindable([]) }: { family: Family; loras: LoraRef[] } = $props()

  $effect(() => models.start())
  $effect(() => modelDefaults.start())

  let open = $state(false)
  let q = $state('')
  const off = $state<Record<string, number>>({})

  const byId = $derived(new Map(models.list.map((m) => [m.id, m])))
  const available = $derived.by(() => {
    const recent = models.recent()
    const used = new Set(loras.map((l) => l.id))
    const s = q.trim().toLowerCase()
    return models.list
      .filter((m) => m.kind === 'lora' && (!m.family || m.family === family) && !used.has(m.id))
      .filter((m) => !s || m.name.toLowerCase().includes(s) || m.civitai?.trainedWords.some((w) => w.toLowerCase().includes(s)))
      .sort((a, b) => {
        const ra = recent.indexOf(a.id)
        const rb = recent.indexOf(b.id)
        if (ra >= 0 || rb >= 0) return (ra < 0 ? 999 : ra) - (rb < 0 ? 999 : rb)
        return a.name.localeCompare(b.name)
      })
  })

  function add(m: LocalModel) {
    loras = [...loras, { id: m.id, weight: modelDefaults.weight(m.id) }]
    models.touch(m.id)
    q = ''
    open = false
  }
  function remove(id: string) {
    loras = loras.filter((l) => l.id !== id)
  }
  function setWeight(id: string, w: number) {
    loras = loras.map((l) => (l.id === id ? { ...l, weight: w } : l))
  }
  function toggle(l: LoraRef) {
    if (l.weight !== 0) {
      off[l.id] = l.weight
      setWeight(l.id, 0)
    } else {
      setWeight(l.id, off[l.id] ?? modelDefaults.weight(l.id))
    }
  }
  function menu(l: LoraRef): MenuItem[] {
    const d = modelDefaults.map[l.id]?.weight
    return [
      { label: 'Save weight as default', icon: 'bookmark_add', disabled: l.weight === 0 || l.weight === d, onselect: () => modelDefaults.saveWeight(l.id, l.weight) },
      { label: d === undefined ? 'Reset weight' : `Reset to ${d}`, icon: 'restart_alt', disabled: l.weight === (d ?? 1), onselect: () => setWeight(l.id, d ?? 1) },
      { label: 'Clear default weight', icon: 'bookmark_remove', danger: true, disabled: d === undefined, onselect: () => modelDefaults.clear(l.id) },
    ]
  }
  const nameOf = (id: string) => byId.get(id)?.name ?? id.replace(/^lora:/, '')
</script>

{#snippet picker()}
  <div class="search">
    <span class="icon" aria-hidden="true">search</span>
    <!-- svelte-ignore a11y_autofocus -->
    <input type="text" placeholder="Search" aria-label="Search" bind:value={q} autofocus={!mobile.current} />
  </div>
  <div class="plist">
    {#each available as m (m.id)}
      <button type="button" class="prow" onclick={() => add(m)}>
        <div class="thumb">
          {#if m.previewUrl}<img src={m.previewUrl} alt="" loading="lazy" />{:else}<span class="icon">deployed_code</span>{/if}
        </div>
        <div class="meta">
          <span class="nm">{m.name}</span>
          {#if m.civitai?.trainedWords.length}<span class="sub">{m.civitai.trainedWords.slice(0, 4).join(', ')}</span>{/if}
        </div>
        <span class="icon add">add</span>
      </button>
    {:else}
      <EmptyState compact icon="deployed_code" title={q ? 'No matches' : 'No loras'} />
    {/each}
  </div>
{/snippet}

<div class="lp">
  {#each loras as l (l.id)}
    {@const m = byId.get(l.id)}
    <div class="item" class:off={l.weight === 0}>
      <div class="thumb">
        {#if m?.previewUrl}<img src={m.previewUrl} alt="" loading="lazy" />{:else}<span class="icon">deployed_code</span>{/if}
      </div>
      <div class="body">
        <div class="head">
          <span class="nm" title={nameOf(l.id)}>{nameOf(l.id)}</span>
          <IconButton
            icon={l.weight === 0 ? 'visibility_off' : 'visibility'}
            label={l.weight === 0 ? 'Enable' : 'Disable'}
            size="sm"
            variant="ghost"
            onclick={() => toggle(l)}
          />
          <Menu items={menu(l)} placement="bottom-end" label="LoRA actions">
            {#snippet trigger({ toggle, open })}
              <IconButton icon="more_horiz" label="More" size="sm" variant="ghost" active={open} onclick={toggle} />
            {/snippet}
          </Menu>
          <IconButton icon="close" label="Remove" size="sm" variant="ghost" onclick={() => remove(l.id)} />
        </div>
        <Slider value={l.weight} min={-2} max={2} step={0.05} defaultValue={modelDefaults.weight(l.id)} editable oninput={(v: number) => setWeight(l.id, v)} />
        {#if m?.civitai?.trainedWords.length}
          <div class="words">
            {#each m.civitai.trainedWords.slice(0, 3) as w}<Chip size="sm" label={w} />{/each}
          </div>
        {/if}
      </div>
    </div>
  {/each}
  <Button icon="add" size="sm" onclick={() => (open = true)}>LoRA</Button>
</div>

{#if mobile.current}
  <BottomSheet bind:open title="LoRA" snaps={[0.6, 0.92]}>{@render picker()}</BottomSheet>
{:else}
  <Modal bind:open title="LoRA" width={460}>{@render picker()}</Modal>
{/if}

<style>
  .lp {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--sp-2);
  }
  .item {
    display: flex;
    gap: var(--sp-3);
    width: 100%;
    padding: var(--sp-2);
    border: 1px solid var(--hairline);
    border-radius: var(--r-md);
    background: var(--surface-1);
  }
  .item.off .body {
    opacity: 0.5;
  }
  .body {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 2px;
  }
  .nm {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--fs-sm);
  }
  .thumb {
    width: 48px;
    height: 48px;
    flex: none;
    display: grid;
    place-items: center;
    border-radius: var(--r-sm);
    background: var(--surface-3);
    color: var(--text-faint);
    overflow: hidden;
  }
  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .words {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .search {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    height: var(--control-h);
    padding: 0 var(--sp-3);
    margin-bottom: var(--sp-2);
    border-radius: var(--r-md);
    background: var(--surface-2);
    color: var(--text-muted);
  }
  .search input {
    flex: 1;
    min-width: 0;
    border: 0;
    outline: 0;
    background: none;
    color: var(--text);
    font: inherit;
  }
  .plist {
    display: flex;
    flex-direction: column;
    max-height: 60vh;
    overflow-y: auto;
  }
  .prow {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    padding: var(--sp-2);
    border: 0;
    border-radius: var(--r-md);
    background: none;
    color: var(--text);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .prow:hover {
    background: var(--hover);
  }
  .prow:active {
    background: var(--pressed);
  }
  .meta {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .sub {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--fs-xs);
    color: var(--text-faint);
  }
  .add {
    color: var(--text-muted);
  }
</style>
