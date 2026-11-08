#!/usr/bin/env bash
# Arnés reproducible de las pruebas finales de audio (Fase 2).
#
# Todo ocurre bajo ~/.cache/nb-sound-qa. La base se copia, los datos derivados se
# copian y la música entra en la copia mediante enlaces duros. La biblioteca real
# solo se abre en modo lectura. Las órdenes de reproducción viajan por MPRIS, como
# lo haría el escritorio.

set -euo pipefail

RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
QA_BASE=${NB_QA_ROOT:-"$HOME/.cache/nb-sound-qa/pruebas-finales"}
DATOS_REALES=${NB_QA_DATOS_REALES:-"${XDG_DATA_HOME:-$HOME/.local/share}/nb-sound"}
CACHE_REAL=${NB_QA_CACHE_REAL:-"${XDG_CACHE_HOME:-$HOME/.cache}/nb-sound"}
MUSICA=${NB_QA_MUSICA:-"$HOME/Música/biblioteca"}
BINARIO=${NB_QA_BINARIO:-"$RAIZ/src-tauri/target/debug/nb-sound"}
MANIFIESTO_REAL=${NB_QA_ALBUM_MP3:-"taylor_swift/albumes/the_life_of_a_showgirl/"}
ID_MPRIS=org.mpris.MediaPlayer2.nbsound
OBJETO_MPRIS=/org/mpris/MediaPlayer2
SUMIDERO=nb_sound_qa
MODULO_SUMIDERO=
MODULO_RESTORE=
SINK_INPUT_APP=
NODO_SUMIDERO=
PID_APP=
PID_PAREC=

if [[ ${NB_QA_EN_SCOPE:-0} != 1 ]]; then
  exec systemd-run --user --scope -p MemoryMax=6G -- \
    env NB_QA_EN_SCOPE=1 "$0" "$@"
fi

uso() {
  printf '%s\n' \
    'Uso: scripts/qa/audio-qa.sh preparar|album-mp3|album-flac|buscar-pausar|ecualizador|normalizacion|todo' \
    '' \
    'Variables: NB_QA_ROOT, NB_QA_BINARIO, NB_QA_MUSICA, NB_QA_DATOS_REALES.' \
    'El guion se relanza solo con systemd-run --user --scope -p MemoryMax=6G.'
}

exigir() {
  if ! "$@"; then
    printf 'Fallo: %s\n' "$*" >&2
    exit 1
  fi
}

limpiar() {
  if [[ -n ${PID_PAREC:-} ]] && kill -0 "$PID_PAREC" 2>/dev/null; then
    kill -INT "$PID_PAREC" 2>/dev/null || true
    wait "$PID_PAREC" 2>/dev/null || true
  fi
  if [[ -n ${PID_APP:-} ]] && kill -0 "$PID_APP" 2>/dev/null; then
    kill -TERM "$PID_APP" 2>/dev/null || true
    wait "$PID_APP" 2>/dev/null || true
  fi
  if [[ -n ${MODULO_SUMIDERO:-} ]]; then
    pactl unload-module "$MODULO_SUMIDERO" >/dev/null 2>&1 || true
  fi
  if [[ -n ${MODULO_RESTORE:-} ]]; then
    pactl load-module module-stream-restore >/dev/null 2>&1 || true
  fi
}
trap limpiar EXIT INT TERM

componentes() {
  for programa in pactl parec busctl sqlite3 ffmpeg systemd-run pw-cli; do
    exigir command -v "$programa" >/dev/null
  done
  exigir test -x "$BINARIO"
  exigir test -f "$DATOS_REALES/nb-sound.sqlite"
  exigir test -d "$MUSICA"
}

base_de_datos() {
  printf '%s/datos/nb-sound.sqlite\n' "$QA_BASE"
}

