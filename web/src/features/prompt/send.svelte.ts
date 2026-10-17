import { grid } from '$features/grid/grid.svelte'
import { studio } from '$features/inpaint/studio.svelte'
import { session, textToSegments } from '$lib/session.svelte'
import type { Family, GenParams, PromptSegment } from '$lib/types'
import { toast, type MenuItem } from '$lib/ui'

export type Tab = 'generate' | 'inpaint' | 'grid'

export interface SentPrompt {
  family: Family
  positive: PromptSegment[]
  negative: PromptSegment[]
}

const TABS: Record<Tab, { label: string; icon: string; hash: string }> = {
  generate: { label: 'Generate', icon: 'auto_awesome', hash: '#/' },
  inpaint: { label: 'Inpaint', icon: 'format_paint', hash: '#/inpaint' },
  grid: { label: 'Grid', icon: 'grid_view', hash: '#/grid' },
}

const clone = (s: PromptSegment[] | undefined) => structuredClone($state.snapshot(s ?? [])) as PromptSegment[]

function read(tab: Tab): SentPrompt {
  if (tab === 'inpaint') return { family: studio.family, positive: clone(studio.positive), negative: clone(studio.negative) }
  if (tab === 'grid') return { family: grid.family, positive: clone(grid.positive), negative: clone(grid.negative) }
  const f = session.family
  return { family: f, positive: clone(session.positive[f]), negative: clone(session.negative[f]) }
}

function write(tab: Tab, p: SentPrompt) {
  if (tab === 'inpaint') {
    studio.family = p.family
    studio.positive = p.positive
    studio.negative = p.negative
  } else if (tab === 'grid') {
    if (!grid.base) grid.pull()
    grid.setFamily(p.family)
    grid.positive = p.positive
    grid.negative = p.negative
  } else {
    session.setFamily(p.family)
    session.positive[p.family] = p.positive
    session.negative[p.family] = p.negative
  }
}

function go(hash: string) {
  if (location.hash !== hash) location.hash = hash
}

// copies the prompt (locked boilerplate segments included) into another tab and switches to it
export function sendPrompt(p: SentPrompt, to: Tab, back?: Tab) {
  const before = read(to)
  write(to, structuredClone(p))
  go(TABS[to].hash)
  toast.success(`Prompt sent to ${TABS[to].label}`, {
    action: {
      label: 'Undo',
      run: () => {
        write(to, before)
        if (back) go(TABS[back].hash)
      },
    },
  })
}

export function promptOf(p: GenParams): SentPrompt {
  const seg = $state.snapshot(p.segments)
  return {
    family: p.family,
    positive: seg?.positive?.length ? clone(seg.positive) : textToSegments(p.prompt),
    negative: seg?.positive?.length ? clone(seg.negative) : textToSegments(p.negative),
  }
}

export function sendItems(from: Tab | null, get: () => SentPrompt = () => read(from as Tab), only?: Tab[], after?: () => void): MenuItem[] {
  return (Object.keys(TABS) as Tab[])
    .filter((t) => t !== from && (!only || only.includes(t)))
    .map((t) => ({
      label: TABS[t].label,
      icon: TABS[t].icon,
      onselect: () => {
        sendPrompt(get(), t, from ?? undefined)
        after?.()
      },
    }))
}
