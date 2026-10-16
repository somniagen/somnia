<script lang="ts" module>
  type Inline = { t: 'text' | 'b' | 'i' | 'a'; s: string; href?: string }
  type Block = { list: boolean; lines: Inline[][] }

  function inline(s: string): Inline[] {
    const out: Inline[] = []
    const re = /\*\*(.+?)\*\*|\*(.+?)\*|\[([^\]]+)\]\(([^)\s]+)\)/g
    let last = 0
    for (const m of s.matchAll(re)) {
      if (m.index! > last) out.push({ t: 'text', s: s.slice(last, m.index) })
      if (m[1]) out.push({ t: 'b', s: m[1] })
      else if (m[2]) out.push({ t: 'i', s: m[2] })
      else {
        let href = m[4]
        if (href.startsWith('/')) href = 'https://danbooru.donmai.us' + href
        out.push(/^https?:\/\//.test(href) ? { t: 'a', s: m[3], href } : { t: 'text', s: m[3] })
      }
      last = m.index! + m[0].length
    }
    if (last < s.length) out.push({ t: 'text', s: s.slice(last) })
    return out
  }

  export function lite(body: string, maxBlocks = 2, maxChars = 700): Block[] {
    const blocks: Block[] = []
    let chars = 0
    for (const raw of body.replace(/\r/g, '').split(/\n\s*\n/)) {
      const lines = raw
        .split('\n')
        .map((l) => l.trim())
        .filter((l) => l && !/^[*-]?\s*!(post|asset)/.test(l))
      if (!lines.length) continue
      if (/^\*\*[^*]+\*\*$/.test(lines[0]) || /^h\d\./.test(lines[0]) || /^#/.test(lines[0])) {
        if (blocks.length) break
        continue
      }
      const list = lines.every((l) => /^[*-]\s/.test(l))
      const text = list ? lines.map((l) => l.replace(/^[*-]\s+/, '')) : [lines.join(' ')]
      blocks.push({ list, lines: text.slice(0, 6).map(inline) })
      chars += raw.length
      if (blocks.length >= maxBlocks || chars > maxChars) break
    }
    return blocks
  }
</script>

<script lang="ts">
  import type { Snippet } from 'svelte'
  import { Spinner } from '$lib/ui'
  import type { TagCategory } from '$lib/types'
  import { categories, categoryName, colorOf, compact, fetchRelated, fetchWiki } from './tags.svelte'

  let {
    name,
    count,
    compact: small = false,
    actions,
    onadd,
    exclude,
  }: {
    name: string
    count?: number
    compact?: boolean
    actions?: Snippet
    // shows commonly paired tags as one-tap additions
    onadd?: (name: string) => void
    exclude?: Set<string>
  } = $props()
  const related = $derived(onadd ? fetchRelated(name) : null)
  let more = $state(false)

  const wiki = $derived(fetchWiki(name))
  const cat = $derived<TagCategory | null | undefined>(categories.get(name))
</script>

