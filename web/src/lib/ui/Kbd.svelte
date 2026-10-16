<script lang="ts">
  import type { Snippet } from 'svelte'
  let { children, class: klass }: { children?: Snippet; class?: string } = $props()
</script>

<kbd class={klass}>{@render children?.()}</kbd>

<style>
  kbd {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 20px;
    height: 20px;
    padding: 0 5px;
    border-radius: 5px;
    background: var(--grad-3);
    box-shadow: inset 0 -1px 0 var(--surface-4);
    color: var(--text-muted);
    font-family: var(--font);
    font-size: var(--fs-xs);
    font-weight: 500;
    line-height: 1;
    vertical-align: middle;
  }
</style>
