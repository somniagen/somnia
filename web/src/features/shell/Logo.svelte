<script lang="ts">
  import { uid } from '$lib/ui/util'

  let { size = 28, wordmark = false, class: klass }: { size?: number; wordmark?: boolean; class?: string } = $props()
  const id = uid('logo')
</script>

<span class={['logo', klass]} aria-label="Somnia" role="img">
  <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
    <mask {id}>
      <rect width="32" height="32" fill="#fff" />
      <circle cx="19.5" cy="12.5" r="9.5" fill="#000" />
    </mask>
    <circle cx="14.5" cy="17.5" r="9.5" fill="currentColor" mask="url(#{id})" />
    <path d="M23 5.5l1.1 2.9 2.9 1.1-2.9 1.1L23 13.5l-1.1-2.9-2.9-1.1 2.9-1.1z" fill="currentColor" />
  </svg>
  {#if wordmark}<span class="wm" style="font-size: {Math.round(size * 0.62)}px">Somnia</span>{/if}
</span>

<style>
  .logo {
    display: inline-flex;
    align-items: center;
    gap: 0.5em;
    color: var(--text);
  }
  svg {
    flex: none;
  }
  .wm {
    font-weight: 600;
    letter-spacing: 0.06em;
    line-height: 1;
  }
</style>
