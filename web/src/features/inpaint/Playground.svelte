<script lang="ts">
  import { api } from '$lib/api'
  import type { UploadResult } from '$lib/types'
  import { Button, Dropzone, toast } from '$lib/ui'
  import Inpainter from './Inpainter.svelte'

  let image = $state<UploadResult | null>(null)
  let open = $state(false)
  let busy = $state(false)
  let result = $state<Record<string, unknown> | null>(null)

  async function onfiles(files: File[]) {
    const f = files[0]
    if (!f) return
    busy = true
    try {
      image = await api.upload(f, f.name)
      result = null
      open = true
    } catch (e) {
      toast.error('Upload failed', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      busy = false
    }
  }
</script>

<div class="pg">
  <Dropzone {onfiles} accept="image/*" paste title={busy ? 'Uploading' : 'Drop an image'} hint="or click, or paste" />
  {#if image}
    <div class="row">
      <img src={image.url} alt="" />
      <div class="info">
        <span>{image.width} x {image.height}</span>
        <Button icon="draw" onclick={() => (open = true)}>Open inpainter</Button>
      </div>
    </div>
  {/if}
  {#if result}
    <div class="row">
      <img src="/files/uploads/{result.maskId}.png" alt="mask" />
      <pre>{JSON.stringify(result, null, 2)}</pre>
    </div>
  {/if}
</div>

{#if open && image}
  <Inpainter
    imageId={image.id}
    imageUrl={image.url}
    width={image.width}
    height={image.height}
    onapply={(r) => {
      console.log('inpaint apply', r)
      result = r
      open = false
    }}
    oncancel={() => (open = false)}
  />
{/if}


<style>
  .pg {
    display: flex;
    flex-direction: column;
    gap: var(--sp-4);
    max-width: 720px;
    margin: 0 auto;
    padding: var(--sp-5) var(--sp-4);
  }
  .row {
    display: flex;
    gap: var(--sp-4);
    align-items: flex-start;
  }
  img {
    width: 200px;
    border-radius: var(--r-md);
    border: 1px solid var(--hairline);
  }
  .info {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    color: var(--text-muted);
  }
  pre {
    margin: 0;
    font-family: var(--font-mono);
    font-size: var(--fs-sm);
    color: var(--text-muted);
  }
</style>
