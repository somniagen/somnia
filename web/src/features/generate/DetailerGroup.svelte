<script lang="ts">
  import ModelSelect from '$features/models/ModelSelect.svelte'
  import TextInput from '$features/shell/TextInput.svelte'
  import type { DetailerPass, FamilyInfo, GenParams } from '$lib/types'
  import { Button, Field, IconButton, NumberField, Slider, Toggle } from '$lib/ui'
  import Group from './Group.svelte'

  let { p, info }: { p: GenParams; info: FamilyInfo } = $props()

  const blank = (): DetailerPass =>
    structuredClone(
      $state.snapshot(info.defaults.detailers[0]) ?? {
        enabled: true,
        detector: '',
        prompt: '',
        negative: '',
        confidence: 0.3,
        dilate: 4,
        blur: 6,
        denoise: 0.4,
        steps: 20,
        padding: 48,
      },
    )

  function add() {
    p.detailers.push({ ...blank(), enabled: true })
  }
  const active = $derived(p.detailers.filter((d) => d.enabled).length)
</script>

<Group id="detail" title={active ? `Detailers (${active})` : 'Detailers'} icon="face_retouching_natural">
  {#each p.detailers as d, i (i)}
    <div class="pass">
      <div class="top">
        <Toggle bind:checked={d.enabled} size="sm" aria-label="Enable detailer" />
        <div class="det">
          <ModelSelect kind="detector" bind:value={d.detector} />
        </div>
        <IconButton icon="close" label="Remove" size="sm" onclick={() => p.detailers.splice(i, 1)} />
      </div>
      {#if d.enabled}
        <Field label="Denoise" info="How strongly the detected area is repainted.">
          {#snippet children()}<Slider bind:value={d.denoise} min={0} max={1} step={0.01} defaultValue={0.4} />{/snippet}
        </Field>
        <Field label="Confidence" info="Minimum detection score to keep a region.">
          {#snippet children()}<Slider bind:value={d.confidence} min={0.05} max={0.95} step={0.01} defaultValue={0.3} />{/snippet}
        </Field>
        <Field label="Steps">
          {#snippet children()}<Slider bind:value={d.steps} min={1} max={60} step={1} defaultValue={20} />{/snippet}
        </Field>
        <div class="three">
          <Field label="Dilate" info="Grows the detected mask, in pixels.">
            {#snippet children(id)}<NumberField {id} bind:value={d.dilate} min={0} max={64} step={1} suffix="px" steppers={false} />{/snippet}
          </Field>
          <Field label="Blur" info="Softens the mask edge, in pixels.">
            {#snippet children(id)}<NumberField {id} bind:value={d.blur} min={0} max={64} step={1} suffix="px" steppers={false} />{/snippet}
          </Field>
          <Field label="Padding" info="Extra context around the region, in pixels.">
            {#snippet children(id)}<NumberField {id} bind:value={d.padding} min={0} max={256} step={4} suffix="px" steppers={false} />{/snippet}
          </Field>
        </div>
        <Field
          label="Prompt"
          info={d.appendPrompt ? 'Added after the main prompt for this region.' : 'Replaces the main prompt for this region. Empty uses the main prompt.'}
        >
          {#snippet children(id)}
            <TextInput {id} bind:value={d.prompt} placeholder={d.appendPrompt ? 'Extra tags for this region' : 'Same as main'} />
          {/snippet}
        </Field>
        <Toggle bind:checked={() => !!d.appendPrompt, (v) => (d.appendPrompt = v)} label="Add to main prompt" size="sm" />
      {/if}
    </div>
  {/each}
  <Button icon="add" onclick={add} full>Add detailer</Button>
</Group>

<style>
  .pass {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    padding: var(--sp-3);
    border: 1px solid var(--hairline);
    border-radius: var(--r-md);
    background: var(--grad-2);
  }
  .top {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
  }
  .det {
    flex: 1;
    min-width: 0;
  }
  .three {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--sp-2);
    align-items: end;
  }
</style>
