import { api } from '$lib/api'
import type { GalleryAlbum, GalleryItem } from '$lib/types'
import { toast } from '$lib/ui'

type Ask = { title: string; value: string; action: string; resolve: (v: string | null) => void }

const fail = (what: string) => (e: unknown) => {
  toast.error(what, { description: e instanceof Error ? e.message : String(e) })
  return null
}

// favorites and albums shared by the gallery grid, its selection bar and the lightbox
class Library {
  albums = $state<GalleryAlbum[]>([])
  ask = $state<Ask | null>(null)
  // bumps when items changed server side so filtered views can refresh
  version = $state(0)

  refresh() {
    return api.albums().then((a) => (this.albums = a), () => {})
  }

  // writes server copies back into the local item objects
  apply(targets: GalleryItem[], fresh: GalleryItem[]) {
    const by = new Map(fresh.map((f) => [f.id, f]))
    for (const t of targets) {
      const f = by.get(t.id)
      if (!f) continue
      t.favorite = f.favorite
      t.albums = f.albums
    }
  }

  async favorite(items: GalleryItem[], value: boolean) {
    if (!items.length) return
    const prev = items.map((i) => i.favorite)
    for (const i of items) i.favorite = value
    const r = await (items.length === 1 ? api.setFavorite(items[0].id, value).then((x) => [x]) : api.setFavorites(items.map((i) => i.id), value)).catch(
      fail('Could not update favorites'),
    )
    if (!r) return items.forEach((i, k) => (i.favorite = prev[k]))
    this.apply(items, r)
    this.version++
  }

  name(title: string, value = '', action = 'Create') {
    return new Promise<string | null>((resolve) => {
      this.ask?.resolve(null)
      this.ask = { title, value, action, resolve }
    })
  }

  async add(items: GalleryItem[], album?: string) {
    const name = album ?? (await this.name('New album'))?.trim()
    if (!name || !items.length) return
    const r = await api.addToAlbum(items.map((i) => i.id), name).catch(fail('Could not add to album'))
    if (!r) return
    this.apply(items, r)
    this.version++
    toast.success(`Added to ${name}`)
    this.refresh()
  }

  async remove(items: GalleryItem[], album: string) {
    const r = await api.removeFromAlbum(items.map((i) => i.id), album).catch(fail('Could not remove from album'))
    if (!r) return
    this.apply(items, r)
    this.version++
    this.refresh()
  }

  async rename(album: string) {
    const name = (await this.name('Rename album', album, 'Rename'))?.trim()
    if (!name || name === album) return null
    const r = await api.renameAlbum(album, name).catch(fail('Could not rename album'))
    if (!r) return null
    this.albums = r
    this.version++
    return name
  }

  async drop(album: string) {
    const r = await api.deleteAlbum(album).catch(fail('Could not delete album'))
    if (!r) return false
    this.albums = r
    this.version++
    toast.success(`Deleted album ${album}`, { description: 'Images stay in the gallery' })
    return true
  }
}

export const library = new Library()
