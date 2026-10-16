import { api } from '$lib/api'
import { session } from '$lib/session.svelte'
import type { Family, PromptSegment, SavedPrompt } from '$lib/types'

export const library = $state<{ items: SavedPrompt[]; loaded: boolean; loading: boolean }>({
  items: [],
  loaded: false,
  loading: false,
})

const clean = (segs: PromptSegment[] | undefined) =>
  (segs ?? []).map((s) => ({ text: s.text, locked: s.locked, ...(s.locked && s.color ? { color: s.color } : {}) })).filter((s) => s.locked || s.text.trim())

export async function refreshLibrary() {
  library.loading = true
  try {
    library.items = await api.prompts()
    library.loaded = true
  } finally {
    library.loading = false
  }
}

export async function saveCurrent(name: string, family: Family = session.family) {
  const p = await api.createPrompt({
    name: name.trim() || 'Untitled',
    family,
    positive: clean($state.snapshot(session.positive[family])),
    negative: clean($state.snapshot(session.negative[family])),
  })
  library.items = [p, ...library.items]
  return p
}

export async function renamePrompt(p: SavedPrompt, name: string) {
  const u = await api.updatePrompt({ ...$state.snapshot(p), name })
  library.items = library.items.map((x) => (x.id === u.id ? u : x))
}

export async function deletePrompt(p: SavedPrompt) {
  await api.deletePrompt(p.id)
  library.items = library.items.filter((x) => x.id !== p.id)
}

export async function restorePrompt(p: SavedPrompt) {
  const { id: _, createdAt: _c, updatedAt: _u, ...rest } = $state.snapshot(p)
  const n = await api.createPrompt(rest)
  library.items = [n, ...library.items]
}

// replaces the session prompts of the prompt's family (or the current one) and keeps locked segments as saved
export function applyPrompt(p: SavedPrompt) {
  const f = p.family && session.byFamily[p.family] ? p.family : session.family
  if (f !== session.family) session.setFamily(f)
  session.positive[f] = $state.snapshot(p.positive)
  session.negative[f] = $state.snapshot(p.negative)
}
