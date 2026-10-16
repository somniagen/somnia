<script lang="ts">
  import { Card, Segmented, Select, Spinner } from '$lib/ui'
  import { segmentsToText, session } from '$lib/session.svelte'
  import type { Family } from '$lib/types'
  import PromptEditor from './PromptEditor.svelte'
  import PromptLibrary from './PromptLibrary.svelte'
  import { applyPrompt } from './library.svelte'
  import { loadLoras, loraModels } from './tags.svelte'

  let lora = $state('')
  loadLoras()
  const loraItems = $derived(loraModels.list.filter((m) => m.civitai?.trainedWords.length).map((m) => ({ value: m.id, label: m.name })))
  $effect(() => {
    if (lora) session.addLora(lora)
  })
</script>

<div class="pg">
  {#if !session.presets}
    <Spinner />
  {:else}
    <div class="col">
      <div class="bar">
        <Segmented items={['illustrious', 'anima']} bind:value={() => session.family, (v: Family) => session.setFamily(v)} size="sm" />
        <Select items={loraItems} bind:value={lora} placeholder="Add lora" />
      </div>
      <PromptEditor
        bind:segments={() => session.positive[session.family] ?? [], (v) => (session.positive[session.family] = v)}
        kind="positive"
        family={session.family}
        loras={session.params?.loras ?? []}
        placeholder="Prompt"
      />
      <PromptEditor
        bind:segments={() => session.negative[session.family] ?? [], (v) => (session.negative[session.family] = v)}
        kind="negative"
        family={session.family}
        placeholder="Negative"
      />
      <pre>{segmentsToText(session.positive[session.family] ?? [])}
---
{segmentsToText(session.negative[session.family] ?? [])}
---
{JSON.stringify(session.positive[session.family])}</pre>
    </div>
    <Card title="Library" icon="bookmarks" class="libcard">
      <PromptLibrary onload={applyPrompt} />
    </Card>
  {/if}
</div>

<style>
  .pg {
    display: flex;
    flex-wrap: wrap;
    gap: var(--sp-4);
    padding: var(--sp-4);
    max-width: 1100px;
  }
  .col {
    flex: 1 1 420px;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
  }
  .bar {
    display: flex;
    gap: var(--sp-2);
  }
  pre {
    white-space: pre-wrap;
    color: var(--text-faint);
    font-size: var(--fs-xs);
  }
  :global(.libcard) {
    flex: 0 1 300px;
  }
</style>
