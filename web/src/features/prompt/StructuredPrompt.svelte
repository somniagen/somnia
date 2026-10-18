<script lang="ts">
  import { removedTags, session } from '$lib/session.svelte'
  import type { Family, LoraRef, PromptSection, PromptSegment } from '$lib/types'
  import { toast } from '$lib/ui'
  import PromptEditor from './PromptEditor.svelte'
  import { SECTIONS, sectionize } from './sections'

  let {
    segments = $bindable([]),
    family,
    loras = [],
  }: { segments: PromptSegment[]; family: Family; loras?: LoraRef[] } = $props()

  const segs = $derived(segments ?? [])
  const removed = $derived(removedTags(segs))

  // anything that arrives without a section (library, reuse, defaults, older sessions) gets sorted in
  $effect(() => {
    if (segs.some((s) => !s.section && s.text.trim())) segments = sectionize(segs)
  })

  const of = (k: PromptSection) => segs.filter((s) => (s.section ?? 'prompt') === k)

  function setSection(k: PromptSection, v: PromptSegment[]) {
    segments = SECTIONS.flatMap((x) => (x.key === k ? v : of(x.key)).map((s) => ({ ...s, section: x.key })))
  }

  function reset() {
    const prev = $state.snapshot(segs) as PromptSegment[]
    segments = sectionize(session.defaultSegments(family, 'positive'))
    toast('Default prompt', { action: { label: 'Undo', run: () => (segments = prev) } })
  }
</script>

<div class="sp">
  {#each SECTIONS as x (x.key)}
    <div class="row" class:main={x.key === 'prompt'}>
      <span class="lbl">{x.label}</span>
      <PromptEditor
        bind:segments={() => of(x.key), (v) => setSection(x.key, v)}
        kind="positive"
        {family}
        loras={x.key === 'prompt' ? loras : []}
        placeholder={of(x.key).some((s) => s.text.trim()) ? '' : x.placeholder}
        foot={x.key === 'prompt'}
        rows={x.key === 'prompt' ? 3 : 1}
        {removed}
        onreset={reset}
      />
    </div>
  {/each}
</div>

<style>
  .sp {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .row {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  /* an empty line after a section's boilerplate only shows once the section is focused */
  .row:not(.main) :global(.pe:not(:focus-within) .lk ~ .ft.empty) {
    height: 0;
    overflow: hidden;
  }
  .lbl {
    padding-left: 2px;
    color: var(--text-faint);
    font-size: var(--fs-xs);
  }
</style>