copiar_datos() {
  local db destino temporal
  db=$(base_de_datos)
  mkdir -p "$QA_BASE/datos/portadas" "$QA_BASE/datos/agregados" \
    "$QA_BASE/datos/movil" "$QA_BASE/datos/por-revisar" "$QA_BASE/datos/stems" \
    "$QA_BASE/cache" "$QA_BASE/registros" "$QA_BASE/informes" "$QA_BASE/fixtures" \
    "$QA_BASE/biblioteca" "$QA_BASE/xdg-data" "$QA_BASE/xdg-cache" "$QA_BASE/xdg-config"

  if [[ -z $(find "$QA_BASE/datos/portadas" -mindepth 1 -maxdepth 1 -print -quit) ]]; then
    cp -a --reflink=auto "$DATOS_REALES/portadas/." "$QA_BASE/datos/portadas/"
  fi
  if [[ -d "$CACHE_REAL" ]]; then
    cp -a --reflink=auto "$CACHE_REAL/." "$QA_BASE/cache/"
  fi

  # Se copia con la API de copia de SQLite para no llevarse un WAL a medias.
  temporal="$db.tmp-$$"
  rm -f "$temporal" "$db-wal" "$db-shm"
  sqlite3 "$DATOS_REALES/nb-sound.sqlite" ".backup '$temporal'"
  mv -f "$temporal" "$db"
  sqlite3 "$db" "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;"

  if [[ -z $(find "$QA_BASE/biblioteca" -mindepth 1 -maxdepth 1 -print -quit) ]]; then
    cp -al "$MUSICA/." "$QA_BASE/biblioteca/"
  fi
}

generar_fixtures() {
  local f="$QA_BASE/fixtures"
  if [[ ! -f "$f/flac-01.flac" ]]; then
    ffmpeg -hide_banner -loglevel error -y -f lavfi \
      -i 'aevalsrc=0.35*sin(2*PI*440*t):s=48000:d=3' -ac 2 \
      -metadata title='QA FLAC 1' -metadata artist='QA' -metadata album='QA FLAC continuo' \
      -c:a flac "$f/flac-01.flac"
    ffmpeg -hide_banner -loglevel error -y -f lavfi \
      -i 'aevalsrc=0.35*sin(2*PI*440*t):s=48000:d=3' -ac 2 \
      -metadata title='QA FLAC 2' -metadata artist='QA' -metadata album='QA FLAC continuo' \
      -c:a flac "$f/flac-02.flac"
    ffmpeg -hide_banner -loglevel error -y -f lavfi \
      -i 'aevalsrc=0.35*sin(2*PI*if(lt(t\,3)\,440\,1760)*t):s=48000:d=10' -ac 2 \
      -metadata title='QA búsqueda y pausa' -metadata artist='QA' -metadata album='QA señales' \
      -c:a flac "$f/buscar-pausa.flac"
    ffmpeg -hide_banner -loglevel error -y -f lavfi \
      -i 'anoisesrc=color=white:amplitude=0.55:sample_rate=48000:duration=4' -ac 2 \
      -metadata title='QA ecualizador' -metadata artist='QA' -metadata album='QA señales' \
      -c:a flac "$f/ecualizador.flac"
    ffmpeg -hide_banner -loglevel error -y -f lavfi \
      -i 'anoisesrc=color=pink:amplitude=1.0:sample_rate=48000:duration=8' -ac 2 \
      -metadata title='QA alta' -metadata artist='QA' -metadata album='QA normalización' \
      -c:a flac "$f/alta.flac"
    ffmpeg -hide_banner -loglevel error -y -f lavfi \
      -i 'anoisesrc=color=pink:amplitude=0.316227766:sample_rate=48000:duration=8' -ac 2 \
      -metadata title='QA baja' -metadata artist='QA' -metadata album='QA normalización' \
      -c:a flac "$f/baja.flac"
  fi
  mkdir -p "$QA_BASE/biblioteca/qa/flac" "$QA_BASE/biblioteca/qa/senales"
  ln -f "$f/flac-01.flac" "$QA_BASE/biblioteca/qa/flac/01.flac"
  ln -f "$f/flac-02.flac" "$QA_BASE/biblioteca/qa/flac/02.flac"
  ln -f "$f/buscar-pausa.flac" "$QA_BASE/biblioteca/qa/senales/buscar-pausa.flac"
  ln -f "$f/ecualizador.flac" "$QA_BASE/biblioteca/qa/senales/ecualizador.flac"
  ln -f "$f/alta.flac" "$QA_BASE/biblioteca/qa/senales/alta.flac"
  ln -f "$f/baja.flac" "$QA_BASE/biblioteca/qa/senales/baja.flac"
}

