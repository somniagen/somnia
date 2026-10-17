<script lang="ts">
  import { IconButton, Menu } from '$lib/ui'
  import { sendItems, type SentPrompt, type Tab } from './send.svelte'

  let {
    from = null,
    get,
    only,
    after,
    size = 'sm',
    label = 'Send prompt to',
  }: { from?: Tab | null; get?: () => SentPrompt; only?: Tab[]; after?: () => void; size?: 'sm' | 'md'; label?: string } = $props()

  const items = $derived(sendItems(from, get, only, after))
</script>

<Menu {items} placement="bottom-end" {label}>
  {#snippet trigger({ toggle, open })}
    <IconButton icon="send" {label} {size} active={open} onclick={toggle} />
  {/snippet}
</Menu>
