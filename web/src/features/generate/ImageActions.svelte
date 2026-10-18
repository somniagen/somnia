<script lang="ts">
  import OpenInEditor from '$features/editors/OpenInEditor.svelte'
  import type { GalleryItem } from '$lib/types'
  import { IconButton, mobile, toast } from '$lib/ui'
  import { plugins } from '$lib/plugins.svelte'
  import { download, img2img, openInpaint, removeBackground, removeImage, reuse, upscaleAgain, variations } from './actions.svelte'

  let {
    item,
    onremoved,
    onnavigate,
    editorLabel,
    class: klass,
  }: { item: GalleryItem; onremoved?: () => void; onnavigate?: () => void; editorLabel?: string; class?: string } = $props()

  let armed = $state(false)
  let timer: ReturnType<typeof setTimeout> | undefined

  $effect(() => {
    void item.id
    armed = false
  })

  async function del() {
    if (!armed) {
      armed = true
      clearTimeout(timer)
      timer = setTimeout(() => (armed = false), 3000)
      return
    }
    armed = false
    if (await removeImage(item)) onremoved?.()
  }

  let cutting = $state(false)
  async function cutout() {
    if (cutting) return
    cutting = true
    const out = await removeBackground(item)
    cutting = false
    if (out) toast.success('Background removed', { description: 'Saved in the same stack' })
  }

  const nav = (fn: (i: GalleryItem) => unknown) => async () => {
    await fn(item)
    onnavigate?.()
  }
</script>

<div class={['acts', klass]}>
  <OpenInEditor url={item.url} galleryId={item.id} compact={mobile.current} label={editorLabel} ghost={!!editorLabel} class="oie-gap" />
  <IconButton icon="history" label="Reuse params" onclick={nav(reuse)} disabled={!item.params} />
  <IconButton icon="brush" label="Inpaint" onclick={nav(openInpaint)} />
  <IconButton icon="image" label="Use as input" onclick={nav(img2img)} />
  <IconButton icon="zoom_in" label="Upscale again" onclick={nav(upscaleAgain)} />
  <IconButton icon="difference" label="Variations" onclick={() => variations(item)} disabled={!item.params} />
  <IconButton
    icon={cutting ? 'progress_activity' : 'background_replace'}
    label={cutting ? 'Removing background' : 'Remove background'}
    class={cutting ? 'spin' : undefined}
    disabled={cutting}
    onclick={cutout}
  />
  {#each plugins.actions as a (a.plugin + a.id)}
    <IconButton
      icon={a.icon || 'extension'}
      label={a.label}
      onclick={async () => {
        try {
          await a.run(item)
        } catch (e) {
          toast.error(a.label, { description: e instanceof Error ? e.message : String(e) })
        }
      }}
    />
  {/each}
  <IconButton icon="download" label="Download" onclick={() => download(item)} />
  <IconButton
    icon={armed ? 'delete_forever' : 'delete'}
    label={armed ? 'Click again to delete' : 'Delete'}
    variant={armed ? 'danger' : 'ghost'}
    class="del"
    onclick={del}
  />
</div>

<style>
  .acts {
    display: flex;
    align-items: center;
    gap: 2px;
  }
  .acts :global(.oie-gap) {
    margin-right: var(--sp-2);
  }
  .acts :global(.del:not(.danger)) {
    color: var(--danger);
  }
  .acts :global(.spin .icon) {
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
