<script lang="ts">
  import { IconButton, InfoTip, Menu, Select, type MenuItem } from '$lib/ui'
  import type { Family, ModelKind } from '$lib/types'
  import { modelDefaults } from './defaults.svelte'
  import { models } from './store.svelte'

  let {
    kind,
    family = null,
    value = $bindable(''),
    allowNone = false,
    defaults = false,
  }: { kind: ModelKind; family?: Family | null; value: string | null; allowNone?: boolean; defaults?: boolean } = $props()

  $effect(() => models.start())
  $effect(() => {
    if (defaults) modelDefaults.start()
  })

  const NONE = '__none__'
  const byId = $derived(new Map(models.list.map((m) => [m.id, m])))
  const items = $derived.by(() => {
    const out: { value: string; label: string }[] = []
    if (allowNone) out.push({ value: NONE, label: 'None' })
    if (kind === 'upscaler') out.push({ value: 'latent', label: 'Latent' })
    for (const m of models.list) {
      if (m.kind !== kind) continue
      if (family && m.family && m.family !== family) continue
      out.push({ value: m.id, label: m.name })
    }
    if (value && value !== NONE && !out.some((i) => i.value === value)) out.push({ value, label: value.replace(/^[a-z_]+:/, '') })
    return out
  })
  const current = $derived(value ?? NONE)
  const showThumb = $derived(kind === 'checkpoint' || kind === 'lora')

  const saved = $derived(!!(value && modelDefaults.map[value]?.params))
  const menu = $derived<MenuItem[]>([
    { label: 'Save as model defaults', icon: 'bookmark_add', disabled: !value, onselect: () => value && modelDefaults.saveParams(value) },
    { label: 'Save with size', icon: 'aspect_ratio', disabled: !value, onselect: () => value && modelDefaults.saveParams(value, true) },
    { label: 'Apply model defaults', icon: 'restart_alt', disabled: !saved, onselect: () => value && modelDefaults.apply(value) },
    { separator: true },
    { label: 'Clear model defaults', icon: 'bookmark_remove', danger: true, disabled: !saved, onselect: () => value && modelDefaults.clear(value) },
  ])

  function pick(v: string) {
    value = v === NONE ? null : v
    if (defaults && value) modelDefaults.apply(value)
  }
</script>

{#if defaults}
  <div class="wrap">
    <div class="sel">{@render select()}</div>
    <Menu items={menu} placement="bottom-end" label="Model defaults">
      {#snippet trigger({ toggle, open })}
        <IconButton icon={saved ? 'bookmark_added' : 'bookmark'} label="Model defaults" active={open} onclick={toggle} />
      {/snippet}
    </Menu>
    <InfoTip text="Sampling settings saved for this checkpoint, applied when you switch to it. Synced across devices." />
  </div>
{:else}
  {@render select()}
{/if}

{#snippet select()}
<Select
  {items}
  value={current}
  searchable={items.length > 6}
  placeholder="Select"
  style="width: 100%"
  onchange={pick}
>
  {#snippet item(it)}
    {@const m = byId.get(it.value)}
    <div class="row">
      {#if showThumb}
        <div class="thumb">
          {#if m?.previewUrl}<img src={m.previewUrl} alt="" loading="lazy" />{:else}<span class="icon">{it.value === NONE ? 'block' : 'deployed_code'}</span>{/if}
        </div>
      {/if}
      <span class="nm">{it.label}</span>
    </div>
  {/snippet}
</Select>
{/snippet}

<style>
  .wrap {
    display: flex;
    align-items: center;
    gap: 2px;
  }
  .sel {
    flex: 1;
    min-width: 0;
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    min-width: 0;
    flex: 1;
  }
  .thumb {
    width: 32px;
    height: 32px;
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
  .nm {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
