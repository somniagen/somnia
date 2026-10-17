<script lang="ts">
  import TextInput from '$features/shell/TextInput.svelte'
  import { Button, Modal } from '$lib/ui'
  import { library } from './library.svelte'

  let value = $state('')
  let open = $state(false)
  let box = $state<HTMLDivElement>()
  const ask = $derived(library.ask)
  const taken = $derived(!!ask && value.trim() !== ask.value && library.albums.some((a) => a.name === value.trim()))

  $effect(() => {
    if (!ask) return
    value = ask.value
    open = true
    requestAnimationFrame(() => box?.querySelector('input')?.select())
  })

  function finish(v: string | null) {
    const a = library.ask
    library.ask = null
    open = false
    a?.resolve(v)
  }
  const ok = () => value.trim() && finish(value.trim())
</script>

<Modal bind:open title={ask?.title ?? ''} width={380} onclose={() => finish(null)}>
  <div class="body" bind:this={box}>
    <TextInput bind:value placeholder="Album name" aria-label="Album name" maxlength={80} onenter={ok} />
    {#if taken}<span class="hint">Merges into the existing album</span>{/if}
  </div>
  {#snippet footer()}
    <Button onclick={() => finish(null)}>Cancel</Button>
    <Button variant="primary" icon="photo_album" disabled={!value.trim()} onclick={ok}>{ask?.action ?? 'Create'}</Button>
  {/snippet}
</Modal>

<style>
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
  }
  .hint {
    font-size: var(--fs-xs);
    color: var(--text-muted);
  }
</style>