<div class="wiki" class:small>
  <div class="head">
    <span class="dot" style="background: {colorOf(cat)}"></span>
    <span class="name" style="color: {colorOf(cat)}">{name.replace(/_/g, ' ')}</span>
    {#if cat != null}<span class="cat">{categoryName[cat]}</span>{/if}
    {#if count}<span class="cat">{compact(count)}</span>{/if}
    <a
      class="ext icon"
      href="https://danbooru.donmai.us/wiki_pages/{encodeURIComponent(name)}"
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Open on Danbooru">open_in_new</a
    >
  </div>
  {#if actions}<div class="acts">{@render actions()}</div>{/if}
  {#await wiki}
    <div class="body muted"><Spinner size={14} /></div>
  {:then w}
    {@const blocks = w ? lite(w.body) : []}
    {#if blocks.length}
      <div
        class="body"
        class:clamp={small && !more}
        role="presentation"
        onclick={(e) => {
          if (small && !(e.target as HTMLElement).closest('a')) more = !more
        }}
      >
        {#each blocks as b, i (i)}
          {#if b.list}
            <ul>
              {#each b.lines as l, j (j)}<li>{@render line(l)}</li>{/each}
            </ul>
          {:else}
            <p>{@render line(b.lines[0])}</p>
          {/if}
        {/each}
      </div>
    {:else}
      <div class="body muted">No wiki entry</div>
    {/if}
  {/await}
  {#if related}
    {#await related then list}
      {@const shown = list.filter((t) => !exclude?.has(t.name)).slice(0, small ? 8 : 10)}
      {#if shown.length}
        <div class="rel" role="group" aria-label="Often used with">
          {#each shown as t (t.name)}
            <button
              type="button"
              class="rt"
              style="--c: {colorOf(t.category)}"
              title="Add {t.name.replace(/_/g, ' ')}"
              onpointerdown={(e) => e.preventDefault()}
              onclick={() => onadd?.(t.name)}><span class="icon">add</span>{t.name.replace(/_/g, ' ')}</button
            >
          {/each}
        </div>
      {/if}
    {/await}
  {/if}
</div>

{#snippet line(parts: Inline[])}
  {#each parts as p, i (i)}
    {#if p.t === 'b'}<b>{p.s}</b>{:else if p.t === 'i'}<i>{p.s}</i>{:else if p.t === 'a'}<a
        href={p.href}
        target="_blank"
        rel="noopener noreferrer">{p.s}</a
      >{:else}{p.s}{/if}
  {/each}
{/snippet}

<style>
  .wiki {
    width: min(340px, calc(100vw - 32px));
    padding: var(--sp-1) var(--sp-2) var(--sp-2);
    font-size: var(--fs-sm);
  }
  .wiki.small {
    width: auto;
    padding: var(--sp-2) var(--sp-3) var(--sp-3);
  }
  .acts {
    display: flex;
    flex-wrap: wrap;
    gap: var(--sp-2);
    margin: 2px 0 var(--sp-2);
  }
  .clamp {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    overflow: hidden;
  }
  .clamp :global(ul),
  .clamp :global(p) {
    display: inline;
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: 28px;
  }
  .dot {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }
  .name {
    font-weight: 600;
    overflow-wrap: anywhere;
  }
  .cat {
    color: var(--text-faint);
    font-size: var(--fs-xs);
    white-space: nowrap;
  }
  .ext {
    margin-left: auto;
    font-size: 16px;
    color: var(--text-muted);
    text-decoration: none;
    padding: 4px;
    border-radius: var(--r-sm);
  }
  .ext:hover {
    background: var(--hover);
    color: var(--text);
  }
  .body {
    color: var(--text-muted);
    line-height: 1.5;
  }
  .body.muted {
    color: var(--text-faint);
    padding-top: 2px;
  }
  p,
  ul {
    margin: 4px 0 0;
  }
  ul {
    padding-left: 18px;
  }
  b {
    color: var(--text);
    font-weight: 600;
  }
  a {
    color: var(--text);
  }
  .rel {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: var(--sp-2);
    padding-top: var(--sp-2);
    border-top: 1px solid var(--hairline);
  }
  .rt {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    height: 24px;
    padding: 0 8px 0 4px;
    border: 0;
    border-radius: var(--r-sm);
    background: var(--grad-3);
    box-shadow: var(--sheen);
    color: var(--c);
    font: inherit;
    font-size: var(--fs-xs);
    white-space: nowrap;
    cursor: pointer;
    transition: transform var(--dur-fast) var(--ease);
  }
  .rt:hover {
    background: var(--grad-4);
  }
  .rt:active {
    transform: scale(0.95);
  }
  .rt .icon {
    font-size: 14px;
    color: var(--text-muted);
  }
  @media (pointer: coarse) {
    .rt {
      height: 32px;
    }
  }
</style>
