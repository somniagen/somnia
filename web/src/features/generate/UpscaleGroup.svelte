<script lang="ts">
  import ModelSelect from '$features/models/ModelSelect.svelte'
  import type { GenParams } from '$lib/types'
  import { Field, Slider } from '$lib/ui'
  import Group from './Group.svelte'

  let { p }: { p: GenParams } = $props()
</script>

<Group id="upscale" title="Upscale" icon="zoom_out_map" toggleable bind:enabled={p.upscale.enabled}>
  <ModelSelect kind="upscaler" bind:value={p.upscale.upscaler} />
  <Field label="Scale" info="Final size multiplier, applied after everything else.">
    {#snippet children()}<Slider bind:value={p.upscale.scale} min={1} max={4} step={0.25} defaultValue={2} />{/snippet}
  </Field>
</Group>
