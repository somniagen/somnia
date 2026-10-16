<script lang="ts">
  import IconButton from './IconButton.svelte'

  interface Props {
    value?: number
    locked?: boolean
    max?: number
    id?: string
    disabled?: boolean
    class?: string
    style?: string
    onchange?: (v: number) => void
  }
  let {
    value = $bindable(0),
    locked = $bindable(false),
    max = 4294967295,
    id,
    disabled = false,
    class: klass,
    style,
    onchange,
  }: Props = $props()

  let draft = $state<string | null>(null)
  let spin = $state(0)

  function set(v: number) {
    v = Math.max(0, Math.min(max, Math.floor(v)))
    if (v !== value) {
      value = v
      onchange?.(v)
    }
  }
  function roll() {
    spin++
    set(Math.floor(Math.random() * (max + 1)))
  }
  function commit() {
    if (draft === null) return
    const n = parseInt(draft.replace(/\D/g, ''), 10)
    draft = null
    if (Number.isFinite(n)) set(n)
  }
</script>

<div class={['seed', klass, { locked, disabled }]} {style}>
  <input
    {id}
    type="text"
    inputmode="numeric"
    aria-label="Seed"
    {disabled}
    value={draft ?? String(value)}
    oninput={(e) => (draft = e.currentTarget.value)}
    onfocus={(e) => e.currentTarget.select()}
    onblur={commit}
    onkeydown={(e) => {
      if (e.key === 'Enter') e.currentTarget.blur()
      if (e.key === 'Escape') {
        draft = null
        e.currentTarget.blur()
      }
    }}
  />
  <span class="dice" style="--r: {spin * 180}deg">
    <IconButton icon="casino" label="Random seed" size="sm" {disabled} onclick={roll} />
  </span>
  <IconButton
    icon={locked ? 'lock' : 'lock_open'}
    label={locked ? 'Seed locked' : 'New seed each run'}
    size="sm"
    active={locked}
    {disabled}
    onclick={() => (locked = !locked)}
  />
</div>

<style>
  .seed {
    display: flex;
    align-items: center;
    gap: 2px;
    height: var(--control-h);
    padding-right: 4px;
    border-radius: var(--r-md);
    background: var(--grad-2);
    transition: background var(--dur-fast) var(--ease);
  }
  .seed:hover,
  .seed:focus-within {
    background: var(--grad-3);
  }
  .seed:focus-within {
    box-shadow: inset 0 0 0 1px var(--focus-line);
  }
  input {
    flex: 1;
    min-width: 0;
    width: 11ch;
    height: 100%;
    padding: 0 10px;
    border: 0;
    background: none;
    color: var(--text);
    font: inherit;
    font-variant-numeric: tabular-nums;
    outline: none;
    transition: color var(--dur) var(--ease);
  }
  input:focus-visible {
    box-shadow: none;
  }
  .seed:not(.locked) input:not(:focus) {
    color: var(--text-muted);
  }
  .dice :global(.icon) {
    transform: rotate(var(--r));
    transition: transform 400ms var(--ease);
  }
  .disabled {
    opacity: 0.45;
  }
  @media (pointer: coarse) {
    .seed {
      height: var(--touch);
    }
  }
</style>
