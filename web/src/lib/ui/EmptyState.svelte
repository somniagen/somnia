<script lang="ts">
  import type { Snippet } from 'svelte'

  interface Props {
    icon?: string
    title: string
    description?: string
    compact?: boolean
    class?: string
    style?: string
    children?: Snippet
  }
  let { icon = 'image', title, description, compact = false, class: klass, style, children }: Props = $props()
</script>

<div class={['empty', klass, { compact }]} {style}>
  <span class="badge" aria-hidden="true"><span class="icon">{icon}</span></span>
  <div class="title">{title}</div>
  {#if description}<div class="desc">{description}</div>{/if}
  {#if children}<div class="actions">{@render children()}</div>{/if}
</div>

<style>
  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--sp-2);
    padding: var(--sp-6) var(--sp-4);
    text-align: center;
  }
  .compact {
    padding: var(--sp-4);
  }
  .badge {
    display: grid;
    place-items: center;
    width: 56px;
    height: 56px;
    margin-bottom: var(--sp-1);
    border-radius: var(--r-lg);
    background: var(--grad-2);
    color: var(--text-faint);
  }
  .badge .icon {
    font-size: 28px;
  }
  .compact .badge {
    width: 40px;
    height: 40px;
  }
  .compact .badge .icon {
    font-size: 22px;
  }
  .title {
    font-weight: 500;
    color: var(--text);
  }
  .desc {
    max-width: 320px;
    font-size: var(--fs-sm);
    color: var(--text-muted);
  }
  .actions {
    display: flex;
    gap: var(--sp-2);
    margin-top: var(--sp-2);
  }
</style>
