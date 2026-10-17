<script lang="ts">
  import { models } from '$features/models/store.svelte'
  import { session } from '$lib/session.svelte'
  import type { Family } from '$lib/types'
  import { IconButton, Menu, type MenuItem } from '$lib/ui'

  let { family }: { family: Family } = $props()

  $effect(() => models.start())

  const list = $derived(models.list.filter((m) => m.kind === 'embedding' && (m.family === family || m.family === null)))

  // names that look like positive embeddings go to the prompt, everything else to the negative
  const target = (name: string): 'positive' | 'negative' => (/pos/i.test(name) && !/neg/i.test(name) ? 'positive' : 'negative')
  const token = (name: string) => `embedding:${name}`

  function present(name: string) {
    const segs = (target(name) === 'positive' ? session.positive : session.negative)[session.family] ?? []
    return segs.some((s) => s.text.trim().toLowerCase() === token(name).toLowerCase())
  }

  function flip(name: string) {
    const which = target(name)
    const store = which === 'positive' ? session.positive : session.negative
    if (present(name)) store[session.family] = (store[session.family] ?? []).filter((s) => s.text.trim().toLowerCase() !== token(name).toLowerCase())
    else session.addBoilerplate(token(name), which)
  }

  const items = $derived<MenuItem[]>(
    list.length
      ? list.map((m) => ({ label: m.name, checked: present(m.name), onselect: () => flip(m.name) }))
      : [{ label: 'No embeddings in embeddings/', disabled: true }],
  )
</script>

<Menu {items} placement="bottom-end" label="Embeddings">
  {#snippet trigger({ toggle, open })}
    <IconButton icon="data_object" label="Embeddings" size="sm" active={open} onclick={toggle} />
  {/snippet}
</Menu>
