<script lang="ts" module>
  export type MenuItem =
    | { separator: true }
    | {
        label: string
        icon?: string
        danger?: boolean
        disabled?: boolean
        shortcut?: string
        checked?: boolean
        onselect?: () => void
      }
</script>

<script lang="ts">
  import type { Snippet } from 'svelte'
  import Popover from './Popover.svelte'
  import type { Anchor, Placement } from './util'

  interface Props {
    items: MenuItem[]
    open?: boolean
    anchor?: Anchor
    placement?: Placement
    label?: string
    class?: string
    style?: string
    trigger?: Snippet<[{ open: boolean; toggle: () => void }]>
  }
  let {
    items,
    open = $bindable(false),
    anchor,
    placement = 'bottom-start',
    label,
    class: klass,
    style,
    trigger,
  }: Props = $props()

  let wrap = $state<HTMLSpanElement>()
  let menu = $state<HTMLDivElement>()
  const anc = $derived(anchor ?? wrap)

  function toggle() {
    open = !open
  }
  function els() {
    return Array.from(menu?.querySelectorAll<HTMLElement>('[role^="menuitem"]:not([aria-disabled="true"])') ?? [])
  }
  function key(e: KeyboardEvent) {
    const list = els()
    const i = list.indexOf(document.activeElement as HTMLElement)
    let n = -1
    if (e.key === 'ArrowDown') n = (i + 1) % list.length
    else if (e.key === 'ArrowUp') n = (i - 1 + list.length) % list.length
    else if (e.key === 'Home') n = 0
    else if (e.key === 'End') n = list.length - 1
    else if (e.key === 'Tab') {
      open = false
      return
    } else return
    e.preventDefault()
    list[n]?.focus()
  }
  function run(it: Extract<MenuItem, { label: string }>) {
    if (it.disabled) return
    open = false
    if (anc instanceof HTMLElement) {
      const f = anc.querySelector<HTMLElement>('button, [tabindex]') ?? anc
      f.focus({ preventScroll: true })
    }
    it.onselect?.()
  }
  $effect(() => {
    if (open && menu) requestAnimationFrame(() => els()[0]?.focus({ preventScroll: true }))
  })
</script>

{#if trigger}
  <span class="trigger" bind:this={wrap}>{@render trigger({ open, toggle })}</span>
{/if}

<Popover bind:open anchor={anc} {placement} class={klass} {style}>
  <div bind:this={menu} class="menu" role="menu" tabindex="-1" aria-label={label} onkeydown={key}>
    {#each items as it, i (i)}
      {#if 'separator' in it}
        <div class="sep" role="separator"></div>
      {:else}
        <div
          class="item"
          class:danger={it.danger}
          role={it.checked === undefined ? 'menuitem' : 'menuitemcheckbox'}
          aria-checked={it.checked}
          aria-disabled={it.disabled || undefined}
          tabindex="-1"
          onclick={() => run(it)}
          onkeydown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              run(it)
            }
          }}
          onpointermove={(e) => !it.disabled && e.currentTarget.focus({ preventScroll: true })}
        >
          <span class="icon" aria-hidden="true">{it.checked ? 'check' : (it.icon ?? '')}</span>
          <span class="l">{it.label}</span>
          {#if it.shortcut}<span class="sc">{it.shortcut}</span>{/if}
        </div>
      {/if}
    {/each}
  </div>
</Popover>

<style>
  .trigger {
    display: inline-flex;
  }
  .menu {
    min-width: 180px;
    outline: none;
  }
  .item {
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 34px;
    padding: 0 10px 0 8px;
    border-radius: var(--r-sm);
    color: var(--text);
    cursor: pointer;
    outline: none;
    user-select: none;
  }
  .item .icon {
    width: 20px;
    font-size: 18px;
    color: var(--text-muted);
  }
  .item:focus,
  .item:focus-visible {
    background: var(--pressed);
    box-shadow: none;
  }
  .item:active {
    background: var(--grad-4);
  }
  .danger,
  .danger .icon {
    color: var(--danger);
  }
  .danger:focus {
    background: var(--danger-soft);
  }
  .item[aria-disabled='true'] {
    opacity: 0.4;
    cursor: default;
  }
  .l {
    flex: 1;
    white-space: nowrap;
  }
  .sc {
    margin-left: var(--sp-4);
    color: var(--text-faint);
    font-size: var(--fs-xs);
  }
  .sep {
    height: 1px;
    margin: 4px 6px;
    background: var(--hairline);
  }
  @media (pointer: coarse) {
    .item {
      min-height: var(--touch);
    }
  }
</style>