insertar_fixtures() {
  local db artista album album_senales id_flac1 id_flac2 id_buscar id_eq id_alta id_baja
  db=$(base_de_datos)
  artista=$(sqlite3 "$db" "SELECT coalesce(max(id), 0) + 1 FROM artistas")
  album=$(sqlite3 "$db" "SELECT coalesce(max(id), 0) + 1 FROM albumes")
  album_senales=$((album + 1))
  id_flac1=$(sqlite3 "$db" "SELECT coalesce(max(id), 0) + 1 FROM pistas")
  id_flac2=$((id_flac1 + 1))
  id_buscar=$((id_flac1 + 2))
  id_eq=$((id_flac1 + 3))
  id_alta=$((id_flac1 + 4))
  id_baja=$((id_flac1 + 5))

  sqlite3 "$db" <<SQL
DELETE FROM pistas WHERE ruta LIKE 'qa/%';
DELETE FROM albumes WHERE clave IN ('qa-fixture-flac', 'qa-fixture-senales');
DELETE FROM artistas WHERE clave = 'qa-fixture';
INSERT INTO artistas (id, nombre, clave) VALUES ($artista, 'QA', 'qa-fixture');
INSERT INTO albumes
  (id, artista_id, titulo, clave, tipo, anio, carpeta)
VALUES
  ($album, $artista, 'QA FLAC continuo', 'qa-fixture-flac', 'Album', 2026, 'qa/flac'),
  ($album_senales, $artista, 'QA señales', 'qa-fixture-senales', 'Album', 2026, 'qa/senales');
INSERT INTO pistas
  (id, album_id, artista_id, titulo, artista_nombre, album_titulo, numero, disco,
   duracion_seg, ruta, tamano, estado, verificada)
VALUES
  ($id_flac1, $album, $artista, 'QA FLAC 1', 'QA', 'QA FLAC continuo', 1, 1,
   3.0, 'qa/flac/01.flac', $(stat -c %s "$QA_BASE/fixtures/flac-01.flac"), 'biblioteca', 1),
  ($id_flac2, $album, $artista, 'QA FLAC 2', 'QA', 'QA FLAC continuo', 2, 1,
   3.0, 'qa/flac/02.flac', $(stat -c %s "$QA_BASE/fixtures/flac-02.flac"), 'biblioteca', 1),
  ($id_buscar, $album_senales, $artista, 'QA búsqueda y pausa', 'QA', 'QA señales', 1, 1,
   10.0, 'qa/senales/buscar-pausa.flac', $(stat -c %s "$QA_BASE/fixtures/buscar-pausa.flac"), 'biblioteca', 1),
  ($id_eq, $album_senales, $artista, 'QA ecualizador', 'QA', 'QA señales', 2, 1,
   4.0, 'qa/senales/ecualizador.flac', $(stat -c %s "$QA_BASE/fixtures/ecualizador.flac"), 'biblioteca', 1),
  ($id_alta, $album_senales, $artista, 'QA alta', 'QA', 'QA señales', 3, 1,
   8.0, 'qa/senales/alta.flac', $(stat -c %s "$QA_BASE/fixtures/alta.flac"), 'biblioteca', 1),
  ($id_baja, $album_senales, $artista, 'QA baja', 'QA', 'QA señales', 4, 1,
   8.0, 'qa/senales/baja.flac', $(stat -c %s "$QA_BASE/fixtures/baja.flac"), 'biblioteca', 1);
SQL

  export NB_QA_DB="$db"
  export NB_QA_ID_ALTA=$id_alta
  export NB_QA_ID_BAJA=$id_baja
  export NB_QA_ALTA_FLAC="$QA_BASE/biblioteca/qa/senales/alta.flac"
  export NB_QA_BAJA_FLAC="$QA_BASE/biblioteca/qa/senales/baja.flac"
  cargo test --manifest-path "$RAIZ/src-tauri/Cargo.toml" --test qa_audio \
    prepara_la_sonoridad_de_las_pistas_sinteticas -- --ignored --nocapture --test-threads=1 \
    | tee "$QA_BASE/informes/preparacion-sonoridad.log"

  printf '%s\n' "$id_flac1" "$id_flac2" >"$QA_BASE/fixtures/ids-flac"
  printf '%s\n' "$id_buscar" >"$QA_BASE/fixtures/id-buscar-pausa"
  printf '%s\n' "$id_eq" >"$QA_BASE/fixtures/id-ecualizador"
  printf '%s\n' "$id_alta" >"$QA_BASE/fixtures/id-alta"
  printf '%s\n' "$id_baja" >"$QA_BASE/fixtures/id-baja"
}

