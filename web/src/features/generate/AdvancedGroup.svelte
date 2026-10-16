<script lang="ts">
  import ModelSelect from '$features/models/ModelSelect.svelte'
  import { session } from '$lib/session.svelte'
  import type { GenParams } from '$lib/types'
  import { Button, Field, NumberField, Slider, Toggle, toast } from '$lib/ui'
  import Group from './Group.svelte'

  let { p }: { p: GenParams } = $props()

  function reset() {
    const before = $state.snapshot(p) as GenParams
    session.resetDefaults()
    toast.info('Reset to defaults', {
      action: {
        label: 'Undo',
        run: () => {
          if (session.params) Object.assign(session.params, before)
        },
      },
    })
  }
</script>

<Group id="advanced" title="Advanced" icon="tune">
  <Field label="Clip skip" info="Skips the last text encoder layers. 2 is typical for Illustrious.">
    {#snippet children(id)}<NumberField {id} bind:value={p.clipSkip} min={1} max={12} step={1} />{/snippet}
  </Field>
  <Field label="PAG" info="Perturbed attention guidance. Sharper structure, a bit slower.">
    {#snippet trailing()}<Toggle bind:checked={p.pag.enabled} size="sm" aria-label="PAG" />{/snippet}
    {#snippet children()}
      <Slider bind:value={p.pag.scale} min={0} max={10} step={0.1} disabled={!p.pag.enabled} defaultValue={3} />
    {/snippet}
  </Field>
  <Field label="CFG rescale" info="Reduces over-saturation at high CFG. 0 is off.">
    {#snippet children()}<Slider bind:value={p.cfgRescale} min={0} max={1} step={0.05} defaultValue={0} />{/snippet}
  </Field>
  <Field label="VAE" info="Empty uses the VAE built into the checkpoint.">
    {#snippet children()}
      <ModelSelect kind="vae" family={p.family} allowNone bind:value={() => p.vae ?? '', (v) => (p.vae = v || null)} />
    {/snippet}
  </Field>
  {#if p.family === 'anima'}
    <Field label="Text encoder" info="Language model used to read the prompt.">
      {#snippet children()}
        <ModelSelect kind="text_encoder" family={p.family} bind:value={() => p.textEncoder ?? '', (v) => (p.textEncoder = v || null)} />
      {/snippet}
    </Field>
  {/if}
  <Button variant="ghost" icon="restart_alt" onclick={reset} class="reset" full>Reset to defaults</Button>
</Group>

<style>
  :global(.reset) {
    color: var(--danger) !important;
  }
</style>
