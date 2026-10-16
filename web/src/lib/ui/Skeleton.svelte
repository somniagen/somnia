<script lang="ts">
  interface Props {
    width?: string
    height?: string
    radius?: string
    circle?: boolean
    class?: string
    style?: string
  }
  let { width = '100%', height = '16px', radius = 'var(--r-sm)', circle = false, class: klass, style }: Props = $props()
</script>

<span
  class={['skel', klass]}
  aria-hidden="true"
  style="width: {width}; height: {circle ? width : height}; border-radius: {circle ? '50%' : radius}; {style ?? ''}"
></span>

<style>
  .skel {
    display: block;
    background-color: var(--surface-2);
    background-image: linear-gradient(90deg, transparent 25%, var(--shimmer) 50%, transparent 75%);
    background-size: 200% 100%;
    animation: shimmer 1.4s linear infinite;
  }
  @keyframes shimmer {
    from {
      background-position: 150% 0;
    }
    to {
      background-position: -50% 0;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .skel {
      animation: none;
    }
  }
</style>