preparar() {
  componentes
  copiar_datos
  local db
  db=$(base_de_datos)
  sqlite3 "$db" <<SQL
UPDATE preferencias SET valor = 'false'
 WHERE clave IN ('analisis_activado', 'analisis_en_segundo_plano',
                 'analizar_al_importar', 'servidor_movil_al_arrancar');
UPDATE preferencias SET valor = json_quote('$QA_BASE/biblioteca')
 WHERE clave = 'carpeta_musica';
UPDATE preferencias SET valor = json_quote('$QA_BASE/copia-seguridad')
 WHERE clave = 'copia_carpeta';
UPDATE preferencias SET valor = '{"general":false,"servicios":[]}'
 WHERE clave = 'politica_de_red';
SQL
  generar_fixtures
  insertar_fixtures
  printf 'Copia preparada en %s\n' "$QA_BASE"
}

reiniciar_sesion() {
  local db pista=$1 posicion=${2:-0} normalizar=${3:-0} preset=${4:-}
  db=$(base_de_datos)
  sqlite3 "$db" "BEGIN IMMEDIATE;
    DELETE FROM cola;
    INSERT INTO cola (posicion, pista_id) VALUES (0, $pista);
    UPDATE estado_reproductor SET pista_id = $pista, posicion_cola = 0,
      posicion_seg = $posicion, volumen = 1, aleatorio = 0,
      repeticion = 'ninguno', normalizar = $normalizar WHERE id = 1;
    UPDATE preferencias SET valor = 'true' WHERE clave = 'ecualizador_activo';
    UPDATE preferencias SET valor = '${preset:-0}' WHERE clave = 'ecualizador_preajuste';
    COMMIT;"
}

reiniciar_sesion_lista() {
  local db primera=$1 pista
  local -a pistas=("$@")
  shift
  db=$(base_de_datos)
  local sql="BEGIN IMMEDIATE; DELETE FROM cola;"
  local posicion=0
  for pista in "${pistas[@]}"; do
    sql+=" INSERT INTO cola (posicion, pista_id) VALUES ($posicion, $pista);"
    posicion=$((posicion + 1))
  done
  sql+=" UPDATE estado_reproductor SET pista_id = $primera, posicion_cola = 0,
    posicion_seg = 0, volumen = 1, aleatorio = 0, repeticion = 'ninguno',
    normalizar = 0 WHERE id = 1; COMMIT;"
  sqlite3 "$db" "$sql"
}

