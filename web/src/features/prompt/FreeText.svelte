<script lang="ts">
  import { Popover, IconButton, Kbd, Button, coarse } from '$lib/ui'
  import Dock from './Dock.svelte'
  import type { Tag } from '$lib/types'
  import { categories, colorOf, compact, requestCategories, searchTags } from './tags.svelte'
  import { displayTag, fragmentAt, reweight, tokenize, weightAt } from './tokenize'

  interface Props {
    value: string
    placeholder?: string
    minRows?: number
    el?: HTMLTextAreaElement
    onlock?: (start: number, end: number) => void
    onedge?: (dir: 'prev' | 'next') => void
    onbackspaceempty?: () => void
    onhover?: (name: string | null, anchor: HTMLElement | null, immediate?: boolean, count?: number) => void
    ontag?: (name: string, anchor: HTMLElement, range: [number, number]) => void
    onblur?: () => void
    // typing or selecting text, so transient tag ui should get out of the way
    onedit?: () => void
  }
  let {
    value = $bindable(''),
    placeholder = '',
    minRows = 1,
    el = $bindable(),
    onlock,
    onedge,
    onbackspaceempty,
    onhover,
    ontag,
    onblur,
    onedit,
  }: Props = $props()

  let mirror = $state<HTMLDivElement>()
  const tokens = $derived(tokenize(value))

  $effect(() => {
    requestCategories(tokens.filter((t) => t.kind === 'tag').map((t) => t.tag!))
  })

  const mac = typeof navigator !== 'undefined' && /mac|iphone|ipad/i.test(navigator.platform)

  function caretRect(offset: number): DOMRect | null {
    if (!mirror) return null
    const spans = mirror.querySelectorAll<HTMLElement>('[data-s]')
    let span: HTMLElement | null = null
    for (const s of spans) {
      if (Number(s.dataset.s) <= offset) span = s
      else break
    }
    if (!span || !span.firstChild) {
      const r = mirror.getBoundingClientRect()
      const cs = getComputedStyle(mirror)
      return new DOMRect(r.left + parseFloat(cs.paddingLeft), r.top + parseFloat(cs.paddingTop), 0, parseFloat(cs.lineHeight) || 20)
    }
    const node = span.firstChild as Text
    const local = Math.min(offset - Number(span.dataset.s), node.length)
    const range = document.createRange()
    range.setStart(node, local)
    range.setEnd(node, local)
    const rects = range.getClientRects()
    if (rects.length) return rects[rects.length - 1]
    if (local < node.length) {
      range.setEnd(node, local + 1)
      const r = range.getClientRects()[0]
      if (r) return new DOMRect(r.left, r.top, 0, r.height)
    }
    return span.getBoundingClientRect()
  }

  function hit(x: number, y: number): HTMLElement | null {
    if (!mirror) return null
    const b = mirror.getBoundingClientRect()
    if (x < b.left || x > b.right || y < b.top || y > b.bottom) return null
    for (const s of mirror.querySelectorAll<HTMLElement>('[data-tag]')) {
      for (const r of s.getClientRects()) if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return s
    }
    return null
  }

  // autocomplete
  let acOpen = $state(false)
  let items = $state<Tag[]>([])
  let active = $state(0)
  let frag: { start: number; end: number; query: string } | null = null
  let acAnchor = $state<{ x: number; y: number }>({ x: 0, y: 0 })
  let acEl = $state<HTMLDivElement>()
  let ctrl: AbortController | null = null
  let acTimer: ReturnType<typeof setTimeout> | undefined
  let suppress = false
  let composing = false

  function closeAc() {
    acOpen = false
    ctrl?.abort()
    clearTimeout(acTimer)
    frag = null
  }

  function runAc() {
    if (!el || composing) return
    if (suppress) {
      suppress = false
      closeAc()
      return
    }
    const f = el.selectionStart === el.selectionEnd ? fragmentAt(value, el.selectionStart) : null
    if (!f) return closeAc()
    frag = f
    clearTimeout(acTimer)
    acTimer = setTimeout(async () => {
      ctrl?.abort()
      const c = (ctrl = new AbortController())
      try {
        const res = await searchTags(f.query, c.signal)
        if (c.signal.aborted || frag !== f) return
        items = res
        active = 0
        const r = caretRect(f.start)
        if (r) acAnchor = { x: r.left - 6, y: r.bottom }
        acOpen = res.length > 0 && document.activeElement === el
      } catch {}
    }, 40)
  }

  function replace(s: number, e: number, text: string, caret?: number) {
    if (!el) return
    el.focus()
    el.setSelectionRange(s, e)
    if (!document.execCommand('insertText', false, text)) {
      el.setRangeText(text, s, e, 'end')
      el.dispatchEvent(new Event('input', { bubbles: true }))
    }
    if (caret !== undefined) el.setSelectionRange(caret, caret)
  }

  function accept(t: Tag) {
    const f = frag
    if (!f || !el) return
    let ins = displayTag(t.name)
    if (f.start > 0 && value[f.start - 1] === ',') ins = ' ' + ins
    const after = value.slice(f.end)
    const comma = /^\s*,\s*/.exec(after)
    suppress = true
    closeAc()
    if (comma) replace(f.start, f.end, ins, f.start + ins.length + comma[0].length)
    else if (/^\s*[)\]}:]/.test(after)) replace(f.start, f.end, ins)
    else replace(f.start, f.end, ins + ', ')
  }

  // selection lock popover
  let selOpen = $state(false)
  let selAnchor = $state<{ x: number; y: number }>({ x: 0, y: 0 })
  let selWeight = $state(1)

  function checkSel() {
    if (!el || document.activeElement !== el) return (selOpen = false)
    const s = el.selectionStart
    const e = el.selectionEnd
    if (s === e || !value.slice(s, e).trim() || !onlock) return (selOpen = false)
    onedit?.()
    const r = caretRect(s)
    if (r) selAnchor = { x: r.left, y: r.top }
    selWeight = weightAt(value, s, e)?.weight ?? 1
    selOpen = true
  }

  function lockSel() {
    if (!el) return
    const s = el.selectionStart
    const e = el.selectionEnd
    selOpen = false
    if (s !== e && value.slice(s, e).trim()) onlock?.(s, e)
  }

  $effect(() => {
    if (!el) return
    const on = () => requestAnimationFrame(checkSel)
    document.addEventListener('selectionchange', on)
    return () => document.removeEventListener('selectionchange', on)
  })

  // a1111 style (tag:1.1) weight on the selection or the item under the caret
  function stepWeight(delta: number) {
    if (!el) return false
    const r = reweight(value, el.selectionStart, el.selectionEnd, delta)
    if (!r) return false
    suppress = true
    closeAc()
    replace(r.start, r.end, r.out)
    el.setSelectionRange(r.sel[0], r.sel[1])
    selWeight = r.weight
    return true
  }

  function keydown(e: KeyboardEvent) {
    if (!el || e.isComposing || composing) return
    if ((e.ctrlKey || e.metaKey) && !e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      if (stepWeight((e.key === 'ArrowUp' ? 1 : -1) * (e.shiftKey ? 0.05 : 0.1))) e.preventDefault()
      return
    }
    if (acOpen && items.length) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        active = (active + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length
        acEl?.querySelector(`[data-i="${active}"]`)?.scrollIntoView({ block: 'nearest' })
        return
      }
      if ((e.key === 'Enter' && !e.shiftKey) || e.key === 'Tab') {
        e.preventDefault()
        accept(items[active])
        return
      }
    }
    const mod = mac ? e.metaKey : e.ctrlKey
    if (mod && e.shiftKey && e.key.toLowerCase() === 'l') {
      e.preventDefault()
      lockSel()
      return
    }
    const s = el.selectionStart
    const en = el.selectionEnd
    if (s !== en || e.shiftKey || e.altKey || mod) return
    if ((e.key === 'ArrowLeft' || e.key === 'ArrowUp') && s === 0 && onedge) {
      e.preventDefault()
      onedge('prev')
    } else if ((e.key === 'ArrowRight' || e.key === 'ArrowDown') && s === value.length && onedge) {
      e.preventDefault()
      onedge('next')
    } else if (e.key === 'Backspace' && value === '' && onbackspaceempty) {
      e.preventDefault()
      onbackspaceempty()
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'Home' || e.key === 'End') closeAc()
  }

  // hover and tap
  let raf = 0
  let hovered: HTMLElement | null = null
  let press: { x: number; y: number; at: number; focused: boolean; caret: number } | null = null

  function itemRange(start: number, end: number): [number, number] {
    let a = start
    let b = end
    while (a > 0 && value[a - 1] !== ',' && value[a - 1] !== '\n') a--
    while (b < value.length && value[b] !== ',' && value[b] !== '\n') b++
    const item = value.slice(a, b).replace(/\\./g, '')
    const opens = (item.match(/[([{]/g) ?? []).length
    const closes = (item.match(/[)\]}]/g) ?? []).length
    if (opens !== closes) return [start, end]
    while (a < b && /\s/.test(value[a])) a++
    while (b > a && /\s/.test(value[b - 1])) b--
    return [a, b]
  }

  function setHover(s: HTMLElement | null, immediate = false) {
    if (s === hovered && !immediate) return
    hovered = s
    onhover?.(s?.dataset.tag ?? null, s, immediate)
  }
  function move(e: PointerEvent) {
    if (press && Math.hypot(e.clientX - press.x, e.clientY - press.y) > 8) cancelPress()
    if (e.pointerType === 'touch') return
    cancelAnimationFrame(raf)
    const { clientX: x, clientY: y } = e
    raf = requestAnimationFrame(() => setHover(hit(x, y)))
  }
  function down(e: PointerEvent) {
    if (e.pointerType !== 'touch' || !el) return
    const focused = document.activeElement === el && el.selectionStart === el.selectionEnd
    press = { x: e.clientX, y: e.clientY, at: performance.now(), focused, caret: el.selectionStart }
  }
  function up(e: PointerEvent) {
    const p = press
    press = null
    if (!p || e.pointerType !== 'touch' || performance.now() - p.at > 450 || !ontag) return
    setTimeout(() => {
      if (!el || el.selectionStart !== el.selectionEnd) return
      const s = hit(p.x, p.y)
      if (!s?.dataset.tag) return
      const st = Number(s.dataset.s)
      const en = st + (s.textContent?.length ?? 0)
      // the first tap only places the caret; tapping the same tag again opens its card
      if (!p.focused || p.caret < st || p.caret > en) return
      ontag(s.dataset.tag, s, itemRange(st, en))
    }, 60)
  }
  function cancelPress() {
    press = null
  }
  function leave(e: PointerEvent) {
    cancelPress()
    cancelAnimationFrame(raf)
    if (e.pointerType !== 'touch') setHover(null)
  }

  function rowHover(i: number, row: HTMLElement | null) {
    onhover?.(row ? items[i].name : null, row, false, row ? items[i].count : undefined)
  }

  const cls = (t: (typeof tokens)[number]) => (t.kind === 'tag' ? 't' : t.kind)
