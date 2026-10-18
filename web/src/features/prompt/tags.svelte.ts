import { SvelteMap } from 'svelte/reactivity'
import { api } from '$lib/api'
import type { LocalModel, RelatedTag, Tag, TagCategory, TagWiki } from '$lib/types'

export const categories = new SvelteMap<string, TagCategory | null>()
const pending = new Set<string>()
let timer: ReturnType<typeof setTimeout> | undefined

export function requestCategories(names: Iterable<string>) {
  for (const n of names) if (n && n.length < 120 && !categories.has(n)) pending.add(n)
  if (!pending.size) return
  clearTimeout(timer)
  timer = setTimeout(flush, 120)
}

async function flush() {
  const all = [...pending]
  pending.clear()
  for (let i = 0; i < all.length; i += 80) {
    const batch = all.slice(i, i + 80)
    for (const n of batch) categories.set(n, null)
    try {
      const res = await api.tagLookup(batch)
      for (const [k, v] of Object.entries(res)) categories.set(k, v)
    } catch {
      for (const n of batch) categories.delete(n)
    }
  }
}

export const categoryVar: Record<number, string> = {
  0: '--tag-general',
  1: '--tag-artist',
  3: '--tag-copyright',
  4: '--tag-character',
  5: '--tag-meta',
}

export const categoryName: Record<number, string> = {
  0: 'General',
  1: 'Artist',
  3: 'Copyright',
  4: 'Character',
  5: 'Meta',
}

export function colorOf(c: TagCategory | null | undefined) {
  return c == null ? 'var(--tag-unknown)' : `var(${categoryVar[c]})`
}

const searchCache = new Map<string, Tag[]>()

export async function searchTags(q: string, signal?: AbortSignal, category?: number): Promise<Tag[]> {
  const key = q.trim().toLowerCase().replace(/\s+/g, '_')
  const ck = category === undefined ? key : `${category}:${key}`
  const hit = searchCache.get(ck)
  if (hit) return hit
  const res = await api.tags(key, 12, signal, category)
  if (searchCache.size > 300) searchCache.delete(searchCache.keys().next().value!)
  searchCache.set(ck, res)
  for (const t of res) categories.set(t.name, t.category)
  return res
}

const wikiCache = new Map<string, Promise<TagWiki | null>>()

export function fetchWiki(name: string): Promise<TagWiki | null> {
  let p = wikiCache.get(name)
  if (!p) {
    p = api.tagWiki(name).catch(() => {
      wikiCache.delete(name)
      return null
    })
    wikiCache.set(name, p)
  }
  return p
}

const relatedCache = new Map<string, Promise<RelatedTag[]>>()

export function fetchRelated(name: string): Promise<RelatedTag[]> {
  let p = relatedCache.get(name)
  if (!p) {
    p = api
      .tagRelated(name)
      .then((r) => {
        for (const t of r) categories.set(t.name, t.category)
        return r
      })
      .catch(() => {
        relatedCache.delete(name)
        return []
      })
    relatedCache.set(name, p)
  }
  return p
}

export function compact(n: number): string {
  if (n >= 1e6) return `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M`
  if (n >= 1e3) return `${(n / 1e3).toFixed(n >= 1e4 ? 0 : 1)}k`
  return String(n)
}

let loraPromise: Promise<LocalModel[]> | null = null
export const loraModels = $state<{ list: LocalModel[] }>({ list: [] })

export function loadLoras(force = false) {
  if (loraPromise && !force) return loraPromise
  loraPromise = api
    .models('lora')
    .then((l) => (loraModels.list = l))
    .catch(() => {
      loraPromise = null
      return []
    })
  return loraPromise
}
