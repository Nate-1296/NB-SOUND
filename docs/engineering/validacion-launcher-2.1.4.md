# Validación de Sound 2.1.4 con Launcher

Fecha: 2026-11-13. Ejecutable publicado: `v2.1.4`, commit `fbaede2`.
Estado: publicada e instalada en Linux; recorrido completo de ambas ventanas comprobado.
La adhesión persistente nueva permanece habilitada solo en Linux.

## Código y CI

- CI `43518196348`: los siete jobs correctos con Rust 1.98. Incluida búsqueda aislada,
  668 pruebas Rust en Linux, 662 en Windows y 664 en macOS; 25 omisiones condicionadas
  en cada suite principal. Pasaron formato, Clippy estricto, 38 pruebas frontend,
  guardianes, licencias y workflows. Arranque: 249,8 KB de 250.
- La primera ejecución local de Vitest agotó la creación de tres workers; los 38 tests
  pasaron con un trabajador. No se amplió ni reintentó el límite de búsqueda de 30 ms.
- Los checkpoints iniciales detectaron una confirmación exclusiva de Linux y un alias
  sin delimitar en Clippy de Windows/macOS. Se corrigieron antes de etiquetar.
  Las plataformas sin activación nueva conservan su arranque anterior; dos regresiones
  nativas comprueban ese límite. No se publicaron esos checkpoints fallidos.

## Paquetes y catálogo

Publicación `43518959506`: Linux, Windows y macOS correctos. Los siete payloads firmados
se descargaron y verificaron con el productor de catálogo y la clave histórica de Sound,
sin rotarla. Se comprobaron versión, bytes, SHA-256, firma e inventario completo. El DMG
adicional no forma parte de esos siete payloads de actualización firmados.

[Release pública](https://github.com/Nate-1296/NB-SOUND/releases/tag/v2.1.4).
El tar Linux comprobado tiene SHA-256
`5025bb26b4054d07728e82bd7a8a113e677ee5b3e0f2f59c0306df3f0b335819`.

Catálogo editorial `43523206333`: correcto. El `nbctl` instalado verificó su firma,
caducidad y siete artefactos, descargó el catálogo público y confirmó la oferta 2.1.4
persistida. El inventario coincide con los paquetes comprobados antes de publicar.

## Recorrido nativo y almacenamiento

Con los paquetes Linux reales y XDG temporal, sin depender de las opciones de depuración,
pasaron rechazo, permiso guardado, cambios semanales/mensuales en ambos sentidos,
desconexión/reconexión recordada, reinicio de Launcher con el llavero real, revocación
activa y tras reiniciar Sound, permiso nuevo, cancelación, segunda apertura y arranque
normal desde Launcher. Tras desconectar, Sound conserva autonomía y recibe activación.
Se inspeccionaron las capturas del consentimiento y del permiso revocado.

Una prueba adicional de la integración compilada localmente mantuvo la adhesión más
allá de 960 segundos sin sondeo web; lectura y escritura posteriores confirmaron la
renovación. El recorrido del paquete distribuido fue independiente de ese ensayo.

Las pruebas de respaldo usan la implementación real: restaurar biblioteca no recupera
concesiones revocadas y otro perfil exige consentimiento. El registro propio conserva
esquema 1, la biblioteca V12 y el contrato móvil no cambia. La primera decisión
persistente del perfil retira también el puerto heredado; restaurar o permitir nuevas
solicitudes no lo reactiva.

El CLI instalado también instaló/desinstaló el tar 2.1.4 en un almacén administrado de QA,
comprobando el marcador, `fpcalc` 1.6.2 y ONNX Runtime 1.31.1/API 27 desde sus recursos.
Ese almacén se retiró y no se registró como instalación personal.

## Instalación y limpieza

Se actualizaron los binarios del sistema únicamente después de verificar los paquetes.
Los nueve archivos instalados de Sound son idénticos a su tar comprobado. Sound y
Launcher quedaron abiertos desde sus ejecutables instalados. No se autoriza una identidad
sobre la biblioteca personal durante QA ni se cambia su frecuencia de copias.

Se retiraron los perfiles de prueba, sus procesos/sockets y cinco identidades QA propias
del llavero, verificando ausencia sin obtener secretos ni tocar otras entradas. Se
eliminaron las compilaciones, dependencias y descargas regenerables ya sin uso. El
checkout de Sound quedó en aproximadamente 67 MB, con fuentes, lockfiles, vendor sellado
e historial. Se conservan los paquetes Linux y evidencia útil en el checkout de Launcher.
Los datos, música, preferencias, respaldos, agregados e instalación personal sobreviven.

La evidencia local ignorada se conserva en `target/closure-evidence` de Launcher.
No se atribuye al escritorio Windows/macOS este recorrido de ventanas: su CI nativa
comprobó el runtime/contratos ejercitados y los instaladores se compilaron, sin ejecutar
la adhesión nueva allí. La distribución firmada del propio Launcher sigue bloqueada por
la disponibilidad de Actions de su repositorio privado; su instalación Linux usa un
paquete local verificado. Su clave editorial no se reemplazó ni se usó la de Sound.
