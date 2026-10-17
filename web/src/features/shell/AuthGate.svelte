<script lang="ts">
  import { auth } from '$lib/auth.svelte'
  import Login from './Login.svelte'
</script>

{#if auth.locked}<Login />{/if}
