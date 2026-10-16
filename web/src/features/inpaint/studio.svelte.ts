import { api } from '$lib/api'
import { live } from '$lib/live.svelte'
import { session, segmentsToText, textToSegments } from '$lib/session.svelte'
import type { Family, GalleryItem, GenParams, PromptSegment } from '$lib/types'
import { toast } from '$lib/ui'
import type { Rect } from './mask'

export type Fill = 'original' | 'noise' | 'blur'

export interface Base {
  // null while the server side copy is still being made
  uploadId: string | null
  url: string
  width: number
  height: number
  // the gallery image this base was loaded from, null for uploads
  item: GalleryItem | null
}

export interface InpaintOpts {
  denoise: number
  maskBlur: number
  padding: number
  onlyMasked: boolean
  fill: Fill
  steps: number | null
  cfg: number | null
  seed: number
  count: number
  detailers: boolean
}

interface Pending {
  id: string
  region: Rect | null
  base: string
}

const KEY = 'somnia.inpaint.v1'
const DEFAULTS: InpaintOpts = {
  denoise: 0.6,
  maskBlur: 4,
  padding: 32,
  onlyMasked: true,
  fill: 'original',
  steps: null,
  cfg: null,
  seed: -1,
  count: 1,
  detailers: false,
}

function load(): { opts: InpaintOpts; positive: PromptSegment[]; negative: PromptSegment[] } {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) ?? 'null')
    if (s) return { opts: { ...DEFAULTS, ...s.opts }, positive: s.positive ?? [], negative: s.negative ?? [] }
  } catch {}
  return { opts: { ...DEFAULTS }, positive: [], negative: [] }
}


class Studio {
  base = $state<Base | null>(null)
  stackId = $state<string | null>(null)
  versions = $state<GalleryItem[]>([])
  pending = $state<Pending[]>([])
  family = $state<Family>('illustrious')
  opts = $state<InpaintOpts>(DEFAULTS)
  positive = $state<PromptSegment[]>([])
  negative = $state<PromptSegment[]>([])
  loading = $state(false)
  private upload: Promise<string> | null = null

  constructor() {
    const s = load()
    this.opts = s.opts
    this.positive = s.positive
    this.negative = s.negative
    $effect.root(() => {
      $effect(() => {
        const v = { opts: $state.snapshot(this.opts), positive: $state.snapshot(this.positive), negative: $state.snapshot(this.negative) }
        try {
          localStorage.setItem(KEY, JSON.stringify(v))
        } catch {}
      })
    })
    live.on((m) => {
      if (m.type === 'done') this.finished(m.job.id, m.job.images)
      else if (m.type === 'error') this.pending = this.pending.filter((p) => p.id !== m.jobId)
      else if (m.type === 'queue' && this.pending.length) {
        // jobs removed elsewhere (queue panel, another device)
        const ids = new Set(m.queue.map((j) => j.id))
        const left = this.pending.filter((p) => ids.has(p.id))
        if (left.length !== this.pending.length) this.pending = left
      }
    })
  }

  private loadPrompt(p: GenParams) {
    const seg = p.segments
    this.positive = seg?.positive?.length ? structuredClone(seg.positive) : textToSegments(p.prompt)
    this.negative = seg?.positive?.length ? structuredClone(seg.negative ?? []) : textToSegments(p.negative)
  }

  // shows the gallery image right away; the upload copy and the stack load in the background
  private show(item: GalleryItem) {
    const base: Base = { uploadId: null, url: item.url, width: item.width, height: item.height, item }
    this.base = base
    const up = api.galleryUpload(item.id).then((r) => {
      if (this.base?.item?.id === item.id) this.base.uploadId = r.id
      return r.id
    })
    up.catch((e) => toast.error('Could not prepare image', { description: e instanceof Error ? e.message : String(e) }))
    this.upload = up
  }

  async open(item: GalleryItem) {
    const stack = item.stackId ?? item.id
    const same = this.stackId === stack
    this.show(item)
    this.stackId = stack
    if (item.params) {
      this.family = item.params.family
      this.loadPrompt(item.params)
    } else this.family = session.family
    if (!same) this.versions = [item]
    try {
      const v = await api.stack(item.id)
      if (this.stackId === stack) this.versions = v
    } catch {}
  }

  async openFile(file: File) {
    this.loading = true
    try {
      const up = await api.upload(file, file.name)
      this.base = { uploadId: up.id, url: up.url, width: up.width, height: up.height, item: null }
      this.upload = Promise.resolve(up.id)
      this.stackId = null
      this.versions = []
      this.family = up.params?.family ?? session.family
      if (up.params) this.loadPrompt(up.params)
    } finally {
      this.loading = false
    }
  }

  // continue editing from another version of the stack
  use(item: GalleryItem) {
    if (this.base?.item?.id !== item.id) this.show(item)
  }

  close() {
    this.base = null
    this.stackId = null
    this.versions = []
    this.upload = null
  }

  async cancel(id: string) {
    try {
      await api.cancel(id)
    } catch {}
    this.pending = this.pending.filter((p) => p.id !== id)
  }

  cancelAll() {
    return Promise.all(this.pending.map((p) => this.cancel(p.id)))
  }

  build(maskId: string, imageId: string): GenParams | null {
    const b = this.base
    const p = session.byFamily[this.family]
    if (!b || !p) return null
    const o = this.opts
    const base = $state.snapshot(p) as GenParams
    return {
      ...base,
      family: this.family,
      prompt: segmentsToText(this.positive),
      negative: segmentsToText(this.negative),
      segments: {
        positive: $state.snapshot(this.positive) as PromptSegment[],
        negative: $state.snapshot(this.negative) as PromptSegment[],
      },
      width: b.width,
      height: b.height,
      steps: o.steps ?? base.steps,
      cfg: o.cfg ?? base.cfg,
      seed: o.seed,
      batchSize: 1,
      secondPass: { ...base.secondPass, enabled: false },
      upscale: { ...base.upscale, enabled: false },
      detailers: o.detailers ? base.detailers : [],
      init: {
        imageId,
        denoise: o.denoise,
        maskId,
        maskBlur: o.maskBlur,
        padding: o.padding,
        onlyMasked: o.onlyMasked,
        fill: o.fill,
      },
      stackId: this.stackId,
    }
  }

  async queue(maskId: string, region: Rect | null) {
    if (!this.upload) return
    const imageId = await this.upload
    const params = this.build(maskId, imageId)
    if (!params) return
    if (!params.model) throw new Error('Pick a model first')
    const { ids } = await api.queue(params, this.opts.count)
    const base = imageId
    this.pending = [...this.pending, ...ids.map((id) => ({ id, region, base }))]
  }

  private finished(jobId: string, images: GalleryItem[]) {
    const p = this.pending.find((x) => x.id === jobId)
    if (!p) return
    this.pending = this.pending.filter((x) => x.id !== jobId)
    if (!images.length) return
    if (!this.stackId) {
      // first result of an uploaded image starts the stack
      this.stackId = images[0].id
      this.versions = [images[0]]
      images = images.slice(1)
      if (!images.length) return void this.follow(p, this.versions[0])
    }
    const fresh = images.filter((i) => !this.versions.some((v) => v.id === i.id))
    this.versions = [...this.versions, ...fresh]
    this.follow(p, images[images.length - 1])
  }

  // results become the new base unless the user moved on to another version meanwhile
  private follow(p: Pending, item: GalleryItem) {
    if (this.base?.uploadId === p.base && !this.pending.some((x) => x.base === p.base)) this.use(item)
  }
}

export const studio = new Studio()
