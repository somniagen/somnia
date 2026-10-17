import type { Download, GalleryItem, Job, Progress, Settings, WsMessage } from './types'
import { auth } from './auth.svelte'

type Listener = (msg: WsMessage) => void

const sortRecent = (items: GalleryItem[]) => [...items].sort((a, b) => b.createdAt - a.createdAt)

class Live {
  connected = $state(false)
  queue = $state<Job[]>([])
  paused = $state(false)
  current = $state<Progress | null>(null)
  preview = $state<string | null>(null)
  recent = $state<GalleryItem[]>([])
  downloads = $state<Record<string, Download>>({})
  settings = $state<Settings | null>(null)
  lastError = $state<{ jobId: string; message: string } | null>(null)

  running = $derived(this.queue.find((j) => j.status === 'running') ?? null)
  pending = $derived(this.queue.filter((j) => j.status === 'queued'))

  private ws: WebSocket | null = null
  private listeners = new Set<Listener>()
  private retry = 0

  start() {
    if (this.ws) return
    this.open()
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && !this.connected) this.reconnectNow()
    })
  }

  on(fn: Listener) {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  private reconnectNow() {
    this.ws?.close()
    this.ws = null
    this.open()
  }

  private open() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws`)
    this.ws = ws
    ws.onopen = () => {
      this.connected = true
      this.retry = 0
    }
    ws.onmessage = (e) => this.handle(JSON.parse(e.data) as WsMessage)
    ws.onclose = (e) => {
      if (this.ws !== ws) return
      this.connected = false
      this.ws = null
      if (e.code === 4401) return auth.lock()
      const delay = Math.min(5000, 300 * 2 ** this.retry++)
      setTimeout(() => this.open(), delay)
    }
  }

  private mergeRecent(items: GalleryItem[]) {
    const ids = new Set(items.map((i) => i.id))
    this.recent = sortRecent([...items, ...this.recent.filter((i) => !ids.has(i.id))]).slice(0, 60)
  }

  dismissError() {
    this.lastError = null
  }

  private handle(msg: WsMessage) {
    switch (msg.type) {
      case 'snapshot':
        this.queue = msg.queue
        this.paused = msg.paused
        this.current = msg.current
        this.preview = msg.current?.preview ?? null
        this.recent = sortRecent(msg.recent)
        this.downloads = Object.fromEntries(msg.downloads.map((d) => [d.id, d]))
        break
      case 'queue':
        this.queue = msg.queue
        this.paused = msg.paused
        if (!msg.queue.some((j) => j.status === 'running')) this.current = null
        break
      case 'progress': {
        const { type, ...p } = msg
        if (this.lastError && this.lastError.jobId !== p.jobId) this.lastError = null
        if (this.current?.jobId !== p.jobId) this.preview = p.preview ?? null
        else if (p.preview) this.preview = p.preview
        this.current = { ...p, preview: this.preview }
        break
      }
      case 'done':
        this.mergeRecent(msg.job.images)
        if (this.current?.jobId === msg.job.id) this.current = null
        break
      case 'error':
        this.lastError = { jobId: msg.jobId, message: msg.message }
        if (this.current?.jobId === msg.jobId) this.current = null
        break
      case 'download':
        this.downloads = { ...this.downloads, [msg.download.id]: msg.download }
        break
      case 'settings':
        this.settings = msg.settings
        break
      case 'gallery_item':
        this.mergeRecent([msg.item])
        break
    }
    for (const fn of this.listeners) fn(msg)
  }
}

export const live = new Live()
if (import.meta.env.DEV) (window as unknown as { __live: typeof live }).__live = live
