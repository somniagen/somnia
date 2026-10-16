<script lang="ts">
  import type { HTMLAttributes } from 'svelte/elements'

  interface Props extends HTMLAttributes<HTMLSpanElement> {
    size?: number
    label?: string
  }
  let { size = 18, label = 'Loading', class: klass, style, ...rest }: Props = $props()
</script>

<span
  role={label ? "status" : undefined}
  aria-label={label || undefined}
  class={['spinner', klass]}
  style="--s: {size}px; {style ?? ''}"
  {...rest}
></span>

<style>
  .spinner {
    display: inline-block;
    flex: none;
    width: var(--s);
    height: var(--s);
    border-radius: 50%;
    border: 2px solid currentColor;
    border-right-color: transparent;
    opacity: 0.85;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .spinner {
      animation-duration: 1.6s;
    }
  }
</style>
