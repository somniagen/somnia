<script lang="ts">
  import { auth } from '$lib/auth.svelte'
  import { Button } from '$lib/ui'
  import Logo from './Logo.svelte'
  import TextInput from './TextInput.svelte'

  let password = $state('')
  let busy = $state(false)
  let wrong = $state(false)
  let error = $state('')

  async function submit(e: SubmitEvent) {
    e.preventDefault()
    if (!password || busy) return
    busy = true
    wrong = false
    error = ''
    try {
      if (!(await auth.login(password))) {
        wrong = true
        password = ''
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err)
    } finally {
      busy = false
    }
  }
</script>

<div class="login">
  <form class="card" class:shake={wrong} onsubmit={submit}>
    <Logo size={40} wordmark />
    <TextInput
      type="password"
      name="password"
      autocomplete="current-password"
      placeholder="Password"
      aria-label="Password"
      aria-invalid={wrong}
      bind:value={password}
      autofocus
    />
    {#if wrong}<div class="msg">Wrong password</div>{:else if error}<div class="msg">{error}</div>{/if}
    <Button type="submit" variant="primary" full loading={busy} disabled={!password}>Unlock</Button>
  </form>
</div>

<style>
  .login {
    position: fixed;
    inset: 0;
    z-index: var(--z-tooltip);
    display: grid;
    place-items: center;
    padding: calc(var(--sp-4) + env(safe-area-inset-top)) var(--sp-4) calc(var(--sp-4) + env(safe-area-inset-bottom));
    background: var(--bg);
    background-image: var(--grad-bg);
  }
  .card {
    width: min(340px, 100%);
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: var(--sp-3);
    padding: var(--sp-5);
    border: 1px solid var(--hairline);
    border-radius: var(--r-lg);
    background: var(--grad-2);
    box-shadow: var(--sheen), var(--shadow-3);
  }
  .card :global(.logo) {
    align-self: center;
    margin-bottom: var(--sp-3);
    color: var(--text);
  }
  .msg {
    color: var(--danger);
    font-size: var(--fs-sm);
  }
  .shake {
    animation: shake 300ms var(--ease);
  }
  @keyframes shake {
    25% {
      transform: translateX(-6px);
    }
    75% {
      transform: translateX(6px);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .shake {
      animation: none;
    }
  }
</style>
