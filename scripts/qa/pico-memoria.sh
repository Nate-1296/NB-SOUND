#!/usr/bin/env bash
# Ejecuta una orden y devuelve el pico de memoria residente (VmHWM) de su proceso
# principal. No hay /usr/bin/time en todas las máquinas y el de bash no da el
# pico, así que se lee /proc mientras vive.
set -euo pipefail

"$@" &
pid=$!
pico=0
while kill -0 "$pid" 2>/dev/null; do
  kb=$(awk '/^VmHWM:/ { print $2 }' "/proc/$pid/status" 2>/dev/null || true)
  if [[ -n $kb && $kb -gt $pico ]]; then
    pico=$kb
  fi
  sleep 0.2
done
estado=0
wait "$pid" || estado=$?
printf 'PICO_MEMORIA_MB %d\n' $((pico / 1024))
exit "$estado"
