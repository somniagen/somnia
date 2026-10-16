<script lang="ts">
  import OpenInEditor from '$features/editors/OpenInEditor.svelte'
  import type { GalleryItem } from '$lib/types'
  import { IconButton, mobile } from '$lib/ui'
  import { download, img2img, openInpaint, removeImage, reuse, upscaleAgain } from './actions.svelte'

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
</style>
