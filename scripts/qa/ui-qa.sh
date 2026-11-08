#!/usr/bin/env bash
# Pruebas finales de interfaz sobre KWin virtual, una copia de los datos y el
# inspector remoto de WebKit. No hay interacción de una persona ni audio físico.

set -euo pipefail

RAIZ=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
QA_BASE=${NB_QA_ROOT:-"$HOME/.cache/nb-sound-qa/pruebas-finales"}
DB="$QA_BASE/datos/nb-sound.sqlite"
BINARIO=${NB_QA_BINARIO_UI:-"$RAIZ/src-tauri/target/release/nb-sound"}
RUNTIME="$QA_BASE/ui-runtime"
WAYLAND_SOCKET="$RUNTIME/wayland-nbqa-ui"
SUMIDERO=nb_sound_qa_ui
MODULO_SUMIDERO=
MODULO_RESTORE=
PID_KWIN=
PID_APP=
PID_CAPTURA=
LISTA_DISPLAY=
X_ANTES=

if [[ ${NB_QA_EN_SCOPE:-0} != 1 ]]; then
  exec systemd-run --user --scope -p MemoryMax=6G -- \
    env NB_QA_EN_SCOPE=1 "$0" "$@"
fi

uso() {
  printf '%s\n' \
    'Uso: scripts/qa/ui-qa.sh preparar|iniciar|inicio|temas|biblioteca|movil|fallo-apariencia|detener|todo'
}

limpiar() {
  if [[ -n ${PID_CAPTURA:-} ]] && kill -0 "$PID_CAPTURA" 2>/dev/null; then
    kill -TERM "$PID_CAPTURA" 2>/dev/null || true
    wait "$PID_CAPTURA" 2>/dev/null || true
  fi
  if [[ -n ${PID_APP:-} ]] && kill -0 "$PID_APP" 2>/dev/null; then
    kill -TERM "$PID_APP" 2>/dev/null || true
    wait "$PID_APP" 2>/dev/null || true
  fi
  if [[ -n ${PID_KWIN:-} ]] && kill -0 "$PID_KWIN" 2>/dev/null; then
    kill -TERM "$PID_KWIN" 2>/dev/null || true
    wait "$PID_KWIN" 2>/dev/null || true
  fi
  if [[ -n ${MODULO_SUMIDERO:-} ]]; then
    pactl unload-module "$MODULO_SUMIDERO" >/dev/null 2>&1 || true
  fi
  if [[ -n ${MODULO_RESTORE:-} ]]; then
    pactl load-module module-stream-restore >/dev/null 2>&1 || true
  fi
}
trap limpiar EXIT INT TERM

preparar() {
  NB_QA_EN_SCOPE=1 "$RAIZ/scripts/qa/audio-qa.sh" preparar
  # La ruta recordada es del webview, no de la base: sin esto una corrida
  # empieza donde terminó la anterior y deja de probar Inicio.
  rm -f "$QA_BASE/xdg-data/org.nbsound.desktop/localstorage/tauri_localhost_0.localstorage"*
  sqlite3 "$DB" <<'SQL'
UPDATE preferencias SET valor = 'false'
 WHERE clave IN ('analisis_activado', 'analisis_en_segundo_plano',
                 'analizar_al_importar', 'servidor_movil_al_arrancar');
UPDATE preferencias SET valor = '"negro_puro"' WHERE clave = 'tema';
UPDATE preferencias SET valor = '"Inter"' WHERE clave = 'tipografia';
UPDATE preferencias SET valor = '100' WHERE clave = 'escala';
UPDATE preferencias SET valor = '"Nate"' WHERE clave = 'nombre_usuario';
UPDATE estado_reproductor SET volumen = 1, normalizar = 0, aleatorio = 0,
  repeticion = 'ninguno', posicion_seg = 0 WHERE id = 1;
DELETE FROM playlists WHERE nombre LIKE 'QA IA%';
SQL
  printf 'Copia de interfaz preparada en %s\n' "$QA_BASE"
}

preparar_sonoridad() {
  sqlite3 "$DB" <<'SQL'
DELETE FROM sonoridad WHERE pista_id IN (
  SELECT id FROM pistas WHERE estado = 'biblioteca' AND ruta LIKE '%.mp3'
  ORDER BY id LIMIT 100
);
UPDATE estado_reproductor SET normalizar = 0, volumen = 1, aleatorio = 0,
  repeticion = 'ninguno', posicion_seg = 0 WHERE id = 1;
SQL
}

preparar_fallo_apariencia() {
  preparar
  # La versión de esquema queda al día, pero la lectura de preferencias falla.
  sqlite3 "$DB" 'DROP TABLE preferencias;'
}

