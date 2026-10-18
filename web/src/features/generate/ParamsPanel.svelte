<script lang="ts">
  import LoraPicker from '$features/models/LoraPicker.svelte'
  import ModelSelect from '$features/models/ModelSelect.svelte'
  import PromptEditor from '$features/prompt/PromptEditor.svelte'
  import PromptLibrary from '$features/prompt/PromptLibrary.svelte'
  import SendTo from '$features/prompt/SendTo.svelte'
  import StructuredPrompt from '$features/prompt/StructuredPrompt.svelte'
  import { session } from '$lib/session.svelte'
  import type { Family, SavedPrompt } from '$lib/types'
  import { AspectPicker, Dropzone, Field, IconButton, NumberField, SeedField, Segmented, Select, Sheet, Slider } from '$lib/ui'
  import { addFile, uploadUrl } from './actions.svelte'
  import AdvancedGroup from './AdvancedGroup.svelte'
  import DetailerGroup from './DetailerGroup.svelte'
  import SecondPassGroup from './SecondPassGroup.svelte'
  import UpscaleGroup from './UpscaleGroup.svelte'
  import VariationField from './VariationField.svelte'
  import EmbeddingPicker from './EmbeddingPicker.svelte'

  const p = $derived(session.params)
  const info = $derived(session.info)
  const fam = $derived(session.family)

  const ratios: [number, number][] = [[1, 1], [5, 4], [4, 3], [3, 2], [16, 9], [2, 1]]

  let lastSeed = $state(Math.floor(Math.random() * 4294967295))
  let library = $state(false)

  const families: { value: Family; label: string }[] = [
    { value: 'illustrious', label: 'Illustrious' },
    { value: 'anima', label: 'Anima' },
  ]

  function loadPrompt(s: SavedPrompt) {
    session.positive[session.family] = s.positive
    session.negative[session.family] = s.negative
    library = false
  }
</script>

{#if p && info}
  <div class="params">
    <Segmented items={families} value={session.family} onchange={(f) => session.setFamily(f)} full />

    {#if p.init}
      <div class="init">
        <div class="thumb" style="background-image: url({uploadUrl(p.init.imageId)})"></div>
        <div class="ibody">
          <div class="irow">
            <span class="ititle">{p.init.maskId ? 'Inpaint' : 'Image to image'}</span>
            <IconButton icon="close" label="Remove input image" size="sm" onclick={() => (p.init = null)} />
          </div>
          <Field label="Denoise" info="0 keeps the input, 1 ignores it.">
            {#snippet children()}<Slider bind:value={p.init!.denoise} min={0} max={1} step={0.01} defaultValue={0.6} />{/snippet}
          </Field>
        </div>
      </div>
    {:else}
      <Dropzone compact paste={false} title="Input image" icon="add_photo_alternate" onfiles={(f) => addFile(f[0])} />
    {/if}

    <ModelSelect kind="checkpoint" family={fam} bind:value={p.model} defaults />

    {#key fam}
      <div class="prompt">
        <div class="phead">
          <span class="lbl">Prompt</span>
          <span class="pact">
            <SendTo from="generate" />
            {#if fam === 'illustrious'}<EmbeddingPicker family={fam} />{/if}
            {#if fam === 'anima'}
              <IconButton
                icon="view_agenda"
                label={session.structured ? 'Single prompt box' : 'Split into quality, subject, artists and prompt'}
                size="sm"
                active={session.structured}
                onclick={() => (session.structured = !session.structured)}
              />
            {/if}
            <IconButton icon="bookmarks" label="Saved prompts" size="sm" onclick={() => (library = true)} />
          </span>
        </div>
        {#if fam === 'anima' && session.structured}
          <StructuredPrompt family={fam} loras={p.loras} bind:segments={() => session.positive[fam] ?? [], (v) => (session.positive[fam] = v)} />
        {:else}
          <PromptEditor
            kind="positive"
            family={fam}
            loras={p.loras}
            placeholder="Describe the image"
            bind:segments={() => session.positive[fam] ?? [], (v) => (session.positive[fam] = v)}
          />
        {/if}
        <PromptEditor
          kind="negative"
          family={fam}
          placeholder="Negative prompt"
          bind:segments={() => session.negative[fam] ?? [], (v) => (session.negative[fam] = v)}
        />
      </div>
    {/key}

    <LoraPicker family={fam} bind:loras={p.loras} />

    <AspectPicker bind:width={p.width} bind:height={p.height} ratios={ratios} step={fam === 'anima' ? 16 : 64} min={fam === 'anima' ? 256 : 512} />

    <Field label="Steps" info="More steps refine details but take longer.">
      {#snippet children()}<Slider bind:value={p.steps} min={1} max={80} step={1} defaultValue={info.defaults.steps} />{/snippet}
    </Field>
    <Field label="CFG" info="How strictly the image follows the prompt.">
      {#snippet children()}<Slider bind:value={p.cfg} min={1} max={20} step={0.5} defaultValue={info.defaults.cfg} />{/snippet}
    </Field>

    <div class="two">
      <Field label="Sampler">
        {#snippet children(id)}<Select {id} items={info.samplers} bind:value={p.sampler} />{/snippet}
      </Field>
      <Field label="Scheduler">
        {#snippet children(id)}<Select {id} items={info.schedulers} bind:value={p.scheduler} />{/snippet}
      </Field>
    </div>

    <Field label="Seed" info="Unlocked picks a random seed for every image. Lock to repeat a result.">
      {#snippet children(id)}
        <SeedField
          {id}
          bind:value={() => (p.seed >= 0 ? p.seed : lastSeed), (v) => ((lastSeed = v), (p.seed = v))}
          bind:locked={() => p.seed >= 0, (l) => (p.seed = l ? lastSeed : -1)}
        />
      {/snippet}
    </Field>
    <VariationField {p} />

    <div class="two">
      <Field label="Batch" info="Images generated together in one run. Uses more VRAM.">
        {#snippet children(id)}<NumberField {id} bind:value={p.batchSize} min={1} max={8} step={1} icon="photo_library" />{/snippet}
      </Field>
      <Field label="Queue" info="How many runs to add to the queue. The seed advances for each.">
        {#snippet children(id)}<NumberField {id} bind:value={session.count} min={1} max={99} step={1} icon="playlist_add" />{/snippet}
      </Field>
    </div>

    <SecondPassGroup {p} {info} />
    <DetailerGroup {p} {info} />
    <UpscaleGroup {p} />
    <AdvancedGroup {p} />
  </div>

  <Sheet bind:open={library} title="Saved prompts" width={520}>
    <PromptLibrary onload={loadPrompt} />
  </Sheet>
{/if}

<style>
  .params {
    display: flex;
    flex-direction: column;
    gap: var(--sp-4);
  }
  .two {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--sp-3);
  }
  .prompt {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
  }
  .phead {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .pact {
    display: flex;
    gap: var(--sp-1);
  }
  .lbl {
    font-size: var(--fs-sm);
    color: var(--text-muted);
    font-weight: 500;
  }
  .init {
    display: flex;
    gap: var(--sp-3);
    padding: var(--sp-3);
    border: 1px solid var(--hairline);
    border-radius: var(--r-lg);
    background: var(--surface-1);
  }
  .thumb {
    flex: none;
    width: 64px;
    border-radius: var(--r-md);
    background-size: cover;
    background-position: center;
    background-color: var(--surface-3);
  }
  .ibody {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
  }
  .irow {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .ititle {
    font-weight: 500;
  }
</style>
