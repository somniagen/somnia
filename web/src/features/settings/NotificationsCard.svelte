<script lang="ts">
  import { api } from '$lib/api'
  import { currentSubscription, deviceLabel, disablePush, enablePush, pushSupport } from '$lib/push'
  import type { PushSubscriptionJson } from '$lib/types'
  import { Button, Card, InfoTip, Toggle, toast } from '$lib/ui'

  const support = pushSupport()
  let endpoint = $state<string | null>(null)
  let busy = $state(false)
  let testing = $state(false)
  const denied = support === 'ok' && Notification.permission === 'denied'

  $effect(() => {
    currentSubscription().then(
      (sub) => {
        endpoint = sub?.endpoint ?? null
        // the server may have dropped it, re-registering is idempotent
        if (sub) api.pushSubscribe(sub.toJSON() as PushSubscriptionJson, deviceLabel()).catch(() => {})
      },
      () => {},
    )
  })

  async function toggle(on: boolean) {
    busy = true
    try {
      if (on) endpoint = (await enablePush()).endpoint
      else {
        await disablePush()
        endpoint = null
      }
    } catch (e) {
      toast.error('Notifications not changed', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      busy = false
    }
  }

  async function test() {
    if (!endpoint) return
    testing = true
    try {
      const r = await api.pushTest(endpoint)
      if (!r.sent) toast.error('Nothing was sent', { description: 'Turn notifications off and on again.' })
    } catch (e) {
      toast.error('Test failed', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      testing = false
    }
  }

  const why = {
    insecure: {
      text: 'Needs HTTPS',
      tip: 'Browsers only allow notifications on HTTPS or on the machine running Somnia. Add a certificate under Network, restart, and open the https address.',
    },
    'ios-browser': {
      text: 'Add to Home Screen first',
      tip: 'On iPhone and iPad notifications only work in the installed app: Share, Add to Home Screen, then open Somnia from the home screen.',
    },
    unsupported: { text: 'Not supported in this browser', tip: 'This browser has no web push support.' },
  }
</script>

<Card title="Notifications" icon="notifications">
  <div class="stack">
    {#if support === 'ok'}
      <div class="line">
        <span class="lbl">This device <InfoTip text="Notifies when the queue finishes or a generation fails, unless Somnia is open in front of you." /></span>
        <Toggle checked={!!endpoint} disabled={busy || (denied && !endpoint)} aria-label="Notifications on this device" onchange={toggle} />
      </div>
      {#if denied && !endpoint}
        <div class="muted">Blocked in browser settings</div>
      {/if}
      {#if endpoint}
        <div class="line">
          <span class="muted">{deviceLabel()}</span>
          <Button size="sm" icon="notifications_active" loading={testing} onclick={test}>Test</Button>
        </div>
      {/if}
    {:else}
      <div class="line">
        <span class="lbl muted"><span class="icon">notifications_off</span>{why[support].text} <InfoTip text={why[support].tip} /></span>
      </div>
    {/if}
  </div>
</Card>

<style>
  .stack {
    display: flex;
    flex-direction: column;
    gap: var(--sp-4);
  }
  .line {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--sp-3);
    min-height: 34px;
  }
  .lbl {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .lbl .icon {
    font-size: 18px;
  }
  .muted {
    color: var(--text-muted);
    font-size: var(--fs-sm);
  }
</style>
