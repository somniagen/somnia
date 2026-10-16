<script lang="ts" generics="T">
  import type { Snippet } from 'svelte'
  import BottomSheet from './BottomSheet.svelte'
  import Popover from './Popover.svelte'
  import { labelOf, mobile, normalize, uid, type Item } from './util'

  interface Props {
    items: (T | Item<T>)[]
    value?: T
    placeholder?: string
    label?: string
    searchable?: boolean
    disabled?: boolean
    size?: 'sm' | 'md'
    id?: string
    icon?: string
    class?: string
    style?: string
    item?: Snippet<[Item<T>, boolean]>
    onchange?: (v: T) => void
  }
  let {
    items,
    value = $bindable(),
    placeholder = 'Select',
    label,
    searchable,
    disabled = false,
    size = 'md',
    id,
    icon,
    class: klass,
    style,
    item,
    onchange,
  }: Props = $props()

  const lid = uid('sel')
  const list = $derived(normalize(items))
  const current = $derived(list.find((it) => it.value === value))
  const canSearch = $derived(searchable ?? list.length > 8)

  let open = $state(false)
  let q = $state('')
  let active = $state(0)
  let trigger = $state<HTMLButtonElement>()
  let listEl = $state<HTMLDivElement>()
  let typed = ''
  let typedAt = 0

  const filtered = $derived.by(() => {
    const s = q.trim().toLowerCase()
    if (!s) return list
    return list.filter((it) => labelOf(it).toLowerCase().includes(s) || it.hint?.toLowerCase().includes(s))
  })

  function show() {
    if (disabled) return
    lastPt = ''
    q = ''
    active = Math.max(0, list.findIndex((it) => it.value === value))
    open = true
  }
  function choose(it: Item<T>) {
    if (it.disabled) return
    open = false
    if (it.value !== value) {
      value = it.value
      onchange?.(it.value)
    }
    trigger?.focus({ preventScroll: true })
  }
  let lastPt = ''
  function hover(e: PointerEvent, i: number) {
    const pt = `${e.screenX},${e.screenY}`
    const first = !lastPt
    if (pt === lastPt) return
    lastPt = pt
    if (first) return
    active = i
  }
  function moveActive(d: number) {
    const n = filtered.length
    if (!n) return
    let i = active
    for (let k = 0; k < n; k++) {
      i = (i + d + n) % n
      if (!filtered[i].disabled) break
    }
    active = i
  }
  function listKey(e: KeyboardEvent) {
    if (e.key === 'ArrowDown') moveActive(1)
    else if (e.key === 'ArrowUp') moveActive(-1)
    else if (e.key === 'Home') active = 0
    else if (e.key === 'End') active = filtered.length - 1
    else if (e.key === 'Enter' || (e.key === ' ' && !canSearch)) {
      const it = filtered[active]
      if (it) choose(it)
    } else if (e.key === 'Tab') {
      open = false
      return
    } else if (!canSearch && e.key.length === 1) {
      const now = performance.now()
      typed = now - typedAt > 600 ? e.key : typed + e.key
      typedAt = now
      const i = filtered.findIndex((it) => labelOf(it).toLowerCase().startsWith(typed.toLowerCase()))
      if (i >= 0) active = i
    } else return
    e.preventDefault()
  }
  function triggerKey(e: KeyboardEvent) {
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
      e.preventDefault()
      show()
    }
  }

  $effect(() => {
    if (!open || !listEl) return
    void filtered
    const el = listEl.querySelector<HTMLElement>(`[data-i="${active}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  })
</script>

{#snippet options(big: boolean)}
  {#if canSearch}
    <div class="search" class:big>
      <span class="icon" aria-hidden="true">search</span>
      <!-- svelte-ignore a11y_autofocus -->
      <input
        type="text"
        placeholder="Search"
        aria-label="Search"
        aria-controls={lid}
        aria-activedescendant={filtered[active] ? `${lid}-${active}` : undefined}
        bind:value={q}
        oninput={() => (active = 0)}
        onkeydown={listKey}
        autofocus={!big}
      />
    </div>
  {/if}
  <div
    bind:this={listEl}
    id={lid}
    class="list"
    class:big
    role="listbox"
    tabindex={canSearch ? -1 : 0}
    aria-label={label}
    aria-activedescendant={filtered[active] ? `${lid}-${active}` : undefined}
    onkeydown={listKey}
  >
    {#each filtered as it, i (i)}
      {@const sel = it.value === value}
      <div
        id="{lid}-{i}"
        data-i={i}
        class="opt"
        class:active={i === active}
        class:sel
        class:disabled={it.disabled}
        role="option"
        tabindex="-1"
        aria-selected={sel}
        aria-disabled={it.disabled}
        onpointermove={(e) => hover(e, i)}
        onclick={() => choose(it)}
        onkeydown={() => {}}
      >
        {#if item}
          {@render item(it, sel)}
        {:else}
          {#if it.icon}<span class="icon" aria-hidden="true">{it.icon}</span>{/if}
          <span class="ol">{labelOf(it)}</span>
          {#if it.hint}<span class="hint">{it.hint}</span>{/if}
        {/if}
        {#if sel}<span class="icon check" aria-hidden="true">check</span>{/if}
      </div>
    {:else}
      <div class="none">No matches</div>
    {/each}
  </div>
{/snippet}

<button
  bind:this={trigger}
  type="button"
  {id}
  class={['select', size, klass, { open }]}
  {style}
  {disabled}
  aria-haspopup="listbox"
  aria-expanded={open}
  aria-label={label}
  onclick={() => (open ? (open = false) : show())}
  onkeydown={triggerKey}
>
  {#if icon || current?.icon}<span class="icon lead" aria-hidden="true">{current?.icon ?? icon}</span>{/if}
  <span class="val" class:ph={!current}>{current ? labelOf(current) : placeholder}</span>
  <span class="icon chev" aria-hidden="true">expand_more</span>
</button>

{#if mobile.current}
  <BottomSheet bind:open title={label} snaps={list.length > 10 ? [0.6, 0.92] : undefined}>
    {@render options(true)}
  </BottomSheet>
{:else}
  <Popover bind:open anchor={trigger} matchWidth autofocus={!canSearch}>
    {@render options(false)}
  </Popover>
{/if}

<style>
  .select {
    --h: var(--control-h);
    display: inline-flex;
    align-items: center;
    gap: var(--sp-2);
    height: var(--h);
    min-width: 0;
    padding: 0 8px 0 12px;
    border: 0;
    border-radius: var(--r-md);
    background: var(--grad-2);
    color: var(--text);
    font: inherit;
    font-size: var(--fs-md);
    text-align: left;
    cursor: pointer;
    transition:
      background var(--dur-fast) var(--ease),
      transform var(--dur-fast) var(--ease);
  }
  .sm {
    --h: var(--control-h-sm);
    font-size: var(--fs-sm);
    border-radius: var(--r-sm);
  }
  .select:hover:not(:disabled),
  .select.open {
    background: var(--grad-3);
  }
  .select:active:not(:disabled) {
    transform: scale(0.985);
  }
  .select:disabled {
    opacity: 0.45;
    cursor: default;
  }
  .val {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .ph {
    color: var(--text-faint);
  }
  .lead {
    font-size: 18px;
    color: var(--text-muted);
  }
  .chev {
    color: var(--text-faint);
    transition: transform var(--dur) var(--ease);
  }
  .open .chev {
    transform: rotate(180deg);
  }
  .search {
    position: sticky;
    top: calc(var(--sp-1) * -1);
    z-index: 1;
    display: flex;
    align-items: center;
    gap: 6px;
    margin: calc(var(--sp-1) * -1) calc(var(--sp-1) * -1) var(--sp-1);
    padding: 0 10px;
    height: 40px;
    background: var(--grad-3);
    box-shadow: 0 1px 0 var(--hairline);
    color: var(--text-faint);
  }
  .search .icon {
    font-size: 18px;
  }
  .search input {
    flex: 1;
    min-width: 0;
    height: 100%;
    border: 0;
    background: none;
    color: var(--text);
    font: inherit;
    outline: none;
  }
  .search input:focus-visible {
    box-shadow: none;
  }
  .search.big {
    position: static;
    margin: 0 0 var(--sp-2);
    height: var(--touch);
    border-radius: var(--r-md);
    background: var(--grad-2);
    box-shadow: none;
  }
  .list {
    outline: none;
  }
  .opt {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: 34px;
    padding: 6px 10px;
    border-radius: var(--r-sm);
    color: var(--text);
    cursor: pointer;
    user-select: none;
  }
  .big .opt {
    min-height: var(--touch);
    padding: 8px 12px;
    border-radius: var(--r-md);
  }
  .opt.active {
    background: var(--hover);
  }
  .list:focus-visible .opt.active,
  .search:focus-within + .list .opt.active {
    background: var(--pressed);
  }
  .opt.sel {
    color: var(--accent-strong);
  }
  .opt.disabled {
    opacity: 0.4;
    cursor: default;
  }
  .opt .icon {
    font-size: 18px;
    color: var(--text-muted);
  }
  .opt.sel .icon {
    color: inherit;
  }
  .ol {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .hint {
    color: var(--text-faint);
    font-size: var(--fs-sm);
  }
  .check {
    margin-left: auto;
  }
  .none {
    padding: 10px;
    color: var(--text-faint);
    font-size: var(--fs-sm);
  }
  @media (pointer: coarse) {
    .select {
      min-height: var(--touch);
    }
  }
</style>
