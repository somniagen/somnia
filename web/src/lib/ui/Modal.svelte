<script lang="ts">
  import type { Snippet } from 'svelte'
  import IconButton from './IconButton.svelte'
  import { uid } from './util'

  interface Props {
    open?: boolean
    title?: string
    width?: number | string
    dismissible?: boolean
    class?: string
    style?: string
    onclose?: () => void
    header?: Snippet
    footer?: Snippet
    children?: Snippet
  }
  let {
    open = $bindable(false),
    title,
    width = 480,
    dismissible = true,
    class: klass,
    style,
    onclose,
    header,
    footer,
    children,
  }: Props = $props()

  const tid = uid('modal')
  let dlg: HTMLDialogElement
  let shown = $state(false)
  let downOnSelf = false
  let ret: Element | null = null

  function close() {
    if (!open) return
    open = false
    onclose?.()
  }

  $effect(() => {
    if (open && !dlg.open) {
      ret = document.activeElement
      dlg.showModal()
      document.documentElement.style.overflow = 'hidden'
      requestAnimationFrame(() => (shown = true))
    } else if (!open && dlg.open) {
      shown = false
      const done = () => {
        if (open) return
        dlg.close()
        document.documentElement.style.overflow = ''
        if (ret instanceof HTMLElement) ret.focus({ preventScroll: true })
      }
      const ms = parseFloat(getComputedStyle(dlg).getPropertyValue('--dur')) || 0
      setTimeout(done, ms + 20)
    }
  })
  $effect(() => () => {
    if (dlg?.open) document.documentElement.style.overflow = ''
  })
</script>

<dialog
  bind:this={dlg}
  class="modal"
  class:shown
  aria-labelledby={title ? tid : undefined}
  oncancel={(e) => {
    e.preventDefault()
    if (dismissible) close()
  }}
  onpointerdown={(e) => (downOnSelf = e.target === dlg)}
  onclick={(e) => {
    if (dismissible && downOnSelf && e.target === dlg) close()
  }}
>
  <div
    class={['panel', klass]}
    style="--w: {typeof width === 'number' ? `${width}px` : width}; {style ?? ''}"
  >
    {#if header}
      {@render header()}
    {:else if title || dismissible}
      <header>
        {#if title}<h2 id={tid}>{title}</h2>{/if}
        {#if dismissible}<IconButton icon="close" label="Close" size="sm" tip={false} onclick={close} />{/if}
      </header>
    {/if}
    <div class="body">{@render children?.()}</div>
    {#if footer}<footer>{@render footer()}</footer>{/if}
  </div>
</dialog>

<style>
  .modal {
    position: fixed;
    inset: 0;
    width: 100%;
    height: 100%;
    max-width: none;
    max-height: none;
    margin: 0;
    padding: var(--sp-4);
    border: 0;
    display: grid;
    place-items: center;
    background: var(--scrim);
    color: var(--text);
    opacity: 0;
    transition: opacity var(--dur) var(--ease);
    overscroll-behavior: contain;
  }
  .modal:not([open]) {
    display: none;
  }
  .modal::backdrop {
    background: transparent;
  }
  .modal.shown {
    opacity: 1;
  }
  .panel {
    display: flex;
    flex-direction: column;
    width: min(var(--w), 100%);
    max-height: calc(100dvh - 32px);
    border-radius: var(--r-lg);
    background: var(--grad-1);
    border: 1px solid var(--hairline);
    box-shadow: var(--shadow-3);
    transform: translateY(8px) scale(0.98);
    transition: transform var(--dur) var(--ease);
  }
  .shown .panel {
    transform: none;
  }
  header {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    padding: var(--sp-3) var(--sp-3) 0 var(--sp-5);
    min-height: 52px;
  }
  h2 {
    flex: 1;
    margin: 0;
    font-size: var(--fs-lg);
    font-weight: 600;
  }
  header :global(.ib) {
    margin-left: auto;
  }
  .body {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: var(--sp-3) var(--sp-5) var(--sp-5);
  }
  footer {
    display: flex;
    justify-content: flex-end;
    gap: var(--sp-2);
    padding: 0 var(--sp-5) var(--sp-5);
  }
</style>
