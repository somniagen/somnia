<script lang="ts">
  import TextInput from '$features/shell/TextInput.svelte'
  import { auth } from '$lib/auth.svelte'
  import type { Settings } from '$lib/types'
  import { Button, Field, IconButton } from '$lib/ui'

  interface Props {
    settings: Settings
    readonly: boolean
    local: boolean
    save: (patch: Partial<Settings>) => Promise<void>
  }
  let { settings, readonly, local, save }: Props = $props()

  let pw = $state('')
  const set = $derived(!!settings.lanPassword)

  async function savePw() {
    if (!pw) return
    await save({ lanPassword: pw })
    pw = ''
  }
</script>

<Field label="Password" info="Other devices must enter it once. This machine never needs it. Changing it signs every device out.">
  {#snippet children(id)}
    <div class="row">
      <TextInput
        {id}
        type="password"
        autocomplete="new-password"
        placeholder={set ? 'Password set' : 'No password'}
        bind:value={pw}
        disabled={readonly}
        onenter={savePw}
      />
      {#if pw}
        <IconButton icon="check" label="Save password" size="sm" onclick={savePw} />
      {:else if set && !readonly}
        <IconButton icon="close" label="Remove password" size="sm" variant="danger" onclick={() => save({ lanPassword: '' })} />
      {/if}
    </div>
  {/snippet}
</Field>

<Field label="HTTPS" info="Certificate and key files, for example from tailscale cert or mkcert. Notifications on other devices need HTTPS. Applies after a restart.">
  {#snippet children(id)}
    <div class="col">
      <TextInput {id} mono placeholder="Certificate (.crt / .pem)" value={settings.httpsCert} disabled={readonly} onchange={(v) => save({ httpsCert: v.trim() })} />
      <TextInput mono placeholder="Key (.key / .pem)" value={settings.httpsKey} disabled={readonly} onchange={(v) => save({ httpsKey: v.trim() })} />
    </div>
  {/snippet}
</Field>

{#if !local && set}
  <div class="out">
    <Button size="sm" icon="logout" onclick={() => auth.logout()}>Sign out</Button>
  </div>
{/if}

<style>
  .row {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
  }
  .col {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
  }
  .out {
    display: flex;
    justify-content: flex-end;
  }
</style>
