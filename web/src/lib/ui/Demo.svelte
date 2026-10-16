<script lang="ts">
  import {
    AspectPicker,
    BottomSheet,
    Button,
    Card,
    Checkbox,
    Chip,
    Combobox,
    Dropzone,
    EmptyState,
    Field,
    GlowProgressBar,
    IconButton,
    ImageTile,
    InfoTip,
    Kbd,
    Menu,
    Modal,
    NumberField,
    SeedField,
    Segmented,
    Select,
    Sheet,
    Skeleton,
    Slider,
    Spinner,
    Surface,
    Tabs,
    Toaster,
    Toggle,
    WheelPicker,
    toast,
    tooltip,
    type MenuItem,
  } from './index'

  const samplers = ['Euler a', 'Euler', 'DPM++ 2M', 'DPM++ 2M SDE', 'DPM++ 3M SDE', 'DPM++ SDE', 'DDIM', 'UniPC', 'LCM', 'Heun', 'LMS', 'DPM2 a']
  const schedulers = [
    { value: 'normal', label: 'Normal' },
    { value: 'karras', label: 'Karras' },
    { value: 'exponential', label: 'Exponential' },
    { value: 'sgm', label: 'SGM uniform', hint: 'anima' },
    { value: 'beta', label: 'Beta' },
  ]
  const tags = [
    '1girl', 'solo', 'long hair', 'looking at viewer', 'smile', 'blush', 'short hair', 'open mouth', 'blue eyes',
    'simple background', 'brown hair', 'black hair', 'blonde hair', 'masterpiece', 'best quality', 'highres', 'absurdres',
  ]

  let loading = $state(false)
  let pressed = $state(false)
  let on = $state(true)
  let hires = $state(false)
  let agree = $state(true)
  let mixed = $state(true)
  let cfg = $state(5)
  let steps = $state(28)
  let denoise = $state(0.35)
  let batch = $state(2)
  let scale = $state(1.5)
  let sampler = $state('Euler a')
  let scheduler = $state('karras')
  let selSampler = $state('DPM++ 2M')
  let family = $state('illustrious')
  let view = $state('grid')
  let tab = $state('gen')
  let seed = $state(1234567890)
  let locked = $state(false)
  let w = $state(832)
  let h = $state(1216)
  let picked = $state<string[]>(['masterpiece', 'best quality'])
  let q = $state('')
  let modal = $state(false)
  let sheet = $state(false)
  let bottom = $state(false)
  let menuOpen = $state(false)
  let ctx = $state<{ x: number; y: number } | null>(null)
  let ctxOpen = $state(false)
  let files = $state<string[]>([])
  let selected = $state([false, true, false, false])

  let progress = $state(0)
  let pstatus = $state<'idle' | 'running' | 'success' | 'error'>('idle')
  let indet = $state(false)
  let timer: ReturnType<typeof setInterval> | undefined

  function run(fail = false) {
    clearInterval(timer)
    indet = false
    progress = 0
    pstatus = 'running'
    timer = setInterval(() => {
      progress = Math.min(1, progress + 0.04 + Math.random() * 0.05)
      if (fail && progress > 0.6) {
        clearInterval(timer)
        pstatus = 'error'
        toast.error('Generation failed', { description: 'CUDA out of memory' })
      } else if (progress >= 1) {
        clearInterval(timer)
        pstatus = 'success'
        toast.success('Done', { action: { label: 'Open', run: () => toast.info('Opened') } })
      }
    }, 160)
  }
  function runIndet() {
    clearInterval(timer)
    indet = true
    pstatus = 'running'
    setTimeout(() => (pstatus = 'success'), 2600)
  }
  $effect(() => () => clearInterval(timer))

  async function searchTags(s: string, signal: AbortSignal) {
    await new Promise((r) => setTimeout(r, 250))
    if (signal.aborted) return []
    const t = s.toLowerCase().replace(/_/g, ' ')
    return tags.filter((x) => x.includes(t)).slice(0, 8)
  }

  const menuItems: MenuItem[] = [
    { label: 'Reuse parameters', icon: 'replay', shortcut: 'R', onselect: () => toast('Parameters loaded') },
    { label: 'Upscale', icon: 'hd', onselect: () => toast('Queued upscale') },
    { label: 'Inpaint', icon: 'brush' },
    { label: 'Copy seed', icon: 'content_copy', disabled: true },
    { separator: true },
    { label: 'Delete', icon: 'delete', danger: true, shortcut: 'Del', onselect: () => toast.error('Deleted') },
  ]

  const imgs = [
    { a: 832 / 1216, src: 'https://picsum.photos/seed/somnia1/416/608' },
    { a: 1, src: 'https://picsum.photos/seed/somnia2/512/512' },
    { a: 1216 / 832, src: 'https://picsum.photos/seed/somnia3/608/416' },
    { a: 832 / 1216, src: null },
  ]
