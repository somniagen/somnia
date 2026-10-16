<script lang="ts">
  import { flip } from 'svelte/animate'
  import { dismiss, pause, resume, toasts, type ToastItem } from './toast.svelte'

  const icons = { success: 'check_circle', error: 'error', info: 'info' }

  function slide(_: Element) {
    return {
      duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 220,
      css: (t: number) => `opacity: ${t}; transform: translateY(${(1 - t) * 12}px) scale(${0.96 + t * 0.04})`,
    }
  }
  function act(t: ToastItem) {
    t.action?.run()
    dismiss(t.id)
  }
</script>

<div class="toaster" aria-live="polite" aria-relevant="additions">
  {#each toasts as t (t.id)}
    <div
      class="toast {t.kind}"
      role={t.kind === 'error' ? 'alert' : 'status'}
      animate:flip={{ duration: 200 }}
      transition:slide
      onpointerenter={() => pause(t.id)}
      onpointerleave={() => resume(t.id)}
    >
      <span class="icon kind" aria-hidden="true">{t.icon ?? icons[t.kind]}</span>
      <div class="text">
        <div class="msg">{t.message}</div>
        {#if t.description}<div class="desc">{t.description}</div>{/if}
      </div>
      {#if t.action}
        <button type="button" class="action" onclick={() => act(t)}>{t.action.label}</button>
      {/if}
      <button type="button" class="x" aria-label="Dismiss" onclick={() => dismiss(t.id)}>
        <span class="icon">close</span>
      </button>
    </div>
  {/each}
</div>

<style>
  .toaster {
    position: fixed;
    right: var(--sp-4);
    bottom: var(--sp-4);
    z-index: var(--z-toast);
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: var(--sp-2);
    width: min(380px, calc(100vw - 32px));
    pointer-events: none;
  }
  .toast {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    width: 100%;
    padding: 10px 8px 10px 14px;
    border-radius: var(--r-md);
    background: var(--grad-3);
    border: 1px solid var(--hairline);
    box-shadow: var(--shadow-3);
    pointer-events: auto;
  }
  .kind {
    flex: none;
    font-variation-settings: 'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24;
    color: var(--text-muted);
  }
  .success .kind {
    color: var(--success);
  }
  .error .kind {
    color: var(--danger);
  }
  .info .kind {
    color: var(--accent);
  }
  .text {
    flex: 1;
    min-width: 0;
  }
  .msg {
    font-size: var(--fs-md);
  }
  .desc {
    font-size: var(--fs-sm);
    color: var(--text-muted);
    overflow-wrap: anywhere;
  }
  .action {
    flex: none;
    height: var(--control-h-sm);
    padding: 0 10px;
    border: 0;
    border-radius: var(--r-sm);
    background: var(--accent-soft);
    color: var(--accent-strong);
    font: inherit;
    font-size: var(--fs-sm);
    font-weight: 500;
    cursor: pointer;
    transition: background var(--dur-fast) var(--ease), transform var(--dur-fast) var(--ease);
  }
  .action:hover {
    background: var(--grad-accent);
    color: var(--text-on-accent);
  }
  .action:active,
  .x:active {
    transform: scale(0.95);
  }
  .x {
    display: grid;
    place-items: center;
    flex: none;
    width: 28px;
    height: 28px;
    padding: 0;
    border: 0;
    border-radius: var(--r-sm);
    background: none;
    color: var(--text-faint);
    cursor: pointer;
  }
  .x .icon {
    font-size: 18px;
  }
  .x:hover {
    background: var(--hover);
    color: var(--text);
  }
  @media (max-width: 640px) {
    .toaster {
      left: var(--sp-3);
      right: var(--sp-3);
      bottom: calc(var(--sp-3) + env(safe-area-inset-bottom));
      width: auto;
      align-items: stretch;
    }
  }
  @media (pointer: coarse) {
    .x,
    .action {
      min-height: 40px;
      min-width: 40px;
    }
  }
</style>
