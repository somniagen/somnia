<script lang="ts">
  import type { Snippet } from 'svelte'
  import type { HTMLAttributes } from 'svelte/elements'
  import Surface from './Surface.svelte'

  interface Props extends HTMLAttributes<HTMLElement> {
    level?: 0 | 1 | 2 | 3 | 4
    title?: string
    icon?: string
    padding?: string
    actions?: Snippet
    children?: Snippet
  }
  let { level = 1, title, icon, padding, actions, children, ...rest }: Props = $props()
</script>

<Surface {level} {padding} as="section" {...rest}>
  {#if title || actions}
    <header>
      {#if icon}<span class="icon" aria-hidden="true">{icon}</span>{/if}
      {#if title}<h3>{title}</h3>{/if}
      {#if actions}<div class="actions">{@render actions()}</div>{/if}
    </header>
  {/if}
  {@render children?.()}
</Surface>

<style>
  header {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: 28px;
    margin-bottom: var(--sp-3);
  }
  header .icon {
    color: var(--text-muted);
    font-size: 20px;
  }
  h3 {
    margin: 0;
    font-size: var(--fs-md);
    font-weight: 600;
  }
  .actions {
    display: flex;
    gap: var(--sp-1);
    margin-left: auto;
  }
</style>
