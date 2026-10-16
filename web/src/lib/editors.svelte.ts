import { api } from './api'
import { live } from './live.svelte'
import type { EditorList, ImageEditor } from './types'

class Editors {
  list = $state<EditorList | null>(null)
  private loading: Promise<void> | null = null

  // the editor the open button uses; null hides it (other device, nothing installed, or turned off)
  current = $derived.by((): ImageEditor | null => {
    const l = this.list
    if (!l?.local || !l.editors.length) return null
    const pick = live.settings?.imageEditor ?? null
    if (pick === 'none') return null
    const auto = l.editors.find((e) => !e.custom) ?? l.editors[0]
    if (pick) return l.editors.find((e) => e.id === pick) ?? auto
    return l.editors.find((e) => e.id === l.current) ?? auto
  })

  // runs a list-returning call and keeps its result
  async apply(p: Promise<EditorList>) {
    this.list = await p
  }

  load(rescan = false) {
    if (this.loading && !rescan) return this.loading
    this.loading = api
      .editors(rescan)
      .then((l) => void (this.list = l))
      .catch(() => {
        this.loading = null
      })
    return this.loading
  }
}

export const editors = new Editors()
