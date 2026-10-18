<script lang="ts">
  import { api } from '$lib/api'
  import { plugins } from '$lib/plugins.svelte'
  import type { PluginInfo } from '$lib/types'
  import { Card, IconButton, InfoTip, Toggle, toast, tooltip } from '$lib/ui'

  let { readonly = false }: { readonly?: boolean } = $props()

  let scanning = $state(false)

  async function run(label: string, fn: () => Promise<unknown>) {
    try {
      await fn()
    } catch (e) {
      toast.error(label, { description: e instanceof Error ? e.message : String(e) })
    }
  }
  async function rescan() {
    scanning = true
    await run('Rescan failed', () => api.rescanPlugins())
    scanning = false
  }
  const pagesOf = (p: PluginInfo) => plugins.pages.filter((x) => x.plugin === p.id)
  const errorOf = (p: PluginInfo) => p.error ?? plugins.errors[p.id] ?? null
</script>

<Card title="Plugins" icon="extension">
  {#snippet actions()}
    <InfoTip text="Each folder in plugins/ with a plugin.json is a plugin. Saving any of its files reloads it live, no restart. See docs/plugins.md." />
    <IconButton icon="refresh" label="Rescan" size="sm" disabled={readonly || scanning} onclick={rescan} />
  {/snippet}
  <div class="stack">
    {#each plugins.list as p (p.id)}
      {@const err = errorOf(p)}
      <div class="pl">
        <div class="line">
          <span class="nm">
            <span class="icon st" class:bad={!!err} class:on={p.enabled && p.loaded && !err}>{err ? 'error' : 'extension'}</span>
            {p.name}
            {#if p.version}<span class="muted">{p.version}</span>{/if}
            {#if p.description}<InfoTip text={p.description} />{/if}
          </span>
          <span class="acts">
            {#each pagesOf(p) as pg (pg.id)}
              <a class="pg" href="#/p/{p.id}/{pg.id}" aria-label={pg.title} use:tooltip={pg.title}><span class="icon">{pg.icon || 'open_in_new'}</span></a>
            {/each}
            <IconButton icon="restart_alt" label="Reload" size="sm" disabled={readonly || !p.enabled} onclick={() => run('Reload failed', () => api.reloadPlugin(p.id))} />
            <Toggle checked={p.enabled} disabled={readonly} aria-label="Enable {p.name}" onchange={(v) => run('Not changed', () => api.setPluginEnabled(p.id, v))} />
          </span>
        </div>
        {#if err}<div class="err">{err}</div>{/if}
      </div>
    {:else}
      <div class="muted">No plugins installed</div>
    {/each}
  </div>
</Card>

<style>
  .stack {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
  }
  .pl {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .line {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--sp-3);
    min-height: 34px;
  }
  .nm {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
  }
  .st {
    font-size: 18px;
    color: var(--text-faint);
  }
  .st.on {
    color: var(--success);
  }
  .st.bad {
    color: var(--danger);
  }
  .acts {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    flex: none;
  }
  .pg {
    display: grid;
    place-items: center;
    width: 28px;
    height: 28px;
    border-radius: var(--r-sm);
    color: var(--text-muted);
  }
  .pg:hover {
    background: var(--surface-3);
    color: var(--text);
  }
  .pg .icon {
    font-size: 18px;
  }
  .muted {
    color: var(--text-muted);
    font-size: var(--fs-sm);
  }
  .err {
    color: var(--danger);
    font-size: var(--fs-xs);
    font-family: var(--font-mono);
    overflow-wrap: anywhere;
  }
</style>
