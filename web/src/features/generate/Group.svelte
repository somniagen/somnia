<script lang="ts">
  import type { Snippet } from 'svelte'
  import { Toggle } from '$lib/ui'

  interface Props {
    id: string
    title: string
    icon: string
    enabled?: boolean | undefined
    toggleable?: boolean
    children: Snippet
  }
  let { id, title, icon, enabled = $bindable(), toggleable = false, children }: Props = $props()

  const key = $derived(`somnia.group.${id}`)
  let open = $state(read())

  function read() {
    try {
      return localStorage.getItem(key) === '1'
    } catch {
      return false
    }
  }
  function toggle() {
    open = !open
    try {
      localStorage.setItem(key, open ? '1' : '0')
    } catch {}
  }
</script>

<section class="group" class:open>
  <div class="head">
    <button type="button" class="hb" onclick={toggle} aria-expanded={open}>
      <span class="icon ic">{icon}</span>
      <span class="t">{title}</span>
      <span class="icon chev">expand_more</span>
    </button>
    {#if toggleable}
      <Toggle bind:checked={enabled} size="sm" aria-label={`Enable ${title}`} />
    {/if}
  </div>
  {#if open}
    <div class="body">{@render children()}</div>
  {/if}
</section>

<style>
  .group {
    border: 1px solid var(--hairline);
    border-radius: var(--r-lg);
    background: var(--surface-1);
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    padding-right: var(--sp-3);
  }
  .hb {
    flex: 1;
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: 40px;
    padding: 0 var(--sp-3);
    border: 0;
    background: none;
    color: var(--text);
    font: inherit;
    font-weight: 500;
    text-align: left;
    cursor: pointer;
    border-radius: var(--r-lg);
    transition: background-color var(--dur-fast) var(--ease);
  }
  .hb:hover {
    background: var(--hover);
  }
  .hb:active {
    background: var(--pressed);
  }
  .ic {
    font-size: 18px;
    color: var(--text-muted);
  }
  .t {
    flex: 1;
  }
  .chev {
    font-size: 18px;
    color: var(--text-faint);
    transition: transform var(--dur) var(--ease);
  }
  .open .chev {
    transform: rotate(180deg);
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    padding: var(--sp-1) var(--sp-3) var(--sp-4);
  }
</style>
