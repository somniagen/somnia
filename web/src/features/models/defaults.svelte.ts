import { api } from '$lib/api'
import { live } from '$lib/live.svelte'
import { session } from '$lib/session.svelte'
import type { GenParams, ModelDefaultParams, ModelDefaults } from '$lib/types'
import { toast } from '$lib/ui'
import { models } from './store.svelte'

const KEYS = ['steps', 'cfg', 'sampler', 'scheduler', 'clipSkip', 'cfgRescale', 'pag', 'vae'] as const

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)
const fail = (e: unknown) => toast.error('Could not save', { description: String(e instanceof Error ? e.message : e) })

class Defaults {
  map = $state<Record<string, ModelDefaults>>({})
  private started = false

  start() {
    if (this.started) return
    this.started = true
    live.on((m) => {
      if (m.type === 'model_defaults') this.map = m.defaults
    })
    api
      .modelDefaults()
      .then((d) => (this.map = d))
      .catch(() => {})
  }

  weight(id: string) {
    return this.map[id]?.weight ?? 1
  }

  // applies saved checkpoint defaults to the session; the toast offers undo
  apply(id: string): boolean {
    const d = this.map[id]?.params
    const p = session.params
    if (!d || !p) return false
    const patch = Object.fromEntries(Object.entries(d).filter(([k, v]) => !same(p[k as keyof GenParams], v))) as Partial<GenParams>
    if (!Object.keys(patch).length) return false
    const undo = session.patchWithUndo(patch)
    toast.info('Model defaults applied', { description: models.get(id)?.name, action: { label: 'Undo', run: undo } })
    return true
  }

  async saveParams(id: string, withSize = false) {
    const p = session.params
    if (!p) return
    const s = $state.snapshot(p) as GenParams
    const params: ModelDefaultParams = Object.fromEntries(KEYS.map((k) => [k, s[k]]))
    if (withSize) Object.assign(params, { width: s.width, height: s.height })
    try {
      this.map[id] = await api.setModelDefaults(id, { params })
      toast.success('Saved as model defaults')
    } catch (e) {
      fail(e)
    }
  }

  async saveWeight(id: string, weight: number) {
    try {
      this.map[id] = await api.setModelDefaults(id, { weight })
      toast.success('Default weight saved', { description: String(weight) })
    } catch (e) {
      fail(e)
    }
  }

  async clear(id: string) {
    try {
      await api.clearModelDefaults(id)
      delete this.map[id]
    } catch (e) {
      fail(e)
    }
  }
}

export const modelDefaults = new Defaults()
