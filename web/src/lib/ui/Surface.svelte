<script lang="ts">
  import type { Snippet } from 'svelte'
  import type { HTMLAttributes } from 'svelte/elements'

  interface Props extends HTMLAttributes<HTMLElement> {
    level?: 0 | 1 | 2 | 3 | 4
    padding?: string
    radius?: 'sm' | 'md' | 'lg'
    as?: string
    interactive?: boolean
    bordered?: boolean
    children?: Snippet
  }
  let {
    level = 1,
    padding = 'var(--sp-4)',
    radius = 'lg',
    as = 'div',
    interactive = false,
    bordered = false,
    class: klass,
    style,
    children,
    ...rest
  }: Props = $props()
</script>

<svelte:element
  this={as}
  class={['surface', `l${level}`, klass, { interactive, bordered }]}
  style="--pad: {padding}; --rad: var(--r-{radius}); {style ?? ''}"
  {...rest}
>
  {@render children?.()}
</svelte:element>

<style>
  .surface {
    padding: var(--pad);
    border: 1px solid var(--hairline);
    border-radius: var(--rad);
    background: var(--grad-1);
    box-shadow: var(--sheen);
    color: var(--text);
  }
  .l0 {
    background: var(--bg);
  }
  .l2 {
    background: var(--grad-2);
  }
  .l3 {
    background: var(--grad-3);
    box-shadow: var(--sheen), var(--shadow-1);
  }
  .l4 {
    background: var(--grad-4);
    box-shadow: var(--sheen), var(--shadow-2);
  }
  :global(.surface) .surface {
    border-color: transparent;
  }
  .bordered,
  :global(.surface) .surface.bordered {
    border-color: var(--hairline);
  }
  .interactive {
    cursor: pointer;
    transition:
      background var(--dur-fast) var(--ease),
      transform var(--dur-fast) var(--ease);
  }
  .interactive:hover {
    background: var(--grad-2);
  }
  .l2.interactive:hover {
    background: var(--grad-3);
  }
  .l3.interactive:hover {
    background: var(--grad-4);
  }
  .interactive:active {
    transform: scale(0.99);
  }
</style>
