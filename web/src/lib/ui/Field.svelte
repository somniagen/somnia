<script lang="ts">
  import type { Snippet } from 'svelte'
  import InfoTip from './InfoTip.svelte'

  interface Props {
    label?: string
    info?: string
    hint?: string
    error?: string | null
    inline?: boolean
    id?: string
    class?: string
    style?: string
    trailing?: Snippet
    children: Snippet<[string]>
  }
  let { label, info, hint, error, inline = false, id, class: klass, style, trailing, children }: Props = $props()

  const auto = $props.id()
  const fid = $derived(id ?? `f-${auto}`)
</script>

<div class={['field', klass, { inline, invalid: !!error }]} {style}>
  {#if label || trailing}
    <div class="head">
      {#if label}<label for={fid}>{label}</label>{/if}
      {#if info}<InfoTip text={info} />{/if}
      {#if trailing}<div class="trail">{@render trailing()}</div>{/if}
    </div>
  {/if}
  <div class="control">{@render children(fid)}</div>
  {#if error}
    <div class="msg err" role="alert">{error}</div>
  {:else if hint}
    <div class="msg">{hint}</div>
  {/if}
</div>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 4px;
    min-height: 20px;
  }
  label {
    font-size: var(--fs-sm);
    font-weight: 500;
    color: var(--text-muted);
  }
  .trail {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: var(--sp-1);
    color: var(--text-faint);
    font-size: var(--fs-sm);
  }
  .control {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .control > :global(*) {
    min-width: 0;
  }
  .inline {
    flex-direction: row;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--sp-3);
  }
  .inline .head {
    flex: 0 0 auto;
    min-width: 96px;
  }
  .inline .control {
    flex: 1;
  }
  .inline .msg {
    flex-basis: 100%;
  }
  .msg {
    font-size: var(--fs-xs);
    color: var(--text-faint);
  }
  .err {
    color: var(--danger);
  }
</style>