</script>

<GlowProgressBar value={indet ? null : progress} status={pstatus} />
<Toaster />

<div class="page">
  <header class="top">
    <h1>Somnia UI</h1>
    <span class="muted">primitives</span>
    <div class="grow"></div>
    <Button variant="ghost" icon="arrow_back" onclick={() => (location.hash = '')}>Back</Button>
  </header>

  <div class="grid">
    <Card title="Buttons" icon="smart_button">
      <div class="row">
        <Button variant="primary" icon="auto_awesome">Generate</Button>
        <Button icon="add">Queue</Button>
        <Button variant="ghost">Cancel</Button>
        <Button variant="danger" icon="delete">Delete</Button>
      </div>
      <div class="row">
        <Button size="sm" variant="primary" {loading} onclick={() => ((loading = true), setTimeout(() => (loading = false), 1500))}>
          {loading ? 'Working' : 'Load'}
        </Button>
        <Button size="sm" iconRight="expand_more">Options</Button>
        <Button size="sm" disabled>Disabled</Button>
      </div>
      <div class="row">
        <IconButton icon="favorite" label="Favorite" active={pressed} onclick={() => (pressed = !pressed)} />
        <IconButton icon="download" label="Download" />
        <IconButton icon="settings" label="Settings" variant="default" />
        <IconButton icon="delete" label="Delete" variant="danger" />
        <IconButton icon="send" label="Send" variant="primary" size="sm" />
        <span class="muted" use:tooltip={'Tooltips work on anything'}>hover me</span>
      </div>
    </Card>

    <Card title="Toggles" icon="toggle_on">
      <div class="col">
        <Toggle bind:checked={on} label="Keep models loaded" />
        <Toggle bind:checked={hires} label="Second pass" size="sm" />
        <Checkbox bind:checked={agree} label="Save metadata" />
        <Checkbox bind:checked={mixed} indeterminate={mixed} label="Partial selection" onchange={() => (mixed = false)} />
        <Checkbox disabled label="Disabled" />
      </div>
    </Card>

    <Card title="Sliders" icon="tune">
      <div class="col">
        <Field label="CFG" info="How strongly the image follows the prompt. 4 to 7 works well for Illustrious.">
          {#snippet children(id)}
            <Slider {id} label="CFG" bind:value={cfg} min={1} max={12} step={0.5} defaultValue={5} />
          {/snippet}
        </Field>
        <Field label="Steps">
          {#snippet children(id)}
            <Slider {id} label="Steps" bind:value={steps} min={1} max={60} defaultValue={28} marks={[{ value: 20, label: '20' }, { value: 28, label: '28' }, { value: 40, label: '40' }]} />
          {/snippet}
        </Field>
        <Field label="Denoise" info="Shift-drag for fine control, double click to reset.">
          {#snippet children(id)}
            <Slider {id} label="Denoise" bind:value={denoise} min={0} max={1} step={0.01} defaultValue={0.35} />
          {/snippet}
        </Field>
      </div>
    </Card>

    <Card title="Numbers" icon="pin">
      <div class="col">
        <div class="row">
          <NumberField label="Batch" bind:value={batch} min={1} max={8} defaultValue={1} />
          <NumberField label="Scale" icon="zoom_in" bind:value={scale} min={1} max={4} step={0.05} suffix="x" defaultValue={1.5} />
        </div>
        <Field label="Seed" info="Dice picks a new seed. Unlocked seeds change every run.">
          {#snippet children(id)}
            <SeedField {id} bind:value={seed} bind:locked />
          {/snippet}
        </Field>
        <span class="muted small">Drag the label to scrub, <Kbd>Shift</Kbd> for fine, wheel when focused.</span>
      </div>
    </Card>

    <Card title="Pickers" icon="list">
      <div class="col">
        <div class="row">
          <Field label="Sampler" style="flex: 1">
            {#snippet children(id)}
              <Select {id} label="Sampler" items={samplers} bind:value={selSampler} />
            {/snippet}
          </Field>
          <Field label="Scheduler" style="flex: 1">
            {#snippet children(id)}
              <Select {id} label="Scheduler" items={schedulers} bind:value={scheduler} />
            {/snippet}
          </Field>
        </div>
        <div class="row wheels">
          <WheelPicker label="Sampler" items={samplers} bind:value={sampler} style="flex: 1" />
          <WheelPicker label="Scheduler" items={schedulers} bind:value={scheduler} visible={5} style="flex: 1">
            {#snippet item(it, sel)}
              <span class:accent={sel}>{it.label}</span>
            {/snippet}
          </WheelPicker>
        </div>
        <span class="muted small">{sampler} / {scheduler}</span>
      </div>
    </Card>

    <Card title="Segments and tabs" icon="tab">
      <div class="col">
        <Segmented
          items={[
            { value: 'illustrious', label: 'Illustrious' },
            { value: 'anima', label: 'Anima' },
          ]}
          bind:value={family}
          full
        />
        <Segmented
          size="sm"
          iconOnly
          items={[
            { value: 'grid', label: 'Grid', icon: 'grid_view' },
            { value: 'list', label: 'List', icon: 'view_list' },
            { value: 'single', label: 'Single', icon: 'crop_square' },
          ]}
          bind:value={view}
        />
        <Tabs
          items={[
            { value: 'gen', label: 'Generate' },
            { value: 'inpaint', label: 'Inpaint' },
            { value: 'models', label: 'Models' },
          ]}
          bind:value={tab}
        >
          {#snippet children(v)}
            <span class="muted">Panel: {v}</span>
          {/snippet}
        </Tabs>
      </div>
    </Card>

    <Card title="Aspect" icon="aspect_ratio">
      <AspectPicker bind:width={w} bind:height={h} />
    </Card>

    <Card title="Tags" icon="sell">
      <div class="col">
        <Combobox
          bind:value={q}
          placeholder="Add tag"
          search={searchTags}
          clearOnSelect
          onselect={(t) => !picked.includes(t) && (picked = [...picked, t])}
        >
          {#snippet item(t, active)}
            <span class="tagdot"></span>
            <span style="flex: 1">{t}</span>
            {#if active}<Kbd>Enter</Kbd>{/if}
          {/snippet}
        </Combobox>
        <div class="row wrap">
          {#each picked as t (t)}
            <Chip label={t} color="--tag-meta" locked={t === 'masterpiece'} removable onremove={() => (picked = picked.filter((x) => x !== t))} />
          {/each}
          <Chip label="1girl" color="--tag-general" />
          <Chip label="hatsune miku" color="--tag-character" removable />
          <Chip label="vocaloid" color="--tag-copyright" />
          <Chip label="wlop" color="--tag-artist" selected onclick={() => toast('Artist clicked')} />
          <Chip label="add_detail:0.6" color="--tag-lora" icon="extension" size="sm" />
          <Chip label="plain" />
        </div>
      </div>
    </Card>

    <Card title="Images" icon="photo_library">
      <div class="tiles">
        {#each imgs as im, i (i)}
          <ImageTile
            src={im.src}
            aspect={im.a}
            alt="Sample {i + 1}"
            selectable
            bind:selected={selected[i]}
            onclick={() => toast('Open image ' + (i + 1))}
          >
            {#snippet actions()}
              <IconButton icon="replay" label="Reuse" size="sm" />
              <IconButton icon="download" label="Download" size="sm" />
              <IconButton icon="delete" label="Delete" size="sm" variant="danger" />
            {/snippet}
          </ImageTile>
        {/each}
      </div>
    </Card>

    <Card title="Dropzone" icon="upload">
      <div class="col">
        <Dropzone onfiles={(f) => (files = f.map((x) => x.name))} multiple />
        <Dropzone compact title="Drop to reuse params" onfiles={(f) => toast.info(f[0].name)} paste={false} />
        {#if files.length}<span class="muted small">{files.join(', ')}</span>{/if}
      </div>
    </Card>

    <Card title="Overlays" icon="layers">
      <div class="row wrap">
        <Button onclick={() => (modal = true)}>Modal</Button>
        <Button onclick={() => (bottom = true)}>Bottom sheet</Button>
        <Button onclick={() => (sheet = true)}>Sheet</Button>
        <Menu items={menuItems} bind:open={menuOpen} label="Image actions">
          {#snippet trigger({ open, toggle })}
            <Button iconRight="expand_more" aria-haspopup="menu" aria-expanded={open} onclick={toggle}>Menu</Button>
          {/snippet}
        </Menu>
      </div>
      <div
        class="ctx"
        role="presentation"
        oncontextmenu={(e) => {
          e.preventDefault()
          ctx = { x: e.clientX, y: e.clientY }
          ctxOpen = true
        }}
      >
        Right click here
      </div>
      <Menu items={menuItems} bind:open={ctxOpen} anchor={ctx} />
    </Card>

    <Card title="Feedback" icon="notifications">
      <div class="col">
        <div class="row wrap">
          <Button size="sm" variant="primary" onclick={() => run()}>Run</Button>
          <Button size="sm" onclick={runIndet}>Indeterminate</Button>
          <Button size="sm" variant="danger" onclick={() => run(true)}>Fail</Button>
        </div>
        <GlowProgressBar fixed={false} value={indet ? null : progress} status={pstatus === 'idle' ? 'running' : pstatus} height={4} />
        <div class="row wrap">
          <Button size="sm" onclick={() => toast.success('Saved prompt')}>Success</Button>
          <Button size="sm" onclick={() => toast.error('Download failed', { description: 'HTTP 503' })}>Error</Button>
          <Button size="sm" onclick={() => toast.info('Model unloaded', { action: { label: 'Undo', run: () => toast('Reloaded') } })}>Info</Button>
        </div>
        <div class="row">
          <Spinner />
          <Spinner size={24} />
          <span class="muted small">Press <Kbd>Ctrl</Kbd> <Kbd>Enter</Kbd> to generate</span>
        </div>
      </div>
    </Card>

    <Card title="Surfaces" icon="layers">
      <div class="col">
        <div class="row">
          <Surface level={0} padding="10px" style="flex: 1">0</Surface>
          <Surface level={1} padding="10px" style="flex: 1">1</Surface>
          <Surface level={2} padding="10px" style="flex: 1">2</Surface>
          <Surface level={3} padding="10px" style="flex: 1">3</Surface>
          <Surface level={4} padding="10px" style="flex: 1">4</Surface>
        </div>
        <Surface level={2} padding="12px" interactive role="button" tabindex={0}>Interactive surface</Surface>
        <div class="col tight">
          <Skeleton width="60%" />
          <Skeleton />
          <div class="row wheels"><Skeleton circle width="32px" style="flex: none" /><Skeleton height="32px" /></div>
        </div>
      </div>
    </Card>

    <Card title="Empty state" icon="inbox">
      <EmptyState icon="image" title="No images yet" description="Write a prompt and press Generate." compact>
        <Button variant="primary" size="sm" icon="auto_awesome">Generate</Button>
      </EmptyState>
    </Card>

    <Card title="Info" icon="info">
      <p class="muted">
        Explanations hide behind <InfoTip text="Like this. Hover or focus on desktop, tap on mobile." /> icons.
      </p>
    </Card>
  </div>
</div>

<Modal bind:open={modal} title="Delete 3 images?">
  <p class="muted">They will be moved to trash.</p>
  {#snippet footer()}
    <Button variant="ghost" onclick={() => (modal = false)}>Cancel</Button>
    <Button variant="danger" icon="delete" onclick={() => ((modal = false), toast.error('Deleted 3 images'))}>Delete</Button>
  {/snippet}
</Modal>

<BottomSheet bind:open={bottom} title="Sampler" snaps={[0.45, 0.9]}>
  <div class="col">
    {#each samplers as s (s)}
      <Button variant={s === sampler ? 'primary' : 'ghost'} full onclick={() => ((sampler = s), (bottom = false))}>{s}</Button>
    {/each}
  </div>
</BottomSheet>

<Sheet bind:open={sheet} title="Second pass">
  <div class="col">
    <Toggle bind:checked={hires} label="Enabled" />
    <Field label="Denoise">
      {#snippet children(id)}
        <Slider {id} label="Denoise" bind:value={denoise} min={0} max={1} step={0.01} defaultValue={0.35} />
      {/snippet}
    </Field>
    <Field label="Sampler">
      {#snippet children(id)}
        <Select {id} label="Sampler" items={samplers} bind:value={selSampler} />
      {/snippet}
    </Field>
  </div>
  {#snippet footer()}
    <Button variant="primary" onclick={() => (sheet = false)}>Apply</Button>
  {/snippet}
</Sheet>

<style>
  .page {
    max-width: 1280px;
    margin: 0 auto;
    padding: var(--sp-5) var(--sp-4) 120px;
  }
  .top {
    display: flex;
    align-items: baseline;
    gap: var(--sp-3);
    margin-bottom: var(--sp-5);
  }
  h1 {
    margin: 0;
    font-size: var(--fs-xl);
    font-weight: 600;
  }
  .grow {
    flex: 1;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(340px, 100%), 1fr));
    gap: var(--sp-4);
    align-items: start;
  }
  .row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--sp-2);
    min-width: 0;
  }
  .row + .row {
    margin-top: var(--sp-3);
  }
  .col > .row + .row {
    margin-top: 0;
  }
  .wrap {
    flex-wrap: wrap;
  }
  .col {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
  }
  .tight {
    gap: var(--sp-2);
  }
  .wheels {
    align-items: stretch;
  }
  .muted {
    color: var(--text-muted);
    margin: 0;
  }
  .small {
    font-size: var(--fs-sm);
  }
  .accent {
    color: var(--accent-strong);
  }
  .tagdot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--tag-general);
  }
  .grid > :global(*) {
    min-width: 0;
  }
  .wheels {
    flex-wrap: nowrap;
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--sp-2);
    align-items: start;
  }
  .ctx {
    display: grid;
    place-items: center;
    height: 72px;
    margin-top: var(--sp-3);
    border-radius: var(--r-md);
    background: var(--grad-2);
    color: var(--text-faint);
    font-size: var(--fs-sm);
    user-select: none;
  }
  @media (max-width: 640px) {
    .page {
      padding: var(--sp-4) var(--sp-3) 120px;
    }
    .grid {
      grid-template-columns: 1fr;
    }
    .tiles {
      grid-template-columns: repeat(2, 1fr);
    }
  }
</style>
