<script lang="ts">
  import IconButton from './IconButton.svelte'
  import NumberField from './NumberField.svelte'
  import Segmented from './Segmented.svelte'

  interface Props {
    width?: number
    height?: number
    options?: [number, number][]
    ratios?: [number, number][]
    custom?: boolean
    step?: number
    min?: number
    max?: number
    class?: string
    style?: string
    onchange?: (w: number, h: number) => void
  }
  let {
    width = $bindable(1024),
    height = $bindable(1024),
    options = [
      [1024, 1024],
      [896, 1152],
      [832, 1216],
      [768, 1344],
      [640, 1536],
    ],
    ratios,
    custom = true,
    step = 64,
    min = 256,
    max = 4096,
    class: klass,
    style,
    onchange,
  }: Props = $props()

  const named: [number, number][] = [
    [1, 1], [5, 4], [9, 7], [4, 3], [3, 2], [8, 5], [16, 9], [7, 4], [2, 1], [21, 9], [12, 5],
  ]
  function ratio(w: number, h: number) {
    const long = Math.max(w, h)
    const short = Math.min(w, h)
    const r = long / short
    let best = named[0]
    for (const n of named) if (Math.abs(n[0] / n[1] - r) < Math.abs(best[0] / best[1] - r)) best = n
    let [a, b] = best
    if (Math.abs(a / b - r) / r > 0.04) {
      const g = (x: number, y: number): number => (y ? g(y, x % y) : x)
      const d = g(long, short)
      ;[a, b] = [long / d, short / d]
    }
    return w >= h ? `${a}:${b}` : `${b}:${a}`
  }

  let orient = $state<'portrait' | 'landscape'>('portrait')
  $effect(() => {
    if (width !== height) orient = width > height ? 'landscape' : 'portrait'
  })

  let by = $state<'short' | 'mp'>(load())
  function load(): 'short' | 'mp' {
    try {
      return localStorage.getItem('somnia.aspect.by') === 'mp' ? 'mp' : 'short'
    } catch {
      return 'short'
    }
  }
  function setBy(v: 'short' | 'mp') {
    try {
      localStorage.setItem('somnia.aspect.by', v)
    } catch {}
  }

  const short = $derived(Math.min(width, height))
  const snap = (v: number) => Math.max(min, Math.min(max, Math.round(v / step) * step))
  const shortFor = (r: number, m = width * height) => Math.sqrt(m / r)
  function fromRatio(a: number, b: number, s = by === 'mp' ? shortFor(Math.max(a, b) / Math.min(a, b)) : short) {
    const sh = snap(s)
    const lg = snap((sh * Math.max(a, b)) / Math.min(a, b))
    return orient === 'landscape' ? [lg, sh] : [sh, lg]
  }
  function setMp(v: number) {
    const r = Math.max(width, height) / short
    const sh = snap(shortFor(r, v * 1e6))
    const lg = snap(sh * r)
    set(...((orient === 'landscape' ? [lg, sh] : [sh, lg]) as [number, number]))
  }
  function setShort(v: number) {
    const sh = snap(v)
    const lg = snap((sh * Math.max(width, height)) / short)
    set(...((orient === 'landscape' ? [lg, sh] : [sh, lg]) as [number, number]))
  }

  const shapes = $derived.by(() => {
    if (ratios) {
      const out = ratios.map(([a, b]) => ({ long: Math.max(a, b), short: Math.min(a, b) }))
      return out.sort((p, q) => p.long / p.short - q.long / q.short)
    }
    const seen = new Set<string>()
    const out: { long: number; short: number }[] = []
    for (const [a, b] of options) {
      const long = Math.max(a, b)
      const short = Math.min(a, b)
      const k = `${long}x${short}`
      if (!seen.has(k)) {
        seen.add(k)
        out.push({ long, short })
      }
    }
    return out.sort((p, q) => p.long / p.short - q.long / q.short)
  })
  const dims = (s: { long: number; short: number }) =>
    ratios ? fromRatio(s.long, s.short) : orient === 'landscape' ? [s.long, s.short] : [s.short, s.long]
  const isSel = (s: { long: number; short: number }, w: number, h: number) =>
    ratios
      ? Math.abs(Math.max(width, height) / Math.min(width, height) / (s.long / s.short) - 1) < 0.035 &&
        (width === height) === (s.long === s.short)
      : (w === width && h === height) || (h === width && w === height)

  function set(w: number, h: number) {
    if (w === width && h === height) return
    width = w
    height = h
    onchange?.(w, h)
  }
  function swap() {
    orient = orient === 'landscape' ? 'portrait' : 'landscape'
    set(height, width)
  }

  const box = (w: number, h: number, size: number) => {
    const s = size / Math.max(w, h)
    return `width: ${Math.round(w * s)}px; height: ${Math.round(h * s)}px`
  }
  const mp = $derived(((width * height) / 1e6).toFixed(2))
