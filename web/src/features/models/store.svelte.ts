import { api } from '$lib/api'
import { live } from '$lib/live.svelte'
import type { IdentifyState, LocalModel } from '$lib/types'

const RECENT = 'somnia.loras.recent'

class Models {
  list = $state<LocalModel[]>([])
  loaded = $state(false)
  loading = $state(false)
  identify = $state<IdentifyState>({ running: false, done: 0, total: 0 })
  private started = false

  start() {
    if (this.started) return
    this.started = true
    live.on((m) => {
      if (m.type === 'models_changed') void this.refresh()
      else if (m.type === 'identify') this.identify = { running: m.running, done: m.done, total: m.total }
    })
    void this.refresh()
    api
      .identifyState()
      .then((s) => (this.identify = s))
      .catch(() => {})
  }

  async refresh() {
    this.loading = true
    try {
      this.list = await api.models()
      this.loaded = true
    } finally {
      this.loading = false
    }
  }

  async rescan() {
    this.loading = true
    try {
      this.list = await api.rescan()
      this.loaded = true
    } finally {
      this.loading = false
    }
  }

  get(id: string) {
    return this.list.find((m) => m.id === id)
  }

  recent(): string[] {
    try {
      return JSON.parse(localStorage.getItem(RECENT) ?? '[]')
    } catch {
      return []
    }
  }

  touch(id: string) {
    try {
      const r = [id, ...this.recent().filter((x) => x !== id)].slice(0, 40)
      localStorage.setItem(RECENT, JSON.stringify(r))
    } catch {}
  }
}

export const models = new Models()
