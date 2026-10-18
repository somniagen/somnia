<script lang="ts">
  import { Tabs } from '$lib/ui'
  import Civitai from './Civitai.svelte'
  import Downloads from './Downloads.svelte'
  import HuggingFace from './HuggingFace.svelte'
  import Library from './Library.svelte'
  import { models } from './store.svelte'

  let tab = $state('library')
  $effect(() => models.start())
</script>

<div class="mm">
  <Tabs
    items={[
      { value: 'library', label: 'Library', icon: 'folder' },
      { value: 'civitai', label: 'Civitai', icon: 'cloud' },
      { value: 'hf', label: 'Hugging Face', icon: 'hub' },
    ]}
    bind:value={tab}
  />
  <Downloads />
  {#if tab === 'library'}<Library />{:else if tab === 'hf'}<HuggingFace />{:else}<Civitai />{/if}
</div>

<style>
  .mm {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    max-width: 1280px;
    margin: 0 auto;
    padding: var(--sp-4);
  }
</style>
