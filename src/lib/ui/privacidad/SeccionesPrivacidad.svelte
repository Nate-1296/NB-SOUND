<!--
  @component
  Privacidad y servicios en línea, e Inteligencia artificial, juntas: comparten el
  estado de la política de red y se cargan aparte del arranque (`check-paquete`).
-->
<script lang="ts">
  import { privacidad } from '$core/privacidad.svelte';

  import SeccionIa from './SeccionIa.svelte';
  import SeccionPrivacidad from './SeccionPrivacidad.svelte';

  interface Props {
    seccion?: 'privacidad' | 'ia';
  }
  let { seccion }: Props = $props();

  $effect(() => {
    void privacidad.refrescar();
  });
</script>

{#if !seccion || seccion === 'privacidad'}
  <SeccionPrivacidad />
{/if}
{#if !seccion || seccion === 'ia'}
  <SeccionIa />
{/if}
