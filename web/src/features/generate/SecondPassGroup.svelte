<script lang="ts">
  import ModelSelect from '$features/models/ModelSelect.svelte'
  import type { FamilyInfo, GenParams } from '$lib/types'
  import { Field, NumberField, Segmented, Select, Slider } from '$lib/ui'
  import Group from './Group.svelte'

  let { p, info }: { p: GenParams; info: FamilyInfo } = $props()
  const sp = $derived(p.secondPass)

  let lastModel = ''
  const mode = $derived(sp.upscaler === 'latent' ? 'latent' : 'model')
  function setMode(m: string) {
    if (m === 'latent') {
      if (sp.upscaler !== 'latent') lastModel = sp.upscaler
      sp.upscaler = 'latent'
    } else sp.upscaler = lastModel || info.defaults.secondPass.upscaler
  }
  const same = '__same'
</script>

<Group id="second" title="Second pass" icon="layers" toggleable bind:enabled={p.secondPass.enabled}>
  <Field label="Upscaler" info="Latent resizes in latent space. A model upscales pixels, then resamples.">
    {#snippet children()}
      <Segmented items={[{ value: 'model', label: 'Model' }, { value: 'latent', label: 'Latent' }]} value={mode} onchange={setMode} full />
    {/snippet}
  </Field>
  {#if mode === 'model'}
    <ModelSelect kind="upscaler" bind:value={sp.upscaler} />
  {/if}
  <Field label="Scale" info="Size multiplier of the second pass.">
    {#snippet children()}
      <Slider bind:value={sp.scale} min={1} max={4} step={0.05} defaultValue={1.5} />
    {/snippet}
  </Field>
  <Field label="Steps">
    {#snippet children()}
      <Slider bind:value={sp.steps} min={1} max={60} step={1} defaultValue={15} />
    {/snippet}
  </Field>
  <Field label="Denoise" info="How much the second pass may change the image.">
    {#snippet children()}
      <Slider bind:value={sp.denoise} min={0} max={1} step={0.01} defaultValue={0.35} />
    {/snippet}
  </Field>
  <div class="two">
    <Field label="Sampler" info="Same keeps the main sampler.">
      {#snippet children(id)}
        <Select
          {id}
          items={[{ value: same, label: 'Same' }, ...info.samplers]}
          value={sp.sampler ?? same}
          onchange={(v) => (sp.sampler = v === same ? null : v)}
        />
      {/snippet}
    </Field>
    <Field label="Scheduler">
      {#snippet children(id)}
        <Select
          {id}
          items={[{ value: same, label: 'Same' }, ...info.schedulers]}
          value={sp.scheduler ?? same}
          onchange={(v) => (sp.scheduler = v === same ? null : v)}
        />
      {/snippet}
    </Field>
  </div>
  <div class="two">
    <Field label="CFG" info="Defaults to the main CFG.">
      {#snippet children(id)}
        <NumberField {id} value={sp.cfg ?? p.cfg} min={1} max={30} step={0.5} onchange={(v) => (sp.cfg = v === p.cfg ? null : v)} />
      {/snippet}
    </Field>
    <Field label="Model" info="Optional checkpoint for the second pass.">
      {#snippet children()}
        <ModelSelect kind="checkpoint" family={p.family} allowNone bind:value={() => sp.model ?? '', (v) => (sp.model = v || null)} />
      {/snippet}
    </Field>
  </div>
</Group>

<style>
  .two {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--sp-3);
  }
</style>