</script>

<div class="ft" style="--rows: {minRows}">
  <div class="mirror" bind:this={mirror} aria-hidden="true">{#each tokens as t (t.start)}<span data-s={t.start} data-tag={t.tag} class={cls(t)} style={t.kind === 'tag' ? `color: ${colorOf(categories.get(t.tag!))}` : undefined}>{t.text}</span>{/each}{' '}</div>
  <textarea
    bind:this={el}
    bind:value
    rows="1"
    {placeholder}
    spellcheck="false"
    autocomplete="off"
    autocapitalize="off"
    aria-autocomplete="list"
    oninput={() => {
      onedit?.()
      runAc()
    }}
    onkeydown={keydown}
    oncompositionstart={() => (composing = true)}
    oncompositionend={() => {
      composing = false
      runAc()
    }}
    onblur={() => {
      setTimeout(() => {
        if (document.activeElement !== el) {
          closeAc()
          selOpen = false
          onblur?.()
        }
      }, 120)
    }}
    onpointermove={move}
    onpointerdown={down}
    onpointerup={up}
    onpointercancel={cancelPress}
    onpointerleave={leave}
    onscroll={() => mirror && el && (mirror.scrollTop = el.scrollTop)}
  ></textarea>
</div>

{#if coarse.current}
  <Dock bind:open={acOpen} avoid={() => (frag ? caretRect(frag.start) : null)} label="Tag suggestions" onclose={closeAc} class="acdock">
    <div role="listbox" tabindex="-1" aria-label="Tag suggestions" bind:this={acEl}>{@render rows()}</div>
  </Dock>
{:else}
  <Popover bind:open={acOpen} anchor={acAnchor} placement="bottom-start" bind:el={acEl} class="ac" onclose={closeAc}>
    <div role="listbox" tabindex="-1" aria-label="Tag suggestions" onpointerleave={() => rowHover(0, null)}>{@render rows()}</div>
  </Popover>
{/if}

{#snippet rows()}
    {#each items as t, i (t.name)}
      <div
        class="row"
        class:active={i === active}
        role="option"
        tabindex="-1"
        aria-selected={i === active}
        data-i={i}
        onpointerdown={(e) => e.preventDefault()}
        onclick={() => accept(t)}
        onkeydown={() => {}}
        onpointerenter={(e) => {
          active = i
          if (e.pointerType !== 'touch') rowHover(i, e.currentTarget)
        }}
      >
        <span class="dot" style="background: {colorOf(t.category)}"></span>
        <span class="nm" style="color: {colorOf(t.category)}">
          {t.name.replace(/_/g, ' ')}
          {#if t.matchedAlias}<span class="alias">{t.matchedAlias.replace(/_/g, ' ')}</span>{/if}
        </span>
        <span class="cnt">{compact(t.count)}</span>
      </div>
    {/each}
{/snippet}

{#if coarse.current}
  <Dock bind:open={selOpen} avoid={() => caretRect(el?.selectionEnd ?? 0)} keep={() => [el]} label="Selection">
    <div class="seldock" onpointerdown={(e) => e.preventDefault()} role="presentation">
      <Button icon="lock" size="sm" full onclick={lockSel}>Lock as boilerplate</Button>
      <div class="wt" aria-label="Weight">
        <IconButton icon="remove" label="Lower weight" size="sm" tip={false} onclick={() => stepWeight(-0.1)} />
        <span class="wv">{selWeight.toFixed(selWeight * 100 % 10 ? 2 : 1)}</span>
        <IconButton icon="add" label="Raise weight" size="sm" tip={false} onclick={() => stepWeight(0.1)} />
      </div>
    </div>
  </Dock>
{:else}
  <Popover bind:open={selOpen} anchor={selAnchor} placement="top-start" class="selpop" dismissible={false}>
    <div class="sel" onpointerdown={(e) => e.preventDefault()} role="presentation">
      <IconButton icon="lock" label="Mark as boilerplate" size="sm" tip="bottom" onclick={lockSel} />
      <span class="kb"><Kbd>{mac ? 'Cmd' : 'Ctrl'}+Shift+L</Kbd></span>
      <span class="kb">weight <Kbd>{mac ? 'Cmd' : 'Ctrl'}+Up/Down</Kbd></span>
    </div>
  </Popover>
{/if}

<style>
  .ft {
    display: grid;
    position: relative;
  }
  .mirror,
  textarea {
    grid-area: 1 / 1;
    margin: 0;
    padding: 2px 0;
    border: 0;
    font: inherit;
    font-size: var(--fs-md);
    line-height: 1.55;
    letter-spacing: normal;
    tab-size: 4;
    white-space: pre-wrap;
    overflow-wrap: break-word;
    word-break: normal;
    min-height: calc(var(--rows) * 1.55em + 4px);
  }
  .mirror {
    color: var(--text);
    pointer-events: none;
    overflow: hidden;
  }
  textarea {
    width: 100%;
    height: 100%;
    resize: none;
    overflow: hidden;
    background: transparent;
    color: transparent;
    -webkit-text-fill-color: transparent;
    caret-color: var(--text);
    outline: none;
    box-shadow: none;
    z-index: 1;
  }
  textarea::placeholder {
    color: var(--text-faint);
    -webkit-text-fill-color: var(--text-faint);
  }
  textarea::selection {
    background: color-mix(in srgb, var(--accent) 24%, transparent);
  }
  .sep {
    color: var(--text-faint);
  }
  .syntax,
  .weight {
    color: var(--text-muted);
  }
  .weight {
    background: var(--surface-4);
    border-radius: 3px;
  }
  .lora {
    color: var(--tag-lora);
    background: color-mix(in srgb, var(--tag-lora) 12%, transparent);
    border-radius: 3px;
  }
  .break {
    color: var(--warning);
    background: var(--warning-soft);
    border-radius: 3px;
  }
  :global(.popover.ac) {
    width: min(340px, calc(100vw - 16px));
    max-height: min(300px, 50dvh);
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: 30px;
    padding: 0 8px;
    border-radius: var(--r-sm);
    cursor: pointer;
    font-size: var(--fs-sm);
    user-select: none;
  }
  .row.active {
    background: var(--pressed);
  }
  .dot {
    flex: none;
    width: 7px;
    height: 7px;
    border-radius: 50%;
  }
  .nm {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .alias {
    margin-left: 6px;
    color: var(--text-faint);
  }
  .alias::before {
    content: '<- ';
  }
  .cnt {
    color: var(--text-faint);
    font-size: var(--fs-xs);
    font-variant-numeric: tabular-nums;
  }
  :global(.dock.acdock) {
    padding: var(--sp-1);
  }
  .seldock {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    padding: var(--sp-1);
  }
  :global(.popover.selpop) {
    padding: 2px;
  }
  .sel {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .kb {
    padding-right: 6px;
    color: var(--text-faint);
    font-size: var(--fs-xs);
  }
  @media (pointer: coarse) {
    .mirror,
    textarea {
      font-size: 16px;
    }
    .row {
      min-height: 44px;
      padding: 0 12px;
      font-size: var(--fs-md);
      gap: var(--sp-3);
    }
    .cnt {
      font-size: var(--fs-sm);
    }
    .kb {
      display: none;
    }
  }
  .wt {
    flex: none;
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