cargar_sumidero() {
  MODULO_RESTORE=$(pactl list short modules |
    awk '$2 == "module-stream-restore" { print $1; exit }')
  if [[ -n $MODULO_RESTORE ]]; then
    # En este PipeWire, stream-restore vuelve a enlazar cada flujo a su salida
    # anterior y hace que `move-sink-input` no tenga efecto.
    pactl unload-module "$MODULO_RESTORE"
  fi
  pactl unload-module "$MODULO_SUMIDERO" >/dev/null 2>&1 || true
  MODULO_SUMIDERO=$(pactl load-module module-null-sink \
    sink_name="$SUMIDERO" rate=48000 format=float32le channels=2)
  NODO_SUMIDERO=$(pw-cli ls Node | awk '
    /^[[:space:]]*id [0-9]+,/ { nodo = $2; sub(/,/, "", nodo) }
    /node.name = "nb_sound_qa"/ { print nodo; exit }
  ')
  if [[ -z $NODO_SUMIDERO ]]; then
    printf 'No se encontró el nodo PipeWire del sumidero\n' >&2
    return 1
  fi
  sleep 0.2
}

esperar_mpris() {
  local i
  for i in $(seq 1 120); do
    if busctl --user status "$ID_MPRIS" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
  done
  printf 'MPRIS no apareció; registro:\n' >&2
  tail -n 80 "$QA_BASE/registros/app-ultima.log" >&2 || true
  return 1
}

arrancar_app() {
  local log="$QA_BASE/registros/app-ultima.log"
  : >"$log"
  env \
    NB_SOUND_TEST_DIR="$QA_BASE" \
    PULSE_SINK="$SUMIDERO" \
    PIPEWIRE_NODE="$NODO_SUMIDERO" \
    WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:9333 \
    XDG_DATA_HOME="$QA_BASE/xdg-data" \
    XDG_CACHE_HOME="$QA_BASE/xdg-cache" \
    XDG_CONFIG_HOME="$QA_BASE/xdg-config" \
    RUST_LOG=warn \
    "$BINARIO" >"$log" 2>&1 &
  PID_APP=$!
  esperar_mpris
  esperar_salida_nula
}

esperar_salida_nula() {
  local i indice registros entrada numero destino
  indice=$(pactl list short sinks | awk -v nombre="$SUMIDERO" '$2 == nombre { print $1 }')
  if [[ -z $indice ]]; then
    printf 'No existe el sumidero %s\n' "$SUMIDERO" >&2
    return 1
  fi
  for i in $(seq 1 40); do
    registros=$(pactl list sink-inputs | awk '
      /^Sink Input #/ {
        propio = 0
        destino = ""
        numero = $0
        sub(/^Sink Input #/, "", numero)
      }
      /^[[:space:]]*Sink: / { destino = $2 }
      index($0, "application.name = \"PipeWire ALSA [nb-sound]\"") { propio = 1 }
      /^$/ {
        if (propio) print numero "|" destino
        propio = 0
      }
      END {
        if (propio) print numero "|" destino
      }
    ')
    SINK_INPUT_APP=
    while IFS='|' read -r numero destino; do
      [[ -z $numero ]] && continue
      if [[ $destino == "$indice" ]]; then
        SINK_INPUT_APP=$numero
      else
        pactl move-sink-input "$numero" "$SUMIDERO"
      fi
    done <<<"$registros"
    if [[ -n $SINK_INPUT_APP ]]; then
      return 0
    fi
    sleep 0.1
  done
  printf 'El audio de NB Sound no llegó al sumidero %s (%s)\n' "$SUMIDERO" "$indice" >&2
  pactl list sink-inputs >&2 || true
  return 1
}

cerrar_app() {
  if [[ -n ${PID_APP:-} ]] && kill -0 "$PID_APP" 2>/dev/null; then
    kill -TERM "$PID_APP" 2>/dev/null || true
    wait "$PID_APP" 2>/dev/null || true
  fi
  PID_APP=
  local i
  for i in $(seq 1 50); do
    if ! busctl --user status "$ID_MPRIS" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
  done
}

mpris() {
  busctl --user call "$ID_MPRIS" "$OBJETO_MPRIS" org.mpris.MediaPlayer2.Player "$@"
}

propiedad() {
  busctl --user get-property "$ID_MPRIS" "$OBJETO_MPRIS" \
    org.mpris.MediaPlayer2.Player "$1"
}

pista_actual() {
  propiedad Metadata |
    sed -n 's/.*mpris:trackid" o "\/org\/nbsound\/pista\/\([0-9][0-9]*\)".*/\1/p'
}

posicion_micros() {
  propiedad Position | sed -n 's/^x \([0-9][0-9]*\)$/\1/p'
}

set_position() {
  local pista=$1 segundos=$2 micros
  micros=$(awk -v s="$segundos" 'BEGIN { printf "%.0f", s * 1000000 }')
  mpris SetPosition "ox" "/org/nbsound/pista/$pista" "$micros"
}

iniciar_grabacion() {
  local salida=$1
  if [[ -z ${SINK_INPUT_APP:-} ]]; then
    printf 'No hay un flujo de NB Sound que grabar\n' >&2
    return 1
  fi
  parec --monitor-stream="$SINK_INPUT_APP" --file-format=wav --rate=48000 \
    --channels=2 --format=float32le --latency-msec=20 "$salida" &
  PID_PAREC=$!
  sleep 0.15
}

detener_grabacion() {
  if [[ -n ${PID_PAREC:-} ]] && kill -0 "$PID_PAREC" 2>/dev/null; then
    kill -INT "$PID_PAREC" 2>/dev/null || true
    wait "$PID_PAREC" 2>/dev/null || true
  fi
  PID_PAREC=
}

analizador() {
  local prueba=$1
  shift
  cargo test --manifest-path "$RAIZ/src-tauri/Cargo.toml" --test qa_audio \
    "$prueba" -- --ignored --nocapture --test-threads=1 "$@"
}

esperar_pista() {
  local esperada=$1 i actual
  for i in $(seq 1 80); do
    actual=$(pista_actual)
    if [[ $actual == "$esperada" ]]; then
      return 0
    fi
    sleep 0.1
  done
  printf 'No empezó la pista %s; quedó %s\n' "$esperada" "${actual:-ninguna}" >&2
  return 1
}

album_real() {
  local db ids=() id duracion indice siguiente manifest carpeta wav informe
  db=$(base_de_datos)
  mapfile -t ids < <(sqlite3 "$db" \
    "SELECT p.id FROM pistas p JOIN albumes a ON a.id = p.album_id
      WHERE p.estado = 'biblioteca' AND p.ruta LIKE '$MANIFIESTO_REAL%'
      ORDER BY p.disco IS NULL, p.disco, p.numero IS NULL, p.numero, p.titulo;")
  if ((${#ids[@]} < 2)); then
    printf 'El álbum MP3 de referencia no tiene dos pistas: %s\n' "$MANIFIESTO_REAL" >&2
    return 1
  fi
  reiniciar_sesion_lista "${ids[@]}"
  cargar_sumidero
  arrancar_app
  carpeta="$QA_BASE/informes/album-mp3"
  mkdir -p "$carpeta"
  find "$carpeta" -maxdepth 1 -type f -name '*.wav' -delete
  mpris Play
  esperar_pista "${ids[0]}"
  mpris Pause
  for indice in $(seq 0 $((${#ids[@]} - 2))); do
    id=${ids[$indice]}
    esperar_pista "$id"
    duracion=$(sqlite3 "$db" "SELECT duracion_seg FROM pistas WHERE id = $id;")
    mpris Pause
    sleep 0.15
    set_position "$id" "$(awk -v d="$duracion" 'BEGIN { printf "%.3f", (d > 3.5 ? d - 3.0 : 0.1) }')"
    sleep 1.5
    siguiente=${ids[$((indice + 1))]}
    wav=$(printf '%s/%02d.wav' "$carpeta" "$indice")
    mpris Play
    sleep 0.5
    iniciar_grabacion "$wav"
    esperar_pista "$siguiente"
    sleep 3
    detener_grabacion
    mpris Pause
  done
  cerrar_app
  manifest="$QA_BASE/informes/album-mp3-fuentes.txt"
  : >"$manifest"
  for id in "${ids[@]}"; do
    sqlite3 "$db" "SELECT ruta FROM pistas WHERE id = $id;" |
      sed "s#^#$QA_BASE/biblioteca/#" >>"$manifest"
  done
  unset NB_QA_WAV
  export NB_QA_WAV_DIR="$carpeta" NB_QA_FUENTES="$manifest"
  informe="$QA_BASE/informes/album-mp3.log"
  analizador un_album_no_anade_silencio_entre_pistas | tee "$informe"
}

album_flac() {
  local db ids=() id wav informe manifest
  db=$(base_de_datos)
  mapfile -t ids <"$QA_BASE/fixtures/ids-flac"
  reiniciar_sesion_lista "${ids[@]}"
  cargar_sumidero
  arrancar_app
  mpris Play
  esperar_pista "${ids[0]}"
  mpris Pause
  set_position "${ids[0]}" 2.2
  sleep 0.5
  mpris Play
  sleep 0.5
  wav="$QA_BASE/informes/album-flac.wav"
  iniciar_grabacion "$wav"
  esperar_pista "${ids[1]}"
  sleep 2.8
  detener_grabacion
  cerrar_app
  manifest="$QA_BASE/informes/album-flac-fuentes.txt"
  : >"$manifest"
  printf '%s\n' \
    "$QA_BASE/biblioteca/qa/flac/01.flac" \
    "$QA_BASE/biblioteca/qa/flac/02.flac" >"$manifest"
  unset NB_QA_WAV_DIR
  export NB_QA_WAV="$wav" NB_QA_FUENTES="$manifest"
  informe="$QA_BASE/informes/album-flac.log"
  analizador un_album_no_anade_silencio_entre_pistas | tee "$informe"
}

buscar_pausar() {
  local id wav informe posicion
  id=$(<"$QA_BASE/fixtures/id-buscar-pausa")
  reiniciar_sesion "$id" 0 0
  cargar_sumidero
  arrancar_app
  # La primera instantánea se publica antes de que exista MPRIS. Un arranque y
  # una pausa hacen que el servicio reciba los metadatos y acepte SetPosition.
  mpris Play
  esperar_pista "$id"
  mpris Pause
  sleep 0.2
  set_position "$id" 4.0
  sleep 0.25
  posicion=$(posicion_micros)
  awk -v p="$posicion" 'BEGIN { if ((p / 1000000 - 4.0) > 0.02 || (4.0 - p / 1000000) > 0.02) exit 1 }' ||
    { printf 'La búsqueda quedó en %s µs, no en 4 s\n' "$posicion" >&2; return 1; }
  wav="$QA_BASE/informes/buscar-pausar.wav"
  iniciar_grabacion "$wav"
  mpris Play
  sleep 1.8
  mpris Pause
  sleep 0.7
  mpris Play
  sleep 1.8
  detener_grabacion
  cerrar_app
  export NB_QA_WAV="$wav"
  informe="$QA_BASE/informes/buscar-pausar.log"
  analizador buscar_y_pausar_no_dejan_discontinuidades | tee "$informe"
  printf 'Posición solicitada: 4.000000 s; posición MPRIS: %.6f s\n' \
    "$(awk -v p="$posicion" 'BEGIN { print p / 1000000 }')"
}

ecualizador() {
  local id preset wav carpeta informe
  id=$(<"$QA_BASE/fixtures/id-ecualizador")
  carpeta="$QA_BASE/informes/ecualizador"
  mkdir -p "$carpeta"
  cargar_sumidero
  for preset in $(seq 0 17); do
    reiniciar_sesion "$id" 0 0 "$preset"
    arrancar_app
    wav=$(printf '%s/%02d.wav' "$carpeta" "$preset")
    iniciar_grabacion "$wav"
    mpris Play
    sleep 2.5
    mpris Pause
    sleep 0.2
    detener_grabacion
    cerrar_app
    printf 'Preselección %02d grabada\n' "$preset"
  done
  export NB_QA_EQ_DIR="$carpeta"
  informe="$QA_BASE/informes/ecualizador.log"
  analizador las_dieciocho_preselecciones_no_recortan | tee "$informe"
}

normalizacion() {
  local id_alta id_baja alta baja informe
  id_alta=$(<"$QA_BASE/fixtures/id-alta" 2>/dev/null || true)
  id_baja=$(<"$QA_BASE/fixtures/id-baja" 2>/dev/null || true)
  if [[ -z $id_alta || -z $id_baja ]]; then
    id_alta=$(sqlite3 "$(base_de_datos)" \
      "SELECT id FROM pistas WHERE ruta = 'qa/senales/alta.flac';")
    id_baja=$(sqlite3 "$(base_de_datos)" \
      "SELECT id FROM pistas WHERE ruta = 'qa/senales/baja.flac';")
  fi
  cargar_sumidero
  reiniciar_sesion "$id_alta" 1 1
  arrancar_app
  set_position "$id_alta" 1.0
  alta="$QA_BASE/informes/normalizacion-alta.wav"
  iniciar_grabacion "$alta"
  mpris Play
  sleep 6
  detener_grabacion
  cerrar_app

  reiniciar_sesion "$id_baja" 1 1
  arrancar_app
  set_position "$id_baja" 1.0
  baja="$QA_BASE/informes/normalizacion-baja.wav"
  iniciar_grabacion "$baja"
  mpris Play
  sleep 6
  detener_grabacion
  cerrar_app

  export NB_QA_ALTA_WAV="$alta" NB_QA_BAJA_WAV="$baja"
  informe="$QA_BASE/informes/normalizacion.log"
  analizador la_normalizacion_iguala_las_pistas | tee "$informe"
}

todo() {
  preparar
  album_real
  album_flac
  buscar_pausar
  ecualizador
  normalizacion
}

case ${1:-} in
  preparar) preparar ;;
  album-mp3) album_real ;;
  album-flac) album_flac ;;
  buscar-pausar) buscar_pausar ;;
  ecualizador) ecualizador ;;
  normalizacion) normalizacion ;;
  todo) todo ;;
  *) uso; exit 2 ;;
esac
