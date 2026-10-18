<script lang="ts">
  import type { Component } from 'svelte'
  import GalleryView from '$features/gallery/GalleryView.svelte'
  import GenerateView from '$features/generate/GenerateView.svelte'
  import GridView from '$features/grid/GridView.svelte'
  import InpaintView from '$features/inpaint/InpaintView.svelte'
  import ModelManager from '$features/models/ModelManager.svelte'
  import SettingsView from '$features/settings/SettingsView.svelte'
  import PluginPage from '$features/shell/PluginPage.svelte'
  import Shell from '$features/shell/Shell.svelte'
  import { boot } from '$features/shell/boot.svelte'
  import { EmptyState } from '$lib/ui'

  const dev = import.meta.glob<{ default: Component }>('./features/*/Playground.svelte')

  let route = $state(location.hash)
  $effect(() => {
    const on = () => (route = location.hash)
    addEventListener('hashchange', on)
    return () => removeEventListener('hashchange', on)
  })
  boot.start()

  const devPath = $derived.by(() => {
    const m = route.match(/^#\/dev\/(\w+)/)
    if (!m) return null
    const key = { prompt: './features/prompt/Playground.svelte', inpaint: './features/inpaint/Playground.svelte' }[m[1]]
    return key ?? null
  })
  const pluginRoute = $derived(route.match(/^#\/p\/([\w-]+)\/([\w-]+)/))
  const chrome = $derived(!(route === '#/ui' || route.startsWith('#/dev/')))
</script>

<Shell {route} {chrome}>
  {#if route === '#/ui'}
    {#await import('./lib/ui/Demo.svelte') then m}
      <m.default />
    {/await}
  {:else if route.startsWith('#/dev/')}
    {#if devPath && dev[devPath]}
      {#await dev[devPath]() then m}
        <m.default />
      {/await}
    {:else}
      <EmptyState icon="construction" title="No playground here" />
    {/if}
  {:else if route === '#/inpaint'}
    <InpaintView />
  {:else if route === '#/grid'}
    <GridView />
  {:else if route === '#/gallery'}
    <GalleryView />
  {:else if route === '#/models'}
    <ModelManager />
  {:else if route.startsWith('#/settings')}
    <SettingsView />
  {:else if pluginRoute}
    {#key route}<PluginPage plugin={pluginRoute[1]} page={pluginRoute[2]} />{/key}
  {:else}
    <GenerateView />
  {/if}
</Shell>
