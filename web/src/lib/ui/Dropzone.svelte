<script lang="ts">
  import type { Snippet } from 'svelte'

  interface Props {
    accept?: string
    multiple?: boolean
    paste?: boolean
    disabled?: boolean
    icon?: string
    title?: string
    hint?: string
    compact?: boolean
    class?: string
    style?: string
    onfiles: (files: File[]) => void
    children?: Snippet<[boolean]>
  }
  let {
    accept = 'image/*',
    multiple = false,
    paste = true,
    disabled = false,
    icon = 'add_photo_alternate',
    title = 'Drop image',
    hint = 'or click, or paste',
    compact = false,
    class: klass,
    style,
    onfiles,
    children,
  }: Props = $props()

  let input: HTMLInputElement
  let over = $state(false)
  let depth = 0

  function ok(f: File) {
    if (!accept || accept === '*') return true
    return accept.split(',').some((a) => {
      a = a.trim()
      if (a.endsWith('/*')) return f.type.startsWith(a.slice(0, -1))
      if (a.startsWith('.')) return f.name.toLowerCase().endsWith(a.toLowerCase())
      return f.type === a
    })
  }
  function emit(list: FileList | File[] | null | undefined) {
    if (!list || disabled) return
    let files = Array.from(list).filter(ok)
    if (!multiple) files = files.slice(0, 1)
    if (files.length) onfiles(files)
  }
  function enter(e: DragEvent) {
    if (disabled || !e.dataTransfer?.types.includes('Files')) return
    e.preventDefault()
    depth++
    over = true
  }
  function leave() {
    depth = Math.max(0, depth - 1)
    if (!depth) over = false
  }
  function drop(e: DragEvent) {
    e.preventDefault()
    depth = 0
    over = false
    emit(e.dataTransfer?.files)
  }

  $effect(() => {
    if (!paste) return
    const onPaste = (e: ClipboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t?.closest('input, textarea, [contenteditable="true"]')) return
      const files = Array.from(e.clipboardData?.files ?? [])
      if (files.length) {
        e.preventDefault()
        emit(files)
      }
    }
    addEventListener('paste', onPaste)
    return () => removeEventListener('paste', onPaste)
  })
</script>

<div
  class={['dz', klass, { over, disabled, compact }]}
  {style}
  role="button"
  tabindex={disabled ? -1 : 0}
  aria-disabled={disabled || undefined}
  aria-label={title}
  onclick={() => !disabled && input.click()}
  onkeydown={(e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      if (!disabled) input.click()
    }
  }}
  ondragenter={enter}
  ondragover={(e) => {
    if (over) e.preventDefault()
  }}
  ondragleave={leave}
  ondrop={drop}
>
  {#if children}
    {@render children(over)}
  {:else}
    <span class="icon big" aria-hidden="true">{over ? 'download' : icon}</span>
    <span class="t">{title}</span>
    {#if hint && !compact}<span class="h">{hint}</span>{/if}
  {/if}
  <input
    bind:this={input}
    type="file"
    {accept}
    {multiple}
    hidden
    onchange={(e) => {
      emit(e.currentTarget.files)
      e.currentTarget.value = ''
    }}
  />
</div>

<style>
  .dz {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    min-height: 140px;
    padding: var(--sp-5);
    border-radius: var(--r-lg);
    background: var(--grad-1);
    border: 1px dashed var(--surface-4);
    color: var(--text-muted);
    text-align: center;
    cursor: pointer;
    transition:
      background-color var(--dur) var(--ease),
      color var(--dur) var(--ease),
      transform var(--dur) var(--ease),
      border-color var(--dur) var(--ease);
  }
  .compact {
    min-height: 0;
    flex-direction: row;
    gap: var(--sp-2);
    padding: var(--sp-3) var(--sp-4);
    border-radius: var(--r-md);
  }
  .dz:hover {
    background-color: var(--surface-2);
    color: var(--text);
  }
  .over {
    border-style: solid;
    border-color: var(--accent);
    background-color: var(--accent-soft);
    color: var(--accent-strong);
    transform: scale(1.01);
  }
  .over .big {
    animation: bob 0.9s var(--ease) infinite alternate;
  }
  .big {
    font-size: 30px;
    margin-bottom: 4px;
  }
  .compact .big {
    font-size: 22px;
    margin: 0;
  }
  .t {
    font-weight: 500;
  }
  .h {
    font-size: var(--fs-sm);
    color: var(--text-faint);
  }
  .disabled {
    opacity: 0.45;
    cursor: default;
  }
  @keyframes bob {
    to {
      transform: translateY(3px);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .over .big {
      animation: none;
    }
  }
</style>
