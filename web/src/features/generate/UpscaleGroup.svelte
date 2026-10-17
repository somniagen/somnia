<script lang="ts">
  import ModelSelect from '$features/models/ModelSelect.svelte'
  import type { GenParams, TiledRefine } from '$lib/types'
  import { Field, Slider, Toggle } from '$lib/ui'
  import Group from './Group.svelte'

  let { p }: { p: GenParams } = $props()

  const t = $derived(p.upscale.tiled)
  function set(patch: Partial<TiledRefine>) {
    p.upscale.tiled = { enabled: false, denoise: 0.3, steps: 20, tileSize: 1024, padding: 64, ...(p.upscale.tiled ?? {}), ...patch }
  }
</script>

<Group id="upscale" title="Upscale" icon="zoom_out_map" toggleable bind:enabled={p.upscale.enabled}>
  <ModelSelect kind="upscaler" bind:value={p.upscale.upscaler} />
  <Field label="Scale" info="Final size multiplier, applied after everything else.">
    {#snippet children()}<Slider bind:value={p.upscale.scale} min={1} max={4} step={0.25} defaultValue={2} />{/snippet}
  </Field>
  <Field label="Tiled refine" info="Resamples the upscaled image tile by tile at low denoise to add real detail. Slower.">
    {#snippet trailing()}
      <Toggle checked={!!t?.enabled} onchange={(on) => set({ enabled: on })} size="sm" aria-label="Tiled refine" />
    {/snippet}
    {#snippet children()}
      {#if t?.enabled}
        <div class="tiled">
          <Field label="Denoise">
            {#snippet children()}
              <Slider bind:value={() => t.denoise, (v) => set({ denoise: v })} min={0} max={1} step={0.01} defaultValue={0.3} />
            {/snippet}
          </Field>
          <Field label="Steps">
            {#snippet children()}
              <Slider bind:value={() => t.steps, (v) => set({ steps: v })} min={1} max={60} step={1} defaultValue={20} />
            {/snippet}
          </Field>
          <Field label="Tile size" info="Tiles overlap and are blended, so seams stay invisible.">
            {#snippet children()}
              <Slider bind:value={() => t.tileSize, (v) => set({ tileSize: v })} min={512} max={2048} step={64} defaultValue={1024} />
            {/snippet}
          </Field>
        </div>
      {/if}
    {/snippet}
  </Field>
</Group>

<style>
  .tiled {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
  }
</style>
