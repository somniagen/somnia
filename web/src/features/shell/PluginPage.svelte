<script lang="ts">
  import { EmptyState } from '$lib/ui'
  import { plugins } from '$lib/plugins.svelte'

  let { plugin, page }: { plugin: string; page: string } = $props()

  let el = $state<HTMLDivElement>()
  const p = $derived(plugins.page(plugin, page))

  $effect(() => {
    if (!el || !p) return
    const target = el
    let cleanup: (() => void) | void
    try {
      cleanup = p.mount(target)
    } catch (e) {
      console.error(`[plugin ${plugin}] page failed`, e)
    }
    return () => {
      try {
        cleanup?.()
      } catch {}
      target.replaceChildren()
    }
  })
</script>

{#if p}
  <div class="pp" bind:this={el}></div>
{:else}
  <EmptyState icon="extension_off" title="Plugin page not available" description={plugins.list.length ? undefined : 'Loading plugins'} />
{/if}

<style>
  .pp {
    height: 100%;
    min-height: 0;
    overflow: auto;
  }
</style>
