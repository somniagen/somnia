<script lang="ts">
  import type { HTMLInputAttributes } from 'svelte/elements'

  interface Props extends Omit<HTMLInputAttributes, 'value' | 'onchange'> {
    value?: string
    mono?: boolean
    multiline?: boolean
    rows?: number
    onchange?: (v: string) => void
    onenter?: () => void
  }
  let { value = $bindable(''), mono = false, multiline = false, rows = 2, onchange, onenter, class: klass, ...rest }: Props = $props()

  function key(e: KeyboardEvent) {
    if (e.key === 'Enter' && (!multiline || e.ctrlKey || e.metaKey)) {
      if (!multiline) (e.currentTarget as HTMLElement).blur()
      onenter?.()
    }
  }
</script>

{#if multiline}
  <textarea
    class={['ti', klass, { mono }]}
    {rows}
    bind:value
    onchange={() => onchange?.(value)}
    onkeydown={key}
    placeholder={rest.placeholder}
    disabled={rest.disabled}
  ></textarea>
{:else}
  <input class={['ti', klass, { mono }]} bind:value onchange={() => onchange?.(value)} onkeydown={key} {...rest} />
{/if}

<style>
  .ti {
    width: 100%;
    min-height: var(--control-h);
    padding: 0 var(--sp-3);
    border: 0;
    border-radius: var(--r-md);
    background: var(--grad-3);
    color: var(--text);
    font: inherit;
    font-size: var(--fs-sm);
    outline: none;
    transition: background-color var(--dur-fast) var(--ease);
  }
  textarea.ti {
    padding: var(--sp-2) var(--sp-3);
    resize: vertical;
    line-height: 1.4;
  }
  .ti:hover {
    background: var(--grad-4);
  }
  .ti:focus {
    background: var(--grad-4);
    box-shadow: inset 0 0 0 1px var(--focus-line);
  }
  .ti:disabled {
    opacity: 0.5;
  }
  .ti::placeholder {
    color: var(--text-faint);
  }
  .mono {
    font-family: var(--font-mono);
  }
  @media (pointer: coarse) {
    .ti {
      min-height: var(--touch);
    }
  }
</style>
