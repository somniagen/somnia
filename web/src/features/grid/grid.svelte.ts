import { api } from '$lib/api'
import { live } from '$lib/live.svelte'
import { session, segmentsToText } from '$lib/session.svelte'
import type { Family, GenParams, Grid, GridAxis, PromptSegment } from '$lib/types'
import { buildAxis, newDraft, type AxisDraft } from './axes'

const KEY = 'somnia.grid.v1'
export const MAX_CELLS = 500
export const WARN_CELLS = 64

interface Stored {
  base: GenParams | null
  positive: PromptSegment[]
  negative: PromptSegment[]
  axes: AxisDraft[]
}

function load(): Stored {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) ?? 'null')
    if (s) return { base: s.base ?? null, positive: s.positive ?? [], negative: s.negative ?? [], axes: s.axes?.length ? s.axes : [newDraft()] }
  } catch {}
  return { base: null, positive: [], negative: [], axes: [newDraft()] }
}

class GridStore {
  base = $state<GenParams | null>(null)
  positive = $state<PromptSegment[]>([])
  negative = $state<PromptSegment[]>([])
  axes = $state<AxisDraft[]>([])
  grids = $state<Grid[]>([])
  currentId = $state<string | null>(null)
  z = $state(0)
  loaded = $state(false)

  family = $derived<Family>(this.base?.family ?? session.family)
  current = $derived(this.grids.find((g) => g.id === this.currentId) ?? this.grids[0] ?? null)
  built = $derived.by((): { axes: GridAxis[]; cells: number; bad: number[] } => {
    const b = this.base
    const axes: GridAxis[] = []
    const bad: number[] = []
    if (!b) return { axes, cells: 0, bad }
    this.axes.forEach((d, i) => {
      const a = buildAxis(d, b)
      if (a) axes.push(a)
      else bad.push(i)
    })
    return { axes, cells: axes.length ? axes.reduce((n, a) => n * a.values.length, 1) : 0, bad }
  })

  constructor() {
    const s = load()
    this.base = s.base
    this.positive = s.positive
    this.negative = s.negative
    this.axes = s.axes
    $effect.root(() => {
      $effect(() => {
        const v: Stored = {
          base: $state.snapshot(this.base) as GenParams | null,
          positive: $state.snapshot(this.positive),
          negative: $state.snapshot(this.negative),
          axes: $state.snapshot(this.axes),
        }
        try {
          localStorage.setItem(KEY, JSON.stringify(v))
        } catch {}
      })
    })
    live.on((m) => {
      if (m.type === 'grid') this.upsert(m.grid)
      else if (m.type === 'grid_removed') this.grids = this.grids.filter((g) => g.id !== m.id)
      else if (m.type === 'snapshot' && this.loaded) void this.refresh()
    })
  }

  async refresh() {
    try {
      const list = await api.grids(30)
      this.grids = list
      this.loaded = true
    } catch {}
  }

  ensure() {
    if (!this.loaded) void this.refresh()
    if (!this.base && session.params) this.pull(true)
  }

  private upsert(g: Grid) {
    const i = this.grids.findIndex((x) => x.id === g.id)
    if (i >= 0) this.grids[i] = g
    else this.grids = [g, ...this.grids]
  }

  // takes the generate tab params; the prompt only when the grid has none of its own
  pull(withPrompt = false) {
    const p = session.build()
    if (!p) return
    const { prompt: _p, negative: _n, segments, stackId: _s, init: _i, ...rest } = p
    this.base = { ...rest, prompt: '', negative: '', init: null } as GenParams
    const empty = !this.positive.some((s) => s.text.trim())
    if ((withPrompt || empty) && segments) {
      this.positive = structuredClone(segments.positive)
      this.negative = structuredClone(segments.negative)
    }
  }

  // switches the base to another family, taking that family's generate params
  setFamily(f: Family) {
    if (this.base?.family === f) return
    const p = session.byFamily[f]
    if (!p) return
    const { stackId: _s, init: _i, ...rest } = $state.snapshot(p) as GenParams
    this.base = { ...rest, family: f, prompt: '', negative: '', init: null } as GenParams
  }

  params(): GenParams | null {
    if (!this.base) return null
    return {
      ...($state.snapshot(this.base) as GenParams),
      prompt: segmentsToText(this.positive),
      negative: segmentsToText(this.negative),
      segments: {
        positive: $state.snapshot(this.positive) as PromptSegment[],
        negative: $state.snapshot(this.negative) as PromptSegment[],
      },
      batchSize: 1,
    }
  }

  async run() {
    const p = this.params()
    if (!p) throw new Error('No base params')
    if (!p.model) throw new Error('Pick a model first')
    const { axes, cells, bad } = this.built
    if (bad.length) throw new Error(`Axis ${'XYZ'[bad[0]]} has no valid values`)
    if (!axes.length) throw new Error('Add an axis')
    if (cells > MAX_CELLS) throw new Error(`${cells} cells, the limit is ${MAX_CELLS}`)
    const g = await api.createGrid(p, axes)
    this.upsert(g)
    this.currentId = g.id
    this.z = 0
    return g
  }

  async remove(id: string) {
    await api.deleteGrid(id)
    this.grids = this.grids.filter((g) => g.id !== id)
    if (this.currentId === id) this.currentId = null
  }

  addAxis() {
    if (this.axes.length < 3) this.axes = [...this.axes, newDraft(this.axes.length === 1 ? 'steps' : 'seed')]
  }

  removeAxis(i: number) {
    this.axes = this.axes.filter((_, j) => j !== i)
    if (!this.axes.length) this.axes = [newDraft()]
  }

  swap(i: number, j: number) {
    const a = [...this.axes]
    ;[a[i], a[j]] = [a[j], a[i]]
    this.axes = a
  }
}

export const grid = new GridStore()
