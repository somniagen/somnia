<script lang="ts">
  import type { Snippet } from 'svelte'
  import BottomSheet from './BottomSheet.svelte'
  import Modal from './Modal.svelte'
  import { mobile } from './util'

  interface Props {
    open?: boolean
    title?: string
    width?: number | string
    snaps?: number[]
    snap?: number
    dismissible?: boolean
    class?: string
    style?: string
    onclose?: () => void
    footer?: Snippet
    children?: Snippet
  }
  let { open = $bindable(false), snap = $bindable(0), width, snaps, ...rest }: Props = $props()
</script>

{#if mobile.current}
  <BottomSheet bind:open bind:snap {snaps} {...rest} />
{:else}
  <Modal bind:open {width} {...rest} />
{/if}