</script>

<div class={['ap', klass]} {style}>
  <div class="top">
    <div class="preview" aria-hidden="true">
      <div class="rect" style={box(width, height, 84)}>
        <span>{ratio(width, height)}</span>
      </div>
    </div>
    <div class="shapes" role="radiogroup" aria-label="Aspect ratio">
      {#each shapes as s (s.long + 'x' + s.short)}
        {@const [w, h] = dims(s)}
        {@const sel = isSel(s, w, h)}
        <button
          type="button"
          role="radio"
          aria-checked={sel}
          aria-label="{ratio(w, h)}, {w} by {h}"
          class:sel
          onclick={() => set(w, h)}
        >
          <span class="mini" style={box(w, h, 22)}></span>
          <span class="lbl">{ratio(w, h)}</span>
        </button>
      {/each}
    </div>
  </div>
  {#if ratios}
    <div class="dims">
      {#if by === 'mp'}
        <NumberField label="MP" value={+mp} step={0.01} min={0.1} max={(max * max) / 1e6} steppers={false} size="sm" onchange={setMp} />
      {:else}
        <NumberField label="Min" value={short} {step} {min} {max} steppers={false} size="sm" onchange={setShort} />
      {/if}
      <Segmented
        items={[{ value: 'short', label: 'Side' }, { value: 'mp', label: 'MP' }]}
        bind:value={by}
        onchange={setBy}
        size="sm"
        label="Size by"
      />
    </div>
  {/if}
  <div class="dims">
    {#if custom}
      <NumberField label="W" bind:value={width} {step} {min} {max} steppers={false} size="sm" onchange={(v) => onchange?.(v, height)} />
      <IconButton icon="swap_horiz" label="Swap orientation" size="sm" onclick={swap} />
      <NumberField label="H" bind:value={height} {step} {min} {max} steppers={false} size="sm" onchange={(v) => onchange?.(width, v)} />
    {:else}
      <span class="wh">{width} x {height}</span>
      <IconButton icon="swap_horiz" label="Swap orientation" size="sm" onclick={swap} />
    {/if}
    <span class="mp">{mp} MP</span>
  </div>
</div>

<style>
  .ap {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
  }
  .top {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
  }
  .preview {
    display: grid;
    place-items: center;
    flex: none;
    width: 100px;
    height: 100px;
    border-radius: var(--r-md);
    background: var(--grad-2);
  }
  .rect {
    display: grid;
    place-items: center;
    border-radius: 5px;
    background: var(--accent-soft);
    box-shadow: inset 0 0 0 1.5px var(--accent);
    color: var(--accent-strong);
    font-size: var(--fs-xs);
    font-weight: 600;
    transition:
      width var(--dur) var(--ease),
      height var(--dur) var(--ease);
  }
  .shapes {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    min-width: 0;
  }
  .shapes button {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-end;
    gap: 4px;
    width: 48px;
    height: 52px;
    padding: 6px 0 5px;
    border: 0;
    border-radius: var(--r-sm);
    background: var(--grad-2);
    color: var(--text-muted);
    font: inherit;
    font-size: var(--fs-xs);
    cursor: pointer;
    transition:
      background var(--dur-fast) var(--ease),
      color var(--dur-fast) var(--ease),
      transform var(--dur-fast) var(--ease);
  }
  .shapes button:hover {
    background: var(--grad-3);
    color: var(--text);
  }
  .shapes button:active {
    transform: scale(0.95);
  }
  .mini {
    display: block;
    margin: auto 0;
    border-radius: 2px;
    box-shadow: inset 0 0 0 1.5px currentColor;
    transition:
      width var(--dur) var(--ease),
      height var(--dur) var(--ease);
  }
  .shapes button.sel {
    background: var(--accent-soft);
    color: var(--accent-strong);
  }
  .lbl {
    line-height: 1;
  }
  .dims {
    display: flex;
    align-items: center;
    gap: var(--sp-1);
  }
  .dims :global(.nf) {
    width: 104px;
  }
  .wh {
    font-variant-numeric: tabular-nums;
  }
  .mp {
    margin-left: auto;
    color: var(--text-faint);
    font-size: var(--fs-sm);
    font-variant-numeric: tabular-nums;
  }
  @media (pointer: coarse) {
    .shapes button {
      width: 52px;
      height: 56px;
    }
  }
</style>
