<script lang="ts">
  import Lightbox from '$features/gallery/Lightbox.svelte'
  import ModelSelect from '$features/models/ModelSelect.svelte'
  import PromptEditor from '$features/prompt/PromptEditor.svelte'
  import PromptLibrary from '$features/prompt/PromptLibrary.svelte'
  import SendTo from '$features/prompt/SendTo.svelte'
  import { boot } from '$features/shell/boot.svelte'
  import Logo from '$features/shell/Logo.svelte'
  import { live } from '$lib/live.svelte'
  import type { Family, GalleryItem, Grid, SavedPrompt } from '$lib/types'
  import { Button, Chip, EmptyState, IconButton, InfoTip, Kbd, Menu, Segmented, Sheet, Skeleton, Spinner, mobile, toast, type MenuItem } from '$lib/ui'
  import AxisEditor from './AxisEditor.svelte'
  import { axisLabel, kindDef, rawValues, short } from './axes'
  import { grid, MAX_CELLS, WARN_CELLS } from './grid.svelte'
  import ResultTable from './ResultTable.svelte'

  let busy = $state(false)
  let library = $state(false)
  let editing = $state<number | null>(null)
  let view = $state<'setup' | 'result'>('setup')
  let lb = $state<{ items: GalleryItem[]; index: number } | null>(null)

  const ready = $derived(boot.state === 'ready')
  const b = $derived(grid.base)
  const fam = $derived(grid.family)
  const g = $derived(grid.current)
  const cells = $derived(grid.built.cells)
  const nz = $derived(g && g.axes[2] ? g.axes[2].values.length : 1)
  const z = $derived(Math.min(grid.z, nz - 1))
  const finished = $derived(g ? g.cells.filter((c) => c.status !== 'queued').length : 0)
  const families: { value: Family; label: string }[] = [
    { value: 'illustrious', label: 'Illustrious' },
    { value: 'anima', label: 'Anima' },
  ]

  $effect(() => {
    if (ready) grid.ensure()
  })

  const title = (x: Grid) => x.axes.map((a) => a.label).join(' x ')
  const statusIcon = (x: Grid) => (x.status === 'done' ? 'check' : x.status === 'failed' ? 'error' : 'progress_activity')
  const history = $derived<MenuItem[]>(
    grid.grids.length
      ? grid.grids.map((x) => ({
          label: `${title(x)} (${x.cells.length})`,
          icon: statusIcon(x),
          onselect: () => ((grid.currentId = x.id), (grid.z = 0), (view = 'result')),
        }))
      : [{ label: 'No grids yet', disabled: true }],
  )

  async function run() {
    if (busy || !ready) return
    busy = true
    try {
      await grid.run()
      view = 'result'
    } catch (e) {
      toast.error('Could not start grid', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      busy = false
    }
  }

  async function remove(x: Grid) {
    const active = x.status === 'running'
    try {
      await grid.remove(x.id)
      toast.success(active ? 'Grid cancelled' : 'Grid removed', { description: active ? undefined : 'Its images stay in the gallery' })
    } catch (e) {
      toast.error('Failed', { description: e instanceof Error ? e.message : String(e) })
    }
  }

  function loadPrompt(s: SavedPrompt) {
    grid.positive = $state.snapshot(s.positive)
    grid.negative = $state.snapshot(s.negative)
    library = false
  }

  function axisSummary(i: number) {
    const d = grid.axes[i]
    const v = rawValues(d)
    if (!v?.length) return 'No values'
    const def = kindDef(d.kind)
    const s = v.slice(0, 4).map((x) => (def.input === 'lines' ? String(x) : def.show ? def.show(x) : String(x)))
    return s.join(', ') + (v.length > 4 ? ` +${v.length - 4}` : '')
  }

  $effect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault()
        run()
      }
    }
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  })
</script>

