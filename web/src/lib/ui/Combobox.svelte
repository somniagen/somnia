<script lang="ts" generics="T">
  import type { Snippet } from 'svelte'
  import type { HTMLInputAttributes } from 'svelte/elements'
  import Popover from './Popover.svelte'
  import Spinner from './Spinner.svelte'
  import { uid } from './util'

  interface Props extends Omit<HTMLInputAttributes, 'value' | 'onselect' | 'size'> {
    value?: string
    search: (q: string, signal: AbortSignal) => Promise<T[]> | T[]
    onselect?: (item: T) => void
    getLabel?: (item: T) => string
    debounce?: number
    minChars?: number
    icon?: string
    clearOnSelect?: boolean
    size?: 'sm' | 'md'
    item?: Snippet<[T, boolean]>
    empty?: Snippet<[string]>
  }
  let {
    value = $bindable(''),
    search,
    onselect,
    getLabel = (it: T) => String(it),
    debounce = 150,
    minChars = 1,
    icon = 'search',
    clearOnSelect = false,
    size = 'md',
    placeholder = 'Search',
    class: klass,
    style,
    item,
    empty,
    ...rest
  }: Props = $props()

  const lid = uid('cbx')
  let results = $state<T[]>([])
  let open = $state(false)
  let loading = $state(false)
  let active = $state(-1)
  let wrap = $state<HTMLDivElement>()
  let input: HTMLInputElement
  let timer: ReturnType<typeof setTimeout> | undefined
  let ctrl: AbortController | null = null
  let queried = $state('')

  function run(q: string) {
    clearTimeout(timer)
    ctrl?.abort()
    if (q.trim().length < minChars) {
      results = []
      loading = false
      open = false
      return
    }
    timer = setTimeout(async () => {
      const c = new AbortController()
      ctrl = c
      loading = true
      try {
        const r = await search(q, c.signal)
        if (c.signal.aborted) return
        results = r
        queried = q
        active = r.length ? 0 : -1
        open = document.activeElement === input
      } catch (e) {
        if (!c.signal.aborted) results = []
      } finally {
        if (ctrl === c) loading = false
      }
    }, debounce)
  }
  function pick(it: T) {
    onselect?.(it)
    value = clearOnSelect ? '' : getLabel(it)
    open = false
    results = clearOnSelect ? [] : results
    input.focus()
  }
  function key(e: KeyboardEvent) {
    const n = results.length
    if (e.key === 'ArrowDown' && n) {
      if (!open) open = true
      else active = (active + 1) % n
    } else if (e.key === 'ArrowUp' && n) active = (active - 1 + n) % n
    else if (e.key === 'Enter' && open && active >= 0 && results[active] !== undefined) pick(results[active])
    else if (e.key === 'Escape' && open) open = false
    else return
    e.preventDefault()
  }
</script>

<div bind:this={wrap} class={['cbx', size, klass]} {style}>
  {#if icon}<span class="icon lead" aria-hidden="true">{icon}</span>{/if}
  <input
    bind:this={input}
    type="text"
    role="combobox"
    autocomplete="off"
    spellcheck="false"
    aria-autocomplete="list"
    aria-expanded={open}
    aria-controls={lid}
    aria-activedescendant={open && active >= 0 ? `${lid}-${active}` : undefined}
    {placeholder}
    bind:value
    oninput={() => run(value)}
    onfocus={() => results.length && value.trim().length >= minChars && (open = true)}
    onblur={() => (open = false)}
    onkeydown={key}
    {...rest}
  />
  {#if loading}<Spinner size={14} label="Searching" />{/if}
</div>

<Popover bind:open anchor={wrap} matchWidth>
  <div id={lid} role="listbox" class="list">
    {#each results as r, i (i)}
      <div
        id="{lid}-{i}"
        class="opt"
        class:active={i === active}
        role="option"
        tabindex="-1"
        aria-selected={i === active}
        onpointerdown={(e) => e.preventDefault()}
        onpointermove={() => (active = i)}
        onclick={() => pick(r)}
        onkeydown={() => {}}
      >
        {#if item}{@render item(r, i === active)}{:else}{getLabel(r)}{/if}
      </div>
    {:else}
      <div class="none">
        {#if empty}{@render empty(queried)}{:else}No results{/if}
      </div>
    {/each}
  </div>
</Popover>

<style>
  .cbx {
    --h: var(--control-h);
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    height: var(--h);
    padding: 0 10px;
    border-radius: var(--r-md);
    background: var(--grad-2);
    color: var(--text-faint);
    transition: background var(--dur-fast) var(--ease);
  }
  .sm {
    --h: var(--control-h-sm);
    border-radius: var(--r-sm);
  }
  .cbx:hover {
    background: var(--grad-3);
  }
  .cbx:focus-within {
    background: var(--grad-3);
    box-shadow: inset 0 0 0 1px var(--focus-line);
  }
  .lead {
    font-size: 18px;
  }
  input {
    flex: 1;
    min-width: 0;
    height: 100%;
    border: 0;
    background: none;
    color: var(--text);
    font: inherit;
    outline: none;
  }
  input:focus-visible {
    box-shadow: none;
  }
  input::placeholder {
    color: var(--text-faint);
  }
  .opt {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: 34px;
    padding: 6px 10px;
    border-radius: var(--r-sm);
    cursor: pointer;
  }
  .opt.active {
    background: var(--pressed);
  }
  .none {
    padding: 10px;
    color: var(--text-faint);
    font-size: var(--fs-sm);
  }
  @media (pointer: coarse) {
    .cbx {
      --h: var(--touch);
    }
    .opt {
      min-height: var(--touch);
    }
  }
</style>
