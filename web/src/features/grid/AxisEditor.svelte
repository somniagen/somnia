<script lang="ts">
  import { models } from '$features/models/store.svelte'
  import TextInput from '$features/shell/TextInput.svelte'
  import { session } from '$lib/session.svelte'
  import { Chip, IconButton, InfoTip, Select } from '$lib/ui'
  import { KINDS, kindDef, rawValues, short, type AxisKind } from './axes'
  import { grid } from './grid.svelte'

  let { index, onremove }: { index: number; onremove?: () => void } = $props()

  $effect(() => models.start())

  const d = $derived(grid.axes[index])
  const def = $derived(kindDef(d.kind))
  const base = $derived(grid.base)
  const info = $derived(session.presets?.families[grid.family] ?? null)
  const kinds = KINDS.map((k) => ({ value: k.kind, label: k.label }))
  const letter = $derived('XYZ'[index])

  const options = $derived.by((): { value: string; label: string }[] => {
    if (d.kind === 'sampler') return (info?.samplers ?? []).map((s) => ({ value: s, label: s }))
    if (d.kind === 'scheduler') return (info?.schedulers ?? []).map((s) => ({ value: s, label: s }))
    if (d.kind === 'model')
      return models.list
        .filter((m) => m.kind === 'checkpoint' && (!m.family || m.family === grid.family))
        .map((m) => ({ value: m.id, label: m.name }))
    if (d.kind === 'vae')
      return [{ value: '', label: 'Built in' }, ...models.list.filter((m) => m.kind === 'vae').map((m) => ({ value: m.id, label: m.name }))]
    return []
  })
  const loras = $derived((base?.loras ?? []).map((l) => ({ value: l.id, label: short(l.id) })))
  const values = $derived(rawValues(d))
  const bad = $derived(def.input !== 'select' && d.text.trim() !== '' && !values?.length)

  function setKind(k: AxisKind) {
    const same = kindDef(k).input === def.input && def.input !== 'select'
    grid.axes[index] = { kind: k, text: same ? d.text : '', picks: [], lora: k === 'lora' ? (base?.loras[0]?.id ?? null) : null }
  }

  function toggle(v: string) {
    d.picks = d.picks.includes(v) ? d.picks.filter((x) => x !== v) : [...d.picks, v]
  }

  const preview = $derived(values && values.length ? values.slice(0, 12).map((v) => (def.show ? def.show(v) : String(v))).join(', ') + (values.length > 12 ? ', ...' : '') : '')
</script>

<div class="ax">
  <div class="head">
    <span class="letter">{letter}</span>
    <Select items={kinds} value={d.kind} onchange={setKind} size="sm" class="kind" label="{letter} axis" />
    {#if values?.length}<span class="n" class:on={values.length > 1}>{values.length}</span>{/if}
    {#if index > 0}
      <IconButton icon="swap_vert" label="Swap with {'XYZ'[index - 1]}" size="sm" variant="ghost" onclick={() => grid.swap(index, index - 1)} />
    {/if}
    {#if onremove}<IconButton icon="close" label="Remove axis" size="sm" variant="ghost" onclick={onremove} />{/if}
  </div>

  {#if d.kind === 'lora'}
    {#if loras.length}
      <Select items={loras} bind:value={d.lora} size="sm" placeholder="LoRA" />
    {:else}
      <div class="note">Add a LoRA in Generate, then pull its settings</div>
    {/if}
  {/if}

  {#if def.input === 'select'}
    <div class="chips">
      {#each options as o (o.value)}
        <Chip label={o.label} size="sm" selected={d.picks.includes(o.value)} onclick={() => toggle(o.value)} />
      {/each}
      {#if options.length > 2}
        <IconButton
          icon={d.picks.length === options.length ? 'deselect' : 'select_all'}
          label={d.picks.length === options.length ? 'Clear' : 'Select all'}
          size="sm"
          variant="ghost"
          onclick={() => (d.picks = d.picks.length === options.length ? [] : options.map((o) => o.value))}
        />
      {/if}
    </div>
  {:else}
    <div class="inp">
      <TextInput bind:value={d.text} multiline={def.input === 'lines'} rows={3} placeholder={def.placeholder} mono class={bad ? 'bad' : ''} />
      {#if def.input === 'lines'}
        <span class="tip"><InfoTip text="One value per line. The first line is searched for in the prompt and replaced by each line, like Prompt S/R." /></span>
      {:else if def.input !== 'size'}
        <span class="tip"><InfoTip text="Comma separated values, or ranges: 1-10 (+2) steps by 2, 4-8 [5] gives 5 evenly spaced values." /></span>
      {/if}
    </div>
    {#if bad}
      <div class="note err">Could not read these values</div>
    {:else if preview && def.input !== 'lines'}
      <div class="note">{preview}</div>
    {/if}
  {/if}
</div>

<style>
  .ax {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    padding: var(--sp-3);
    border: 1px solid var(--hairline);
    border-radius: var(--r-lg);
    background: var(--grad-1);
    box-shadow: var(--sheen);
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
  }
  .head :global(.kind) {
    flex: 1;
    min-width: 0;
  }
  .letter {
    flex: none;
    display: grid;
    place-items: center;
    width: 24px;
    height: 24px;
    border-radius: var(--r-sm);
    background: var(--grad-3);
    font-weight: 600;
    font-size: var(--fs-sm);
  }
  .n {
    min-width: 22px;
    padding: 0 6px;
    border-radius: var(--r-sm);
    background: var(--surface-3);
    color: var(--text-muted);
    font-size: var(--fs-xs);
    line-height: 20px;
    text-align: center;
    font-variant-numeric: tabular-nums;
  }
  .n.on {
    color: var(--text);
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--sp-1);
    max-height: 180px;
    overflow-y: auto;
  }
  .inp {
    display: flex;
    align-items: flex-start;
    gap: var(--sp-2);
  }
  .inp :global(.ti) {
    flex: 1;
  }
  .inp :global(.bad) {
    box-shadow: inset 0 0 0 1px var(--danger);
  }
  .tip {
    margin-top: 7px;
  }
  .note {
    font-size: var(--fs-xs);
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
  }
  .note.err {
    color: var(--danger);
  }
</style>
