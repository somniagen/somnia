<script lang="ts">
  import { tick } from 'svelte'
  import { Button, Chip, IconButton, Popover, coarse, toast, tooltip } from '$lib/ui'
  import { bareTag, removedTags, segmentsToText, session } from '$lib/session.svelte'
  import type { Family, LoraRef, PromptSegment } from '$lib/types'
  import Dock from './Dock.svelte'
  import FreeText from './FreeText.svelte'
  import WikiCard from './WikiCard.svelte'
  import { categories, colorOf, loadLoras, loraModels, requestCategories } from './tags.svelte'
  import { displayTag, estimateTokens, reweight, tokenize, weightAt } from './tokenize'
  import { saveCurrent } from './library.svelte'
  import { colorKey, colorVar, segColors, segKind } from './segcolor'

  let {
    segments = $bindable([]),
    kind = 'positive',
    family,
    loras = [],
    placeholder = '',
    foot = true,
    rows,
    removed,
    onreset,
  }: {
    segments: PromptSegment[]
    kind?: 'positive' | 'negative'
    family: Family
    loras?: LoraRef[]
    placeholder?: string
    foot?: boolean
    rows?: number
    // "-tag" removals when they live outside these segments (structured sections)
    removed?: Set<string>
    onreset?: () => void
  } = $props()

  const segs = $derived(segments ?? [])
  const view = $derived<PromptSegment[]>(
    !segs.length || segs[segs.length - 1].locked ? [...segs, { text: '', locked: false }] : segs,
  )
  const els: (HTMLTextAreaElement | undefined)[] = $state([])
  const chips: (HTMLElement | undefined)[] = $state([])
  const hasFree = $derived(segs.some((s) => !s.locked && s.text.trim()))
  const lastFree = $derived(view.length - 1)
  const mac = typeof navigator !== 'undefined' && /mac|iphone|ipad/i.test(navigator.platform)

  const keys = $derived.by(() => {
    const seen = new Map<string, number>()
    return view.map((s) => {
      const k = (s.locked ? 'L' : 'F') + s.text
      const n = seen.get(k) ?? 0
      seen.set(k, n + 1)
      return `${k}#${n}`
    })
  })

  function join(a: string, b: string) {
    const x = a.replace(/[\s,]+$/, '')
    const y = b.replace(/^[\s,]+/, '')
    if (!x) return y
    if (!y) return a
    return x.endsWith('\n') ? x + y : `${x}, ${y}`
  }

  function normalize(list: PromptSegment[]): PromptSegment[] {
    const out: PromptSegment[] = []
    for (const s of list) {
      if (s.locked) {
        const t = s.text.trim().replace(/^,+|,+$/g, '').trim()
        if (t) out.push(s.color ? { text: t, locked: true, color: s.color } : { text: t, locked: true })
        continue
      }
      if (!s.text.trim()) continue
      const prev = out[out.length - 1]
      if (prev && !prev.locked) prev.text = join(prev.text, s.text)
      else out.push({ text: s.text, locked: false })
    }
    return out
  }

  function setText(i: number, v: string, keepCards = false) {
    if (!keepCards) {
      wikiOpen = false
      cardOpen = false
    }
    if (i >= segs.length) segments = [...segs, { text: v, locked: false }]
    else segments = segs.map((s, j) => (j === i ? { ...s, text: v } : s))
  }

  async function focusAt(i: number, pos: 'start' | 'end' | number) {
    await tick()
    const el = els[i]
    if (!el) return
    el.focus()
    const p = pos === 'start' ? 0 : pos === 'end' ? el.value.length : pos
    el.setSelectionRange(p, p)
  }

  function freeIndex(from: number, dir: 1 | -1) {
    for (let i = from + dir; i >= 0 && i < view.length; i += dir) if (!view[i].locked) return i
    return -1
  }

  function lockRange(i: number, s: number, e: number) {
    const text = view[i].text
    const before = text.slice(0, s).replace(/[\s,]+$/, '')
    const sel = text.slice(s, e)
    const after = text.slice(e).replace(/^[\s,]+/, '')
    const next = [...segs.slice(0, i), { text: before, locked: false }, { text: sel, locked: true }, { text: after, locked: false }, ...segs.slice(i + 1)]
    const lockedIdx = normalize(next.slice(0, i + 2)).length - 1
    segments = normalize(next)
    const f = lockedIdx + 1
    if (f < segments.length && !segments[f].locked) focusAt(f, 'start')
    else focusAt(segments.length, 'start')
  }

  function unlock(i: number) {
    segments = normalize(segs.map((s, j) => (j === i ? { text: s.text, locked: false } : s)))
  }

  function remove(i: number) {
    const prev = $state.snapshot(segs) as PromptSegment[]
    const t = segs[i].text
    segments = normalize(segs.filter((_, j) => j !== i))
    toast('Boilerplate removed', {
      description: t.length > 60 ? t.slice(0, 60) + '...' : t,
      action: { label: 'Undo', run: () => (segments = prev) },
    })
  }

  function setColor(i: number, color: string | undefined) {
    segments = segs.map((s, j) => (j === i ? (color ? { ...s, color } : { text: s.text, locked: s.locked }) : s))
  }

  let nudged = $state(-1)
  function nudge(i: number) {
    nudged = -1
    requestAnimationFrame(() => (nudged = i))
    setTimeout(() => nudged === i && (nudged = -1), 400)
  }

  function edge(i: number, dir: 'prev' | 'next') {
    const j = freeIndex(i, dir === 'prev' ? -1 : 1)
    if (j >= 0) focusAt(j, dir === 'prev' ? 'end' : 'start')
    else if (dir === 'prev' && i > 0) nudge(i - 1)
  }

  function backspaceEmpty(i: number) {
    const j = freeIndex(i, -1)
    if (i !== lastFree) {
      segments = normalize(segs.filter((_, k) => k !== i))
      if (j >= 0) focusAt(j, 'end')
      else tick().then(() => focusAt(freeIndex(i - 1, 1), 'start'))
    } else if (i > 0) nudge(i - 1)
  }

  function blurred(i: number) {
    if (i < segs.length && i !== lastFree && !segs[i].text.trim()) segments = normalize(segs)
  }

  // colors
  const loraWords = $derived(
    new Set(loraModels.list.flatMap((m) => m.civitai?.trainedWords ?? []).map((w) => w.trim().replace(/^,+|,+$/g, '').trim())),
  )
  const off = $derived(removed ?? removedTags(segs))
  const segKey = (s: PromptSegment) => colorKey(s, segKind(s.text, kind, (t) => categories.get(t), loraWords))

  // reorder
  let box = $state<HTMLDivElement>()
  let drag = $state<{ i: number; dx: number; dy: number } | null>(null)
  let marker = $state<{ x: number; y: number; w: number; h: number } | null>(null)
  let dropAt = -1
  let dragged = false

  function rects() {
    const m = new Map<string, DOMRect>()
    for (const el of box?.querySelectorAll<HTMLElement>('.lk[data-key]') ?? []) m.set(el.dataset.key!, el.getBoundingClientRect())
    return m
  }
  async function flip(before: Map<string, DOMRect>) {
    await tick()
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return
    for (const el of box?.querySelectorAll<HTMLElement>('.lk[data-key]') ?? []) {
      const b = before.get(el.dataset.key!)
      if (!b) continue
      const r = el.getBoundingClientRect()
      const dx = b.left - r.left
      const dy = b.top - r.top
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue
      el.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }], {
        duration: 240,
        easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
      })
    }
  }
  async function focusHandle(key: string) {
    await tick()
    box?.querySelector<HTMLElement>(`.lk[data-key="${CSS.escape(key)}"] .lkbtn`)?.focus()
  }

  function moveTo(from: number, k: number) {
    const arr = [...view]
    const [it] = arr.splice(from, 1)
    arr.splice(k > from ? k - 1 : k, 0, it)
    segments = normalize(arr)
  }
  function step(i: number, dir: -1 | 1, refocus = false) {
    const j = i + dir
    if (j < 0 || j >= segs.length) return
    const before = rects()
    const key = keys[i]
    moveTo(i, dir < 0 ? j : j + 1)
    flip(before)
    if (refocus) focusHandle(key)
  }

  function target(x: number, y: number, from: number) {
    let best: { i: number; r: DOMRect; locked: boolean } | null = null
    let bestD = Infinity
    view.forEach((s, i) => {
      if (i === from) return
      const el = s.locked ? chips[i] : els[i]?.parentElement
      if (!el) return
      const r = el.getBoundingClientRect()
      const dy = y < r.top ? r.top - y : y > r.bottom ? y - r.bottom : 0
      const dx = s.locked ? (x < r.left ? r.left - x : x > r.right ? x - r.right : 0) : 0
      const d = dy * 3 + dx
      if (d < bestD) {
        bestD = d
        best = { i, r, locked: s.locked }
      }
    })
    if (!best) return
    const { i, r, locked } = best as { i: number; r: DOMRect; locked: boolean }
    const after = locked ? x > r.left + r.width / 2 : y > r.top + r.height / 2
    dropAt = after ? i + 1 : i
    marker = locked
      ? { x: after ? r.right + 2 : r.left - 4, y: r.top, w: 2, h: r.height }
      : { x: r.left, y: after ? r.bottom : r.top - 2, w: r.width, h: 2 }
  }

  function handleDown(e: PointerEvent, i: number) {
    if (e.button !== 0) return
    const h = e.currentTarget as HTMLElement
    const sx = e.clientX
    const sy = e.clientY
    let started = false
    dragged = false
    try {
      h.setPointerCapture(e.pointerId)
    } catch {}
    const move = (ev: PointerEvent) => {
      const dx = ev.clientX - sx
      const dy = ev.clientY - sy
      if (!started) {
        if (Math.hypot(dx, dy) < 6) return
        started = true
        wikiOpen = false
        cardOpen = false
        menuOpen = false
      }
      ev.preventDefault()
      drag = { i, dx, dy }
      target(ev.clientX, ev.clientY, i)
    }
    const end = (ev: PointerEvent) => {
      h.removeEventListener('pointermove', move)
      h.removeEventListener('pointerup', end)
      h.removeEventListener('pointercancel', end)
      if (!started) return
      dragged = true
      setTimeout(() => (dragged = false), 0)
      const before = rects()
      const k = ev.type === 'pointercancel' ? -1 : dropAt
      drag = null
      marker = null
      dropAt = -1
      if (k >= 0 && k !== i && k !== i + 1) moveTo(i, k)
      flip(before)
    }
    h.addEventListener('pointermove', move)
    h.addEventListener('pointerup', end)
    h.addEventListener('pointercancel', end)
  }

  function handleKey(e: KeyboardEvent, i: number) {
    if (!e.altKey) return
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') step(i, -1, true)
    else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') step(i, 1, true)
    else return
    e.preventDefault()
  }

  // locked segment menu
  let menuOpen = $state(false)
  let menuAnchor = $state<HTMLElement | { x: number; y: number } | null>(null)
  let menuIdx = $state(-1)
  let menuTag = $state<{ name: string; el: HTMLElement } | null>(null)
  let menuEl = $state<HTMLDivElement>()
  type Act = { label: string; icon: string; run: () => void; danger?: boolean; disabled?: boolean; hint?: string }
  const acts = $derived.by<(Act | null)[]>(() => {
    const i = menuIdx
    const t = menuTag
    return [
      ...(t ? [{ label: t.name.replace(/_/g, ' '), icon: 'info', run: () => showCard(t.name, t.el) }, null] : []),
      { label: 'Move earlier', icon: 'arrow_back', disabled: i <= 0, hint: 'Alt+Left', run: () => step(i, -1, !coarse.current) },
      { label: 'Move later', icon: 'arrow_forward', disabled: i >= segs.length - 1, hint: 'Alt+Right', run: () => step(i, 1, !coarse.current) },
      {
        label: 'Copy',
        icon: 'content_copy',
        run: () => navigator.clipboard?.writeText(segs[i]?.text ?? '').catch(() => {}),
      },
      { label: 'Unlock', icon: 'lock_open', run: () => unlock(i) },
      null,
      { label: 'Remove', icon: 'delete', danger: true, run: () => remove(i) },
    ]
  })
  function openMenu(i: number, anchor: HTMLElement | { x: number; y: number }, tag: HTMLElement | null = null) {
    wikiOpen = false
    cardOpen = false
    menuIdx = i
    menuAnchor = anchor
    menuTag = tag?.dataset.tag ? { name: tag.dataset.tag, el: tag } : null
    menuOpen = true
  }
  function runAct(a: Act) {
    if (a.disabled) return
    menuOpen = false
    a.run()
  }
  function menuKey(e: KeyboardEvent) {
    const list = [...(menuEl?.querySelectorAll<HTMLElement>('.mi:not(:disabled), .sw') ?? [])]
    const at = list.indexOf(document.activeElement as HTMLElement)
    let n = -1
    if (e.key === 'ArrowDown') n = (at + 1) % list.length
    else if (e.key === 'ArrowUp') n = (at - 1 + list.length) % list.length
    else if (e.key === 'ArrowRight' && list[at]?.classList.contains('sw')) n = Math.min(list.length - 1, at + 1)
    else if (e.key === 'ArrowLeft' && list[at]?.classList.contains('sw')) n = Math.max(0, at - 1)
    else return
    e.preventDefault()
    list[n]?.focus()
  }
  function chipTap(e: PointerEvent, i: number) {
    if (e.pointerType !== 'touch' || drag || (e.target as HTMLElement).closest('.lkbtn')) return
    const t = (e.target as HTMLElement).closest<HTMLElement>('[data-tag]')
    openMenu(i, e.currentTarget as HTMLElement, t)
  }

  // wiki hover (desktop)
  let wikiOpen = $state(false)
  let wikiName = $state('')
  let wikiCount = $state<number | undefined>()
  let wikiAnchor = $state<HTMLElement | null>(null)
  let wikiPlacement = $state<'bottom-start' | 'right-start'>('bottom-start')
  let showT: ReturnType<typeof setTimeout> | undefined
  let hideT: ReturnType<typeof setTimeout> | undefined

  function hover(name: string | null, anchor: HTMLElement | null, immediate = false, count?: number) {
    clearTimeout(showT)
    if (drag) return
    if (!name || !anchor) {
      clearTimeout(hideT)
      hideT = setTimeout(() => (wikiOpen = false), 280)
      return
    }
    if (wikiOpen && name === wikiName && anchor === wikiAnchor) {
      clearTimeout(hideT)
      return
    }
    showT = setTimeout(
      () => {
        clearTimeout(hideT)
        wikiName = name
        wikiCount = count
        wikiAnchor = anchor
        wikiPlacement = anchor.closest('.row') ? 'right-start' : 'bottom-start'
        wikiOpen = true
      },
      immediate ? 0 : wikiOpen ? 200 : 650,
    )
  }
  function lockedOver(e: PointerEvent) {
    if (e.pointerType === 'touch' || drag) return
    const t = (e.target as HTMLElement).closest<HTMLElement>('[data-tag]')
    hover(t?.dataset.tag ?? null, t)
  }

  // tag card (touch)
  let cardOpen = $state(false)
  let cardName = $state('')
  let cardAnchor = $state<HTMLElement | null>(null)
  let cardLock = $state<(() => void) | null>(null)
  let cardItem = $state<{ i: number; a: number; b: number } | null>(null)
  const cardWeight = $derived(cardItem ? (weightAt(segs[cardItem.i]?.text ?? '', cardItem.a, cardItem.b)?.weight ?? null) : null)

  let stepping = false
  function stepCard(delta: number) {
    const c = cardItem
    if (!c) return
    const text = segs[c.i]?.text ?? ''
    const r = reweight(text, c.a, c.b, delta)
    if (!r) return
    stepping = true
    setText(c.i, text.slice(0, r.start) + r.out + text.slice(r.end), true)
    stepping = false
    const b = r.start + r.out.length
    cardItem = { i: c.i, a: r.start, b }
    cardLock = () => lockRange(c.i, r.start, b)
  }

  function showCard(name: string, anchor: HTMLElement, lock: (() => void) | null = null, item: { i: number; a: number; b: number } | null = null) {
    if (!coarse.current) {
      hover(name, anchor, true)
      return
    }
    cardName = name
    cardAnchor = anchor
    cardLock = lock
    cardItem = item
    cardOpen = true
  }

  $effect(() => {
    requestCategories(segs.filter((s) => s.locked).flatMap((s) => tokenize(s.text).filter((t) => t.tag).map((t) => t.tag!)))
  })

  // lora triggers
  const promptTags = $derived(new Set(tokenize(segmentsToText(segs)).flatMap((t) => (t.tag ? [t.tag] : []))))
  const refreshed = new Set<string>()
  $effect(() => {
    if (kind !== 'positive') return
    loadLoras().then(() => {
      const missing = loras.find((l) => !loraModels.list.some((m) => m.id === l.id) && !refreshed.has(l.id))
      if (missing) {
        refreshed.add(missing.id)
        loadLoras(true)
      }
    })
  })
  const triggers = $derived.by(() => {
    if (kind !== 'positive') return []
    const seen = new Set<string>()
    const out: { text: string; lora: string }[] = []
    for (const l of loras) {
      const m = loraModels.list.find((x) => x.id === l.id)
      for (const w of m?.civitai?.trainedWords ?? []) {
        const text = w.trim().replace(/^,+|,+$/g, '').trim()
        const tags = tokenize(text).flatMap((t) => (t.tag ? [t.tag] : []))
        if (!text || seen.has(text) || (tags.length && tags.every((t) => promptTags.has(t)))) continue
        seen.add(text)
        out.push({ text, lora: m?.civitai?.name ?? m?.name ?? l.id })
      }
    }
    return out
  })
  // appends a suggested tag to the last editable segment
  function addTag(name: string) {
    let i = segs.length - 1
    while (i >= 0 && segs[i].locked) i--
    const tag = displayTag(name)
    if (i < 0) {
      segments = normalize([...segs, { text: tag, locked: false }])
      return
    }
    const cur = segs[i].text.replace(/[\s,]+$/, '')
    setText(i, cur ? `${cur}, ${tag}` : tag, true)
  }

  function addTrigger(text: string) {
    const at = segs.findIndex((s) => !s.locked)
    const next = [...segs]
    next.splice(at < 0 ? next.length : at, 0, { text, locked: true, color: 'copper' })
    segments = normalize(next)
  }

  // toolbar
  const tokens = $derived(estimateTokens(segmentsToText(segs)))
  const chunk = $derived(Math.max(75, Math.ceil(tokens / 75) * 75))

  function useDefault() {
    if (onreset) return onreset()
    const prev = $state.snapshot(segs) as PromptSegment[]
    segments = session.defaultSegments(family, kind)
    toast(kind === 'positive' ? 'Default prompt' : 'Default negative', { action: { label: 'Undo', run: () => (segments = prev) } })
  }

  function clearFree() {
    const prev = $state.snapshot(segs) as PromptSegment[]
    segments = segs.filter((s) => s.locked)
    toast('Prompt cleared', { action: { label: 'Undo', run: () => (segments = prev) } })
    focusAt(segments.length, 'start')
  }

  let saveOpen = $state(false)
  let saveBtn = $state<HTMLButtonElement>()
  let saveName = $state('')
  let saving = $state(false)
  async function save() {
    saving = true
    try {
      const p = await saveCurrent(saveName, family)
      toast.success('Saved to library', { description: p.name })
      saveOpen = false
      saveName = ''
    } catch (e) {
      toast.error('Could not save', { description: String((e as Error).message ?? e) })
    } finally {
      saving = false
    }
  }

  function boxDown(e: PointerEvent) {
    if (e.target === e.currentTarget) {
      e.preventDefault()
      focusAt(lastFree, 'end')
    }
  }
