/**
 * Cuándo cambió la biblioteca: un número que sube cada vez que algo la cambia
 * (borrar, editar, importar, una playlist, la carpeta). Las vistas lo leen en el
 * efecto que pide sus datos y se refrescan solas, sin recargar ni reiniciar: antes
 * una canción borrada seguía en Inicio, en el álbum y en Tu música hasta volver a
 * abrir la vista.
 *
 * La favorita no cuenta: se ve al momento en todas partes por `acciones.svelte.ts`,
 * y refrescar cada lista por un corazón movería las listas bajo el ratón.
 */
class Cambios {
  version = $state(0);

  avisar() {
    this.version += 1;
  }
}

export const cambios = new Cambios();

/** Los comandos del puente que cambian la biblioteca o sus playlists. */
export const COMANDOS_QUE_CAMBIAN: ReadonlySet<string> = new Set([
  'borrar_pista',
  'purgar_duplicados',
  'buscar_duplicados',
  'editar_pista',
  'editar_album',
  'completar_datos',
  'por_revisar_importar',
  'por_revisar_descartar',
  'carpeta_musica_aplicar',
  'crear_playlist',
  'renombrar_playlist',
  'borrar_playlist',
  'duplicar_playlist',
  'vaciar_playlist',
  'agregar_a_playlist',
  'quitar_de_playlist',
  'mover_en_playlist',
  'anclar_playlist',
  'crear_playlist_inteligente',
  'editar_playlist_inteligente',
  'regenerar_playlists_automaticas',
  'dj_guardar',
  'perfil_cambiar_foto'
]);