iniciar_sumidero() {
  MODULO_RESTORE=$(pactl list short modules |
    awk '$2 == "module-stream-restore" { print $1 }')
  if [[ -n $MODULO_RESTORE ]]; then
    pactl unload-module "$MODULO_RESTORE"
  fi
  MODULO_SUMIDERO=$(pactl load-module module-null-sink \
    sink_name="$SUMIDERO" rate=48000 format=float32le channels=2)
  NODO_SUMIDERO=$(pw-cli ls Node | awk '
    /^[[:space:]]*id [0-9]+,/ { nodo = $2; sub(/,/, "", nodo) }
    /node.name = "nb_sound_qa_ui"/ { print nodo }
  ')
  export NODO_SUMIDERO
}

iniciar_kwin() {
  mkdir -p "$RUNTIME"
  chmod 700 "$RUNTIME"
  X_ANTES=$(find /tmp/.X11-unix -maxdepth 1 -type s -name 'X*' -printf '%f\n' |
    sort | tr '\n' ' ')
  env XDG_RUNTIME_DIR="$RUNTIME" kwin_wayland \
    --socket wayland-nbqa-ui --virtual --width 1280 --height 800 \
    --xwayland --no-lockscreen --no-global-shortcuts \
    >"$QA_BASE/registros/kwin-qa.log" 2>&1 &
  PID_KWIN=$!
  local i
  for i in $(seq 1 100); do
    if [[ -S $WAYLAND_SOCKET ]]; then
      break
    fi
    sleep 0.1
  done
  if [[ ! -S $WAYLAND_SOCKET ]]; then
    printf 'KWin virtual no creó el socket Wayland\n' >&2
    tail -n 80 "$QA_BASE/registros/kwin-qa.log" >&2 || true
    return 1
  fi
  for i in $(seq 1 100); do
    local nuevos nuevo
    nuevos=$(find /tmp/.X11-unix -maxdepth 1 -type s -name 'X*' -printf '%f\n' |
      sort)
    for nuevo in $nuevos; do
      if [[ " $X_ANTES " != *" $nuevo "* ]]; then
        LISTA_DISPLAY=":${nuevo#X}"
        break
      fi
    done
    if [[ -n $LISTA_DISPLAY ]]; then
      break
    fi
    sleep 0.1
  done
  if [[ -z $LISTA_DISPLAY ]]; then
    printf 'KWin virtual no arrancó Xwayland\n' >&2
    return 1
  fi
  export LISTA_DISPLAY
}

esperar_inspector() {
  local i
  for i in $(seq 1 120); do
    if curl -fsS http://127.0.0.1:9333/ 2>/dev/null | rg -q 'socket/'; then
      return 0
    fi
    sleep 0.1
  done
  printf 'El inspector de WebKit no apareció\n' >&2
  return 1
}

arrancar_app() {
  local registro="$QA_BASE/registros/app-ui.log"
  : >"$registro"
  env \
    WAYLAND_DISPLAY="$WAYLAND_SOCKET" \
    DISPLAY="$LISTA_DISPLAY" \
    GDK_BACKEND=x11 \
    NB_SOUND_TEST_DIR="$QA_BASE" \
    PULSE_SINK="$SUMIDERO" \
    PIPEWIRE_NODE="$NODO_SUMIDERO" \
    WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:9333 \
    XDG_DATA_HOME="$QA_BASE/xdg-data" \
    XDG_CACHE_HOME="$QA_BASE/xdg-cache" \
    XDG_CONFIG_HOME="$QA_BASE/xdg-config" \
    RUST_LOG=warn \
    "$BINARIO" >"$registro" 2>&1 &
  PID_APP=$!
  export PID_APP
  esperar_inspector
}

iniciar_entorno() {
  iniciar_sumidero
  iniciar_kwin
  arrancar_app
}

cerrar_app() {
  if [[ -n ${PID_APP:-} ]] && kill -0 "$PID_APP" 2>/dev/null; then
    kill -TERM "$PID_APP" 2>/dev/null || true
    wait "$PID_APP" 2>/dev/null || true
  fi
  PID_APP=
}

capturar_primer_fotograma() {
  local carpeta="$QA_BASE/capturas/arranque"
  mkdir -p "$carpeta"
  find "$carpeta" -maxdepth 1 -type f -name '*.png' -delete
  (
    for _ in $(seq 1 600); do
      ventana=$(DISPLAY="$LISTA_DISPLAY" xdotool search --onlyvisible --name '^NB Sound$' 2>/dev/null |
        head -n 1 || true)
      if [[ -n $ventana ]]; then
        for marco in $(seq -w 1 12); do
          DISPLAY="$LISTA_DISPLAY" import -window "$ventana" "$carpeta/$marco.png" \
            >/dev/null 2>&1 || true
          sleep 0.025
        done
        exit 0
      fi
      sleep 0.01
    done
    exit 1
  ) &
  PID_CAPTURA=$!
  arrancar_app
  wait "$PID_CAPTURA"
  PID_CAPTURA=
  DISPLAY="$LISTA_DISPLAY" import -window \
    "$(DISPLAY="$LISTA_DISPLAY" xdotool search --onlyvisible --name '^NB Sound$' 2>/dev/null |
      head -n 1)" \
    "$carpeta/estable.png"
  local muestras=()
  local archivo color promedio
  for archivo in "$carpeta"/*.png; do
    color=$(magick "$archivo" -format '%[pixel:p{10,200}]' info:)
    promedio=$(magick "$archivo" -crop 140x600+5+80 +repage \
      -format '%[fx:round(mean.r*255)],%[fx:round(mean.g*255)],%[fx:round(mean.b*255)]' info:)
    muestras+=("$(basename "$archivo"):${color}:${promedio}")
  done
  local fabrica=0
  for archivo in "${muestras[@]}"; do
    if [[ $archivo == *"gray(0)"* || $archivo == *"srgb(0,0,0)"* ]]; then
      fabrica=$((fabrica + 1))
    fi
  done
  printf 'CAPTURAS_ARRANQUE %s\n' "$(printf '%s\n' "${muestras[@]}" | paste -sd ';' -)"
  if ((fabrica > 0)); then
    printf 'El tema de fábrica apareció en %d capturas\n' "$fabrica" >&2
    return 1
  fi
}

comprobar_ventana_con_apariencia_fallida() {
  local inicio fin ventana=
  inicio=$(date +%s%3N)
  for _ in $(seq 1 200); do
    ventana=$(DISPLAY="$LISTA_DISPLAY" xdotool search --onlyvisible --name '^NB Sound$' 2>/dev/null |
      head -n 1 || true)
    if [[ -n $ventana ]]; then
      break
    fi
    sleep 0.025
  done
  fin=$(date +%s%3N)
  if [[ -z $ventana ]]; then
    printf 'VENTANAS_X11 %s\n' \
      "$(DISPLAY="$LISTA_DISPLAY" xdotool search --name '.*' getwindowname %@ 2>/dev/null | paste -sd ';' - || true)"
    printf 'La ventana no apareció con la carga de apariencia rechazada\n' >&2
    return 1
  fi
  printf 'VENTANA_CON_APARIENCIA_FALLIDA ventana=%s aparicionMs=%s\n' \
    "$ventana" "$((fin - inicio))"
}

escenario() {
  local nombre=$1
  env NB_QA_DB="$DB" NB_QA_APP_PID="$PID_APP" \
    NB_QA_RAIZ="$RAIZ" \
    NB_QA_INFORMES="$QA_BASE/informes" \
    NB_QA_CERT_PATH="$QA_BASE/datos/movil/sync_cert.pem" \
    DISPLAY="$LISTA_DISPLAY" \
    node "$RAIZ/scripts/qa/ui-qa.mjs" "$nombre"
}

escenario_movil() {
  env NB_QA_DB="$DB" NB_QA_APP_PID="$PID_APP" \
    NB_QA_RAIZ="$RAIZ" \
    NB_QA_INFORMES="$QA_BASE/informes" \
    NB_QA_CERT_PATH="$QA_BASE/datos/movil/sync_cert.pem" \
    DISPLAY="$LISTA_DISPLAY" \
    nice -n 10 node "$RAIZ/scripts/qa/mobile-qa.mjs"
}

todo() {
  preparar
  iniciar_entorno
  escenario inicio
  escenario temas
  escenario preparar-arranque
  cerrar_app
  capturar_primer_fotograma
  escenario verificar-arranque
  escenario biblioteca
  escenario playlists
  escenario reproduccion
  escenario mpris
  escenario atajos
  escenario perfil
  cerrar_app
  preparar_sonoridad
  arrancar_app
  escenario sonoridad
  escenario normalizacion
  cerrar_app
  preparar
  arrancar_app
  escenario_movil
}

case ${1:-} in
  preparar) preparar ;;
  iniciar) iniciar_entorno ;;
  inicio|temas|biblioteca|playlists|reproduccion|mpris|atajos|perfil) iniciar_entorno; escenario "$1" ;;
  movil)
    preparar
    iniciar_entorno
    escenario_movil
    ;;
  fallo-apariencia)
    preparar_fallo_apariencia
    iniciar_entorno
    comprobar_ventana_con_apariencia_fallida
    ;;
  sonoridad) preparar; preparar_sonoridad; iniciar_entorno; escenario sonoridad ;;
  normalizacion) preparar; iniciar_entorno; escenario normalizacion ;;
  arranque)
    preparar
    iniciar_sumidero
    iniciar_kwin
    arrancar_app
    escenario preparar-arranque
    cerrar_app
    capturar_primer_fotograma
    escenario verificar-arranque
    ;;
  detener) limpiar ;;
  todo) todo ;;
  *) uso; exit 2 ;;
esac
