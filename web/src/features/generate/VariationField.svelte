<script lang="ts">
  import type { GenParams, Variation } from '$lib/types'
  import { Field, SeedField, Slider, Toggle } from '$lib/ui'

  let { p }: { p: GenParams } = $props()

  let lastSeed = $state(Math.floor(Math.random() * 4294967295))
  const v = $derived(p.variation)

  function set(patch: Partial<Variation>) {
    p.variation = { enabled: false, seed: -1, strength: 0.1, ...(p.variation ?? {}), ...patch }
  }
</script>

<Field label="Variation" info="Blends in noise from a second seed. Small strengths give close variations of the same image.">
  {#snippet trailing()}
    <Toggle checked={!!v?.enabled} onchange={(on) => set({ enabled: on })} size="sm" aria-label="Variation" />
  {/snippet}
  {#snippet children(id)}
    {#if v?.enabled}
      <div class="var">
        <Slider bind:value={() => v.strength, (s) => set({ strength: s })} min={0} max={1} step={0.01} defaultValue={0.1} />
        <SeedField
          {id}
          bind:value={() => (v.seed >= 0 ? v.seed : lastSeed), (s) => ((lastSeed = s), set({ seed: s }))}
          bind:locked={() => v.seed >= 0, (l) => set({ seed: l ? lastSeed : -1 })}
        />
      </div>
    {/if}
  {/snippet}
</Field>

<style>
  .var {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
  }
</style>
