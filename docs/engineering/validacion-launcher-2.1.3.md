# Validación de la integración Launcher en 2.1.3

Fecha: 2026-11-12. Estado: 2.1.3 publicada; tar Linux y recorrido administrado comprobados.

## Comprobado con la fuente del candidato 2.1.2

- `pnpm verify`: formato, tipos sin errores/advertencias, 38 pruebas frontend y guardianes
  correctos, incluidos contrato móvil, red, privacidad, puente, binarios y empaquetado web.
- `cargo fmt --all -- --check`, Clippy de todos los targets/features con `-D warnings` y
  pruebas Rust: 647 correctas y 24 omitidas por requisitos de corpus o escenarios QA.
- `pnpm tauri build --debug --no-bundle --ci`: binario nativo con frontend integrado.
- La exportación compartida coincide con la fuente canónica de Launcher:
  `dacf15206e9a6497f88609b97457740ddab72e2b3431a8d030915c6d044f56ae`.
- Recorrido real Launcher, host y Sound con datos temporales y KWin aislado: autorización,
  cambios en ambos sentidos, conflicto/validación de dominio cubiertos por pruebas y
  desconexión que conserva Sound y rechaza nuevas consultas del Launcher.
- Conexión mantenida 961 segundos desde el inicio del recorrido autorizado. Se deshabilitó
  el sondeo del frontend durante la espera; el supervisor Rust mantuvo ambos extremos.
  Después se confirmaron lecturas y cambios semanal/mensual y se revocó el acceso.
- El ensayo del módulo de instalación verifica marca/estructura, recursos relativos,
  exclusión entre proceso y gestor y rechazo de una marca inválida o ausente en un árbol
  administrado. Una pérdida de marca durante el arranque no habilita el actualizador propio.

No se modificó una biblioteca personal ni NB Sound Mobile. Los escenarios omitidos siguen
sin ejecutarse; esta iteración no los presenta como aprobados. La muestra de propagación
de 17 ms entre los dos DOM corresponde a desarrollo y no es un presupuesto de producción.

## Distribución

La CI, las firmas y el tar Linux se comprobaron antes de publicar, según la evidencia final
registrada abajo. La ejecución de la UI Windows/macOS sigue pendiente y no se deduce de
compilar sus paquetes ni de pasar sus suites.

## Corrección de la medición en 2.1.3

La CI `43211718683` pasó frontend, dependencias/licencias, Windows y macOS. Linux falló
solo en `cien_mil_pistas_se_buscan_en_menos_de_30_ms`: 32,620119 ms durante la suite paralela.
La CI anterior `43122817755`, sin esta integración, ya había fallado en la misma prueba
con 35,447493 ms. El flujo de instaladores se canceló y el borrador 2.1.2 se eliminó;
no se publicó ese candidato ni se sustituyó una instalación personal.

Se separó la medición sin modificar la búsqueda ni el límite. `cargo test` la declara
ignorada; `scripts/test-rendimiento.mjs` comprueba que exista y la ejecuta sola, una vez,
con `--ignored --exact --test-threads=1`. `pnpm verify` y cada runtime de CI la incluyen
obligatoriamente. El caso aislado pasó localmente y en cada runtime de la CI 2.1.3.
La nueva comprobación general se registra en los apartados siguientes.

## Validación local de 2.1.3

`pnpm verify`, formato, Clippy y la suite Rust pasaron con esta fuente. La suite general
ejecutó 646 pruebas y omitió 25; la medición obligatoria aislada añadió una prueba
correcta. Las otras 24 omisiones conservan sus requisitos de corpus o entorno QA.
El bundle regenerado desde Launcher es
`1829f2ce6a7c72ed407e58ae142e75556eb5e9c9c0dacfdedf340e3b475caea5`.
Su único cambio adicional normaliza el SDDL de una prueba Windows para admitir los alias
canónicos de SID sin cambiar el descriptor ni los permisos del transporte.

## Paquete y publicación comprobados

La CI `43217181437` pasó íntegra, incluidas las mediciones aisladas en Linux, Windows
y macOS. `43217183421` generó los instaladores. Launcher verificó las siete firmas
con la clave pública existente. El tar Linux tiene SHA-256
`ca6c47f41719e7d89019e0e8713d0fc5c481eee1e61026ecae402d45a72ed715`
y 30.639.817 bytes. La release se publicó a las 20:53:51 UTC del 2026-11-12:
https://github.com/Nate-1296/NB-SOUND/releases/tag/v2.1.3.

El paquete Linux real se instaló/abrió desde Launcher con datos temporales. Su recurso
confirmó lectura y cambio; los bloqueos impidieron sustituir o retirar binarios en uso.
El puente devolvió `INSTALLATION_MANAGED` al consultar el actualizador propio; se restauró
la política de red temporal. Desconectar conservó Sound. Retirar y reinstalar conservaron
la frecuencia del propietario, comprobada por consulta y sin acceder a su base.
`fpcalc` 1.6.2 ejecutó y ONNX Runtime 1.31.1 cargó desde el árbol administrado.
No se atribuye ejecución de modelos opcionales ni UI Windows/macOS a estas comprobaciones.
La descarga pública por Launcher pausó con 1.060.871 bytes y reanudó hasta verificación final.

## Catálogo editorial y corrección del ensayo de cola

El workflow editorial `43315321548` publicó el catálogo firmado de 2.1.3. Launcher
verificó sus siete artefactos por HTTPS y desde su ventana nativa, con consentimiento,
persistencia tras reiniciar y carga local sin una nueva consulta automática. El productor
renueva por 14 días; la renovación semanal está definida, aún sin acreditar su primera
activación programada. La firma de Sound solo autoriza sus propios paquetes.

La CI `43321218754` pasó Linux y Windows, pero macOS falló en el ensayo de cola:
el renderizado fuera de línea avanzaba hasta la tercera pista antes de que el vigía
asíncrono entregara la transición de la segunda. El ensayo espera ahora cada cambio
de ficha y su publicación antes de seguir renderizando. Conserva las aserciones sobre
las tres pistas visibles y el historial; no modifica el motor ni el binario distribuido.

En la continuación del 2026-11-12 pasaron `pnpm verify` (38 pruebas frontend,
guardianes y presupuesto de búsqueda aislado), formato, Clippy con todos los targets/features
y `cargo test --locked --all-features`: 640 pruebas de biblioteca correctas, siete omitidas,
más suites de integración/editorial y documentación. Las omisiones de corpus/QA conservan
sus requisitos. La medición de búsqueda había fallado durante compilaciones simultáneas
del trabajo anterior (70,45 ms); ejecutada con el equipo libre pasó sin ampliar los 30 ms.
La CI nativa de la corrección del ensayo se registra aparte al terminar.