{#snippet setup()}
  {#if !ready || !b}
    <div class="skel">
      <Skeleton height="34px" />
      <Skeleton height="120px" />
      <Skeleton height="80px" />
    </div>
  {:else}
    <section>
      <div class="sh">
        <span class="lbl">Base</span>
        <InfoTip text="A snapshot of the Generate settings every cell starts from. The axes change one setting each." />
        <span class="grow"></span>
        <IconButton icon="sync" label="Use current Generate settings" size="sm" onclick={() => (grid.pull(), toast.success('Settings pulled from Generate'))} />
      </div>
      <Segmented items={families} value={fam} onchange={(f) => grid.setFamily(f)} full size="sm" />
      <ModelSelect kind="checkpoint" family={fam} bind:value={b.model} />
      <div class="chips">
        <Chip size="sm" icon="aspect_ratio" label="{b.width}x{b.height}" />
        <Chip size="sm" icon="footprint" label="{b.steps} steps" />
        <Chip size="sm" icon="tune" label="CFG {b.cfg}" />
        <Chip size="sm" icon="blur_on" label="{b.sampler} / {b.scheduler}" />
        {#each b.loras as l (l.id)}<Chip size="sm" color="--tag-lora" label="{short(l.id)} {l.weight}" />{/each}
        {#if b.secondPass.enabled}<Chip size="sm" label="Second pass" />{/if}
        {#if b.detailers.some((d) => d.enabled)}<Chip size="sm" label="Detailer" />{/if}
        {#if b.upscale.enabled}<Chip size="sm" label="Upscale" />{/if}
        {#if b.seed >= 0}<Chip size="sm" icon="lock" label="Seed {b.seed}" />{/if}
      </div>
    </section>
    <section>
      {#key fam}
        <div class="sh">
          <span class="lbl">Prompt</span>
          <span class="grow"></span>
          <SendTo from="grid" />
          <IconButton icon="bookmarks" label="Saved prompts" size="sm" onclick={() => (library = true)} />
        </div>
        <PromptEditor kind="positive" family={fam} loras={b.loras} placeholder="Describe the image" bind:segments={grid.positive} />
        <PromptEditor kind="negative" family={fam} placeholder="Negative prompt" bind:segments={grid.negative} />
      {/key}
    </section>
    <section>
      <div class="sh">
        <span class="lbl">Axes</span>
        <InfoTip text="X makes the columns, Y the rows, Z one table per value. Every combination is queued with the same seed unless an axis changes it." />
      </div>
      {#if mobile.current}
        {#each grid.axes as d, i (i)}
          <button class="axrow" onclick={() => (editing = i)}>
            <span class="letter">{'XYZ'[i]}</span>
            <span class="axt">
              <span class="axl">{axisLabel(d)}</span>
              <span class="axv" class:err={grid.built.bad.includes(i)}>{axisSummary(i)}</span>
            </span>
            <span class="icon">chevron_right</span>
          </button>
        {/each}
      {:else}
        {#each grid.axes as _, i (i)}
          <AxisEditor index={i} onremove={grid.axes.length > 1 || i > 0 ? () => grid.removeAxis(i) : undefined} />
        {/each}
      {/if}
      {#if grid.axes.length < 3}
        <Button icon="add" size="sm" variant="ghost" onclick={() => (grid.addAxis(), mobile.current && (editing = grid.axes.length - 1))}>
          Add {'XYZ'[grid.axes.length]} axis
        </Button>
      {/if}
    </section>
  {/if}
{/snippet}

{#snippet runBar()}
  <div class="rb">
    <span class="count" class:warn={cells > WARN_CELLS} class:over={cells > MAX_CELLS}>
      <span class="icon">grid_view</span>{cells}
      {#if cells > WARN_CELLS}<InfoTip icon="warning" text={cells > MAX_CELLS ? `The limit is ${MAX_CELLS} cells.` : `${cells} images will be queued.`} />{/if}
    </span>
    <Button variant="primary" icon="play_arrow" full loading={busy} disabled={!ready || !b?.model || !cells || cells > MAX_CELLS} onclick={run} class="go">
      Run grid
      {#if !mobile.current}<Kbd>Ctrl Enter</Kbd>{/if}
    </Button>
  </div>
{/snippet}

{#snippet results()}
  <div class="tools">
    {#if mobile.current}<Logo size={22} />{/if}
    <Menu items={history} placement="bottom-start" label="Recent grids">
      {#snippet trigger({ toggle, open })}
        <IconButton icon="history" label="Recent grids" active={open} onclick={toggle} />
      {/snippet}
    </Menu>
    {#if g}
      <span class="gt">{title(g)}</span>
      {#if g.status === 'running' || g.status === 'composing'}
        <span class="prog"><Spinner size={14} />{finished}/{g.cells.length}</span>
      {/if}
      <span class="grow"></span>
      {#if nz > 1 && g.axes[2]}
        <Segmented
          items={g.axes[2].values.map((v, i) => ({ value: i, label: v.label }))}
          value={z}
          onchange={(v) => (grid.z = v)}
          size="sm"
          label={g.axes[2].label}
        />
      {/if}
      {#if g.images[z]}
        <IconButton icon="image" label="Open grid image" onclick={() => (lb = { items: g.images, index: z })} />
      {/if}
      <IconButton
        icon={g.status === 'running' ? 'stop_circle' : 'delete'}
        label={g.status === 'running' ? 'Cancel grid' : 'Remove from history'}
        variant={g.status === 'running' ? 'danger' : 'default'}
        onclick={() => remove(g)}
      />
    {:else}
      <span class="grow"></span>
    {/if}
  </div>
  <div class="table">
    {#if g}
      <ResultTable {g} {z} onopen={(items, index) => (lb = { items, index })} />
    {:else}
      <EmptyState icon="grid_view" title="No grids yet" description="Pick what to compare, then run.">
        {#if mobile.current}<Button onclick={() => (view = 'setup')}>Set up</Button>{/if}
      </EmptyState>
    {/if}
  </div>
{/snippet}

{#if mobile.current}
  <div class="gv m">
    <div class="mtabs">
      <Segmented
        items={[
          { value: 'setup' as const, label: 'Setup', icon: 'tune' },
          { value: 'result' as const, label: g && g.status === 'running' ? `Results ${finished}/${g.cells.length}` : 'Results', icon: 'grid_view' },
        ]}
        bind:value={view}
        full
        size="sm"
      />
    </div>
    {#if view === 'setup'}
      <div class="mscroll">{@render setup()}</div>
      <div class="mfoot">{@render runBar()}</div>
    {:else}
      <div class="res">{@render results()}</div>
    {/if}
  </div>
{:else}
  <div class="gv">
    <aside class="panel">
      <div class="scroll">{@render setup()}</div>
      <div class="foot">{@render runBar()}</div>
    </aside>
    <section class="main">{@render results()}</section>
  </div>
{/if}

<Sheet bind:open={() => editing !== null, (v) => !v && (editing = null)} title={editing !== null ? `${'XYZ'[editing]} axis` : ''} width={480}>
  {#if editing !== null && grid.axes[editing]}
    <div class="sheet">
      <AxisEditor
        index={editing}
        onremove={grid.axes.length > 1 || editing > 0 ? () => (grid.removeAxis(editing!), (editing = null)) : undefined}
      />
      <Button variant="primary" full onclick={() => (editing = null)}>Done</Button>
    </div>
  {/if}
</Sheet>

<Sheet bind:open={library} title="Saved prompts" width={520}>
  <PromptLibrary onload={loadPrompt} />
</Sheet>

{#if lb}
  <Lightbox items={lb.items} bind:index={lb.index} onclose={() => (lb = null)} />
{/if}

<style>
  .gv {
    display: flex;
    height: 100%;
    min-height: 0;
  }
  .panel {
    flex: none;
    width: 400px;
    display: flex;
    flex-direction: column;
    min-height: 0;
    border-right: 1px solid var(--hairline);
    background: var(--bg);
  }
  .scroll {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
  }
  .foot,
  .mfoot {
    flex: none;
    padding: var(--sp-3) var(--sp-4);
    border-top: 1px solid var(--hairline);
    background: var(--bg);
  }
  .mfoot {
    padding: var(--sp-2) var(--sp-4);
  }
  section {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    padding: var(--sp-4);
    border-bottom: 1px solid var(--hairline);
  }
  .main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    padding: 0;
    border: 0;
    gap: 0;
  }
  .sh {
    display: flex;
    align-items: center;
    gap: var(--sp-1);
    min-height: 28px;
  }
  .lbl {
    font-size: var(--fs-sm);
    color: var(--text-muted);
    font-weight: 500;
  }
  .grow {
    flex: 1;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--sp-1);
  }
  .skel {
    display: flex;
    flex-direction: column;
    gap: var(--sp-4);
    padding: var(--sp-4);
  }
  .rb {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
  }
  .rb :global(.go:not(:disabled)) {
    height: 42px;
    font-weight: 600;
  }
  .count {
    display: flex;
    align-items: center;
    gap: var(--sp-1);
    font-variant-numeric: tabular-nums;
    color: var(--text-muted);
    white-space: nowrap;
  }
  .count .icon {
    font-size: 18px;
  }
  .count.warn {
    color: var(--warning);
  }
  .count.over {
    color: var(--danger);
  }
  .tools {
    flex: none;
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: 56px;
    padding: var(--sp-2) var(--sp-3);
  }
  .gt {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
  }
  .prog {
    display: flex;
    align-items: center;
    gap: var(--sp-1);
    color: var(--text-muted);
    font-size: var(--fs-sm);
    font-variant-numeric: tabular-nums;
  }
  .table {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .table > :global(*) {
    flex: 1;
    min-height: 0;
  }
  .table > :global(.empty) {
    flex: 0;
    margin: auto;
  }
  .gv.m {
    flex-direction: column;
  }
  .mtabs {
    flex: none;
    padding: var(--sp-2) var(--sp-3);
    border-bottom: 1px solid var(--hairline);
  }
  .mscroll {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .res {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .m .tools {
    min-height: 48px;
    flex-wrap: wrap;
  }
  .axrow {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    min-height: var(--touch);
    padding: var(--sp-2) var(--sp-3);
    border: 1px solid var(--hairline);
    border-radius: var(--r-lg);
    background: var(--grad-1);
    box-shadow: var(--sheen);
    color: var(--text);
    font: inherit;
    text-align: left;
    cursor: pointer;
    transition: transform var(--dur-fast) var(--ease);
  }
  .axrow:active {
    transform: scale(0.98);
    background: var(--grad-2);
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
  .axt {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .axl {
    font-weight: 500;
  }
  .axv {
    color: var(--text-muted);
    font-size: var(--fs-sm);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .axv.err {
    color: var(--danger);
  }
  .axrow > .icon {
    color: var(--text-faint);
  }
  .sheet {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
  }
</style>
