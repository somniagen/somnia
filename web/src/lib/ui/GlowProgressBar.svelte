<script lang="ts">
  type Status = 'idle' | 'running' | 'success' | 'error'
  interface Props {
    value?: number | null
    status?: Status
    fixed?: boolean
    height?: number
    label?: string
    class?: string
    style?: string
  }
  let {
    value = 0,
    status = 'running',
    fixed = true,
    height = 3,
    label = 'Progress',
    class: klass,
    style,
  }: Props = $props()

  let shown = $state(false)
  let instant = $state(false)
  let prev: Status = 'idle'

  $effect(() => {
    const s = status
    const was = prev
    prev = s
    if (s === 'running') {
      if (was !== 'running') {
        instant = true
        setTimeout(() => (instant = false), 40)
      }
      shown = true
      return
    }
    if (s === 'idle') {
      shown = false
      return
    }
    shown = true
    const t = setTimeout(() => (shown = false), s === 'success' ? 650 : 2600)
    return () => clearTimeout(t)
  })

  let lastPct = 0
  $effect(() => {
    const v = pct
    if (v < lastPct - 0.5 && status === 'running') {
      instant = true
      setTimeout(() => (instant = false), 60)
    }
    lastPct = v
  })

  const indeterminate = $derived(status === 'running' && (value === null || value === undefined))
  const pct = $derived(status === 'success' ? 100 : Math.max(0, Math.min(1, value ?? 0)) * 100)
</script>

<div
  class={['gpb', status, klass, { fixed, shown, instant, indeterminate, empty: !indeterminate && pct <= 0 }]}
  style="--h: {height}px; {style ?? ''}"
  role="progressbar"
  aria-label={label}
  aria-valuemin={0}
  aria-valuemax={100}
  aria-valuenow={indeterminate ? undefined : Math.round(pct)}
  aria-hidden={!shown}
>
  <div class="fill" style={indeterminate ? '' : `width: ${pct}%`}>
    <span class="shine"></span>
    <span class="edge"></span>
  </div>
</div>

<style>
  .gpb {
    --c: var(--accent);
    --c2: var(--accent-strong);
    --glow: var(--accent-glow);
    position: relative;
    height: var(--h);
    width: 100%;
    opacity: 0;
    pointer-events: none;
    transition: opacity 450ms var(--ease);
    overflow-x: clip;
  }
  .gpb:not(.fixed) {
    border-radius: 2px;
    background: var(--grad-3);
  }
  .empty .edge {
    opacity: 0;
    animation: none;
  }
  /* below the notch / status bar, glow only spills downwards and hidden when idle so safari never samples it */
  .fixed {
    position: fixed;
    top: env(safe-area-inset-top, 0px);
    left: 0;
    right: 0;
    z-index: var(--z-progress);
    clip-path: inset(0 0 -120px 0);
    visibility: hidden;
    transition:
      opacity 450ms var(--ease),
      visibility 0s linear 450ms;
  }
  .shown {
    opacity: 1;
    transition-duration: 150ms;
  }
  .fixed.shown {
    visibility: visible;
    transition:
      opacity 150ms var(--ease),
      visibility 0s;
  }
  .error {
    --c: var(--danger);
    --c2: var(--danger);
    --glow: color-mix(in srgb, var(--danger) 55%, transparent);
  }
  .fill {
    position: relative;
    height: 100%;
    width: 0;
    border-radius: 0 2px 2px 0;
    background: linear-gradient(90deg, color-mix(in srgb, var(--c) 25%, transparent), var(--c) 60%, var(--c2));
    box-shadow:
      0 0 6px 0 var(--glow),
      0 0 18px 1px color-mix(in srgb, var(--glow) 45%, transparent);
    transition:
      width 420ms var(--ease),
      filter 300ms var(--ease);
  }
  .instant .fill {
    transition: none;
  }
  .shine {
    position: absolute;
    inset: 0;
    overflow: hidden;
    background: linear-gradient(90deg, transparent 0%, color-mix(in srgb, var(--text) 45%, transparent) 50%, transparent 100%) no-repeat;
    background-size: 30% 100%;
    animation: shine 1.8s linear infinite;
    opacity: 0.3;
    mix-blend-mode: overlay;
  }
  .edge {
    position: absolute;
    right: -2px;
    top: 50%;
    width: 160px;
    height: calc(var(--h) * 8 + 24px);
    transform: translateY(-50%);
    background: radial-gradient(ellipse at 96% 50%, var(--glow), color-mix(in srgb, var(--glow) 30%, transparent) 35%, transparent 70%);
    filter: blur(5px);
    animation: pulse 1.6s ease-in-out infinite;
  }
  .edge::after {
    content: '';
    position: absolute;
    right: 2px;
    top: 50%;
    width: 22px;
    height: var(--h);
    margin-top: calc(var(--h) / -2);
    border-radius: 2px;
    background: var(--c2);
    box-shadow:
      0 0 4px 1px var(--c2),
      0 0 12px 3px var(--glow),
      0 0 28px 8px var(--glow),
      0 0 56px 16px color-mix(in srgb, var(--glow) 40%, transparent);
  }
  .indeterminate .fill {
    width: 35%;
    animation: indet 1.3s var(--ease) infinite;
  }
  .success .fill {
    animation: flash 650ms var(--ease) forwards;
  }
  .success .edge,
  .error .edge {
    animation: none;
  }
  .error .shine {
    display: none;
  }
  @keyframes shine {
    from {
      background-position: -40% 0;
    }
    to {
      background-position: 140% 0;
    }
  }
  @keyframes pulse {
    0%,
    100% {
      opacity: 0.7;
    }
    50% {
      opacity: 1;
    }
  }
  @keyframes indet {
    from {
      transform: translateX(-100%);
    }
    to {
      transform: translateX(290%);
    }
  }
  @keyframes flash {
    0% {
      filter: brightness(1);
      box-shadow: 0 0 0 0 transparent;
    }
    30% {
      filter: brightness(1.6);
      box-shadow: 0 0 18px 3px var(--glow);
    }
    100% {
      filter: brightness(1);
      box-shadow: 0 0 6px 0 var(--glow);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .shine,
    .edge {
      animation: none;
    }
    .indeterminate .fill {
      width: 100%;
      animation: none;
      opacity: 0.6;
    }
    .fill {
      transition: none;
    }
  }
</style>