</script>

<div class="pe" class:neg={kind === 'negative'} class:dragging={!!drag}>
  <div class="box" bind:this={box} onpointerdown={boxDown} role="presentation">
    {#each view as s, i (i)}
      {#if s.locked}
        {@const ck = segKey(s)}
        <span
          bind:this={chips[i]}
          class="lk"
          class:nudge={nudged === i}
          class:lifted={drag?.i === i}
          class:menu={menuOpen && menuIdx === i}
          data-key={keys[i]}
          style="--seg: {colorVar(ck)}; {drag?.i === i ? `transform: translate(${drag.dx}px, ${drag.dy}px)` : ''}"
          role="group"
          aria-label="Boilerplate"
          oncontextmenu={(e) => {
            e.preventDefault()
            openMenu(i, { x: e.clientX, y: e.clientY }, (e.target as HTMLElement).closest<HTMLElement>('[data-tag]'))
          }}
          onpointerup={(e) => chipTap(e, i)}
          onpointermove={lockedOver}
          onpointerleave={() => hover(null, null)}
          ><button
            type="button"
            class="lkbtn icon"
            aria-label="Boilerplate options, Alt+Arrow to move"
            use:tooltip={{ text: 'Drag to reorder, click for options', describe: false }}
            onpointerdown={(e) => handleDown(e, i)}
            onkeydown={(e) => handleKey(e, i)}
            onclick={(e) => {
              if (dragged) {
                dragged = false
                return
              }
              openMenu(i, e.currentTarget.closest('.lk') as HTMLElement)
            }}>drag_indicator</button
          >{#each tokenize(s.text) as t (t.start)}<span
              data-tag={t.tag}
              class={t.kind}
              class:off={t.tag && off.size && off.has(bareTag(t.text))}
              style={t.tag ? `--c: ${colorOf(categories.get(t.tag))}` : undefined}>{t.text}</span
            >{/each}</span
        >
      {:else}
        <FreeText
          bind:value={() => s.text, (v) => setText(i, v)}
          bind:el={els[i]}
          placeholder={i === lastFree && !hasFree ? placeholder : ''}
          minRows={i === lastFree ? (rows ?? (kind === 'positive' ? 3 : 2)) : 1}
          onlock={(a, b) => lockRange(i, a, b)}
          onedge={(d) => edge(i, d)}
          onbackspaceempty={() => backspaceEmpty(i)}
          onhover={hover}
          ontag={(name, anchor, [a, b]) => showCard(name, anchor, () => lockRange(i, a, b), { i, a, b })}
          onblur={() => blurred(i)}
          onedit={() => {
            if (cardOpen && !stepping) cardOpen = false
          }}
        />
      {/if}
    {/each}
  </div>
  {#if foot}<div class="foot">
    <div class="trig">
      {#each triggers as t (t.text)}
        <Chip
          size="sm"
          icon="add"
          color="--tag-lora"
          label={t.text}
          title="{t.lora}: {t.text}"
          style="max-width: 240px"
          onclick={() => addTrigger(t.text)}
        />
      {/each}
    </div>
    <div class="tools">
      <span class="count" class:over={tokens > 75} use:tooltip={'Approximate tokens, 75 per chunk'}>{tokens}/{chunk}</span>
      <IconButton icon="restart_alt" label={kind === 'positive' ? 'Use default prompt' : 'Use default negative'} size="sm" onclick={useDefault} />
      <IconButton icon="ink_eraser" label="Clear prompt" size="sm" disabled={!hasFree} onclick={clearFree} />
      <IconButton bind:el={saveBtn} icon="bookmark_add" label="Save to library" size="sm" active={saveOpen} onclick={() => (saveOpen = !saveOpen)} />
    </div>
  </div>{/if}
</div>

{#if marker}
  <div class="marker" style="left: {marker.x}px; top: {marker.y}px; width: {marker.w}px; height: {marker.h}px"></div>
{/if}

<Popover bind:open={menuOpen} anchor={menuAnchor} placement="bottom-start" class="segmenu" autofocus>
  <div bind:this={menuEl} role="menu" aria-label="Boilerplate" tabindex="-1" onkeydown={menuKey}>
    {#each acts as a, k (k)}
      {#if a}
        <button
          type="button"
          class="mi"
          class:danger={a.danger}
          class:tagrow={a.icon === 'info'}
          role="menuitem"
          tabindex={k === 0 ? 0 : -1}
          disabled={a.disabled}
          onclick={() => runAct(a)}
        >
          <span class="icon" aria-hidden="true">{a.icon}</span>
          <span class="ml">{a.label}</span>
          {#if a.hint && !coarse.current}<span class="hint">{a.hint.replace('Alt', mac ? 'Opt' : 'Alt')}</span>{/if}
        </button>
      {:else}
        <div class="msep" role="separator"></div>
      {/if}
    {/each}
    <div class="msep" role="separator"></div>
    {#if segs[menuIdx]}
      {@const cur = segs[menuIdx].color}
      {@const auto = segKey({ text: segs[menuIdx].text, locked: true })}
      <div class="sws" role="radiogroup" aria-label="Color">
        <button
          type="button"
          class="sw auto"
          role="radio"
          tabindex="-1"
          aria-checked={!cur}
          aria-label="Auto color"
          style="--sw: {colorVar(auto)}"
          use:tooltip={'Auto'}
          onclick={() => setColor(menuIdx, undefined)}><span class="icon">auto_awesome</span></button
        >
        {#each segColors as c (c.key)}
          <button
            type="button"
            class="sw"
            role="radio"
            tabindex="-1"
            aria-checked={cur === c.key}
            aria-label={c.label}
            style="--sw: var({c.v})"
            onclick={() => setColor(menuIdx, c.key)}
          ></button>
        {/each}
      </div>
    {/if}
  </div>
</Popover>

<Popover bind:open={wikiOpen} anchor={wikiAnchor} placement={wikiPlacement} class="wikipop">
  <div role="presentation" onpointerenter={() => clearTimeout(hideT)} onpointerleave={() => hover(null, null)}>
    {#if wikiName}<WikiCard name={wikiName} count={wikiCount} onadd={addTag} exclude={promptTags} />{/if}
  </div>
</Popover>

<Dock bind:open={cardOpen} avoid={() => cardAnchor?.getBoundingClientRect()} label="Tag">
  {#if cardName}
    {#key cardName}
      <WikiCard name={cardName} compact actions={cardLock ? cardActs : undefined} onadd={addTag} exclude={promptTags} />
    {/key}
  {/if}
</Dock>

{#snippet cardActs()}
  {#if cardWeight !== null}
    <div class="wt" role="group" aria-label="Weight" onpointerdown={(e) => e.preventDefault()}>
      <IconButton icon="remove" label="Lower weight" size="sm" tip={false} onclick={() => stepCard(-0.1)} />
      <span class="wv">{cardWeight.toFixed(cardWeight * 100 % 10 ? 2 : 1)}</span>
      <IconButton icon="add" label="Raise weight" size="sm" tip={false} onclick={() => stepCard(0.1)} />
    </div>
  {/if}
  <Button
    size="sm"
    icon="lock"
    onpointerdown={(e: PointerEvent) => e.preventDefault()}
    onclick={() => {
      const f = cardLock
      cardOpen = false
      f?.()
    }}>Lock as boilerplate</Button
  >
{/snippet}

<Popover bind:open={saveOpen} anchor={saveBtn} placement="bottom-end" autofocus>
  <form
    class="save"
    onsubmit={(e) => {
      e.preventDefault()
      save()
    }}
  >
    <input class="inp" bind:value={saveName} placeholder="Name" aria-label="Prompt name" />
    <Button variant="primary" size="sm" type="submit" loading={saving}>Save</Button>
  </form>
</Popover>

<style>
  .pe {
    display: flex;
    flex-direction: column;
    border-radius: var(--r-md);
    background: var(--surface-2);
    transition: background var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease);
  }
  .pe:focus-within {
    background: var(--surface-3);
    box-shadow: inset 0 0 0 1px var(--focus-line);
  }
  .box {
    padding: 8px 10px 2px;
    cursor: text;
    font-size: var(--fs-md);
    line-height: 1.55;
  }
  .lk {
    --seg: var(--text-muted);
    display: inline-block;
    max-width: 100%;
    vertical-align: top;
    margin: 0 6px 4px 0;
    padding: 1px 7px 1px 2px;
    border-radius: var(--r-sm);
    background: color-mix(in srgb, var(--seg) 9%, var(--surface-1));
    box-shadow: inset 2px 0 0 color-mix(in srgb, var(--seg) 55%, var(--surface-4));
    color: var(--boilerplate);
    overflow-wrap: break-word;
    cursor: default;
    user-select: none;
    -webkit-user-select: none;
    -webkit-touch-callout: none;
    transition:
      background var(--dur-fast) var(--ease),
      box-shadow var(--dur-fast) var(--ease);
  }
  .pe:focus-within .lk {
    background: color-mix(in srgb, var(--seg) 9%, var(--surface-2));
  }
  .lk.menu {
    background: color-mix(in srgb, var(--seg) 16%, var(--surface-2));
  }
  .lk.lifted {
    position: relative;
    z-index: 2;
    background: color-mix(in srgb, var(--seg) 14%, var(--surface-4));
    box-shadow:
      inset 2px 0 0 color-mix(in srgb, var(--seg) 70%, var(--surface-4)),
      var(--shadow-2);
    transition: none;
    pointer-events: none;
  }
  .dragging,
  .dragging * {
    cursor: grabbing !important;
  }
  .lk .tag:hover {
    color: color-mix(in srgb, var(--c) 55%, var(--boilerplate));
  }
  .lk .off {
    text-decoration: line-through;
    text-decoration-color: color-mix(in srgb, var(--danger) 70%, transparent);
    opacity: 0.55;
  }
  .lk .lora {
    color: color-mix(in srgb, var(--tag-lora) 45%, var(--boilerplate));
  }
  .nudge {
    animation: nudge 360ms var(--ease);
  }
  @keyframes nudge {
    25% {
      background: var(--surface-4);
    }
    40% {
      transform: translateX(-2px);
    }
  }
  .lkbtn {
    display: inline-grid;
    place-items: center;
    vertical-align: -3px;
    width: 18px;
    height: 18px;
    margin-right: 2px;
    padding: 0;
    border: 0;
    border-radius: 3px;
    background: none;
    color: color-mix(in srgb, var(--seg) 45%, var(--text-faint));
    font-size: 15px;
    cursor: grab;
    touch-action: none;
  }
  .lkbtn:hover {
    background: var(--hover);
    color: var(--text);
  }
  .marker {
    position: fixed;
    z-index: var(--z-popover);
    border-radius: 1px;
    background: var(--accent);
    box-shadow: 0 0 6px var(--accent-glow);
    pointer-events: none;
    transition:
      left 80ms var(--ease),
      top 80ms var(--ease);
  }
  .foot {
    display: flex;
    align-items: flex-end;
    gap: var(--sp-2);
    padding: 0 4px 4px 10px;
    min-height: 32px;
  }
  .trig {
    flex: 1;
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    min-width: 0;
    padding-bottom: 3px;
  }
  .tools {
    display: flex;
    align-items: center;
    gap: 2px;
    margin-left: auto;
  }
  .count {
    padding: 0 6px;
    color: var(--text-faint);
    font-size: var(--fs-xs);
    font-variant-numeric: tabular-nums;
    cursor: default;
  }
  .count.over {
    color: var(--text-muted);
  }
  :global(.popover.wikipop) {
    padding: var(--sp-1);
  }
  :global(.popover.segmenu) {
    min-width: 200px;
  }
  .mi {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    width: 100%;
    min-height: 30px;
    padding: 0 8px;
    border: 0;
    border-radius: var(--r-sm);
    background: none;
    color: var(--text);
    font: inherit;
    font-size: var(--fs-sm);
    text-align: left;
    cursor: pointer;
  }
  .mi .icon {
    font-size: 18px;
    color: var(--text-muted);
  }
  .mi:hover:not(:disabled),
  .mi:focus-visible {
    background: var(--hover);
    box-shadow: none;
  }
  .mi:active:not(:disabled) {
    background: var(--pressed);
  }
  .mi:disabled {
    color: var(--text-faint);
    cursor: default;
  }
  .mi:disabled .icon {
    color: var(--text-faint);
  }
  .mi.danger,
  .mi.danger .icon {
    color: var(--danger);
  }
  .mi.tagrow .ml {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .ml {
    flex: 1;
    min-width: 0;
  }
  .hint {
    color: var(--text-faint);
    font-size: var(--fs-xs);
  }
  .msep {
    height: 1px;
    margin: 4px 2px;
    background: var(--hairline);
  }
  .sws {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 4px 6px 6px;
  }
  .sw {
    display: grid;
    place-items: center;
    width: 20px;
    height: 20px;
    padding: 0;
    border: 0;
    border-radius: var(--r-sm);
    background: color-mix(in srgb, var(--sw) 55%, var(--surface-4));
    cursor: pointer;
    transition: transform var(--dur-fast) var(--ease);
  }
  .sw:hover {
    transform: scale(1.1);
  }
  .sw[aria-checked='true'] {
    box-shadow:
      0 0 0 2px var(--surface-3),
      0 0 0 3px var(--accent);
  }
  .sw.auto {
    background: var(--surface-4);
    color: color-mix(in srgb, var(--sw) 70%, var(--text));
  }
  .sw.auto .icon {
    font-size: 14px;
  }
  .save {
    display: flex;
    gap: var(--sp-2);
    padding: 2px;
  }
  .inp {
    width: 200px;
    height: var(--control-h-sm);
    padding: 0 8px;
    border: 0;
    border-radius: var(--r-sm);
    background: var(--surface-2);
    color: var(--text);
    font: inherit;
    font-size: var(--fs-sm);
    outline: none;
  }
  .inp:focus-visible {
    box-shadow: inset 0 0 0 1px var(--focus-line);
  }
  .inp::placeholder {
    color: var(--text-faint);
  }
  @media (pointer: coarse) {
    .box {
      font-size: 16px;
    }
    .lk {
      padding: 2px 8px 2px 2px;
    }
    .lkbtn {
      width: 26px;
      height: 26px;
      vertical-align: -7px;
      font-size: 18px;
    }
    .mi {
      min-height: 44px;
      font-size: var(--fs-md);
    }
    .sws {
      gap: 10px;
      padding: 6px 8px 8px;
    }
    .sw {
      width: 30px;
      height: 30px;
    }
  }
  .wt {
    display: flex;
    align-items: center;
    gap: 2px;
    border-radius: var(--r-sm);
    background: var(--grad-2);
  }
  .wv {
    min-width: 36px;
    text-align: center;
    font-size: var(--fs-sm);
    font-variant-numeric: tabular-nums;
  }
</style>
