# Plan de ejecución de la V2

> **Estado:** Vigente desde el 2026-10-29.
> Describe **en qué orden se construye NB Sound V2, con qué criterio se da algo por terminado y por qué ese orden**.
> Las decisiones que lo sostienen están en los [ADR](../adr/README.md); las reglas que no se negocian, en la
> [Constitución](../contextual/constitution/README.md).

## Fases

| Orden | Fase | Objetivo | Documento |
|---|---|---|---|
| 1.º | 0 | Fundaciones y prototipos que deciden | [fase-0-fundaciones.md](./fase-0-fundaciones.md) |
| 2.º | 1 | Datos: esquema V2 e importación de la V1 sin pérdida | [fase-1-datos.md](./fase-1-datos.md) |
| 3.º | 2 | Escuchar: reproductor, biblioteca y la carcasa completa | [fase-2-escuchar.md](./fase-2-escuchar.md) |
| 4.º | 3 | El móvil sigue funcionando: servidor compatible | [fase-3-movil.md](./fase-3-movil.md) |
| 5.º | 4 | Importar y catalogar sin vista de importación | [fase-4-catalogar.md](./fase-4-catalogar.md) |
| 6.º | 5 | Agregados: karaoke y análisis musical | [fase-5-agregados.md](./fase-5-agregados.md) |
| 7.º | 6 | DJ Privado y A ciegas | [fase-6-dj.md](./fase-6-dj.md) |
| 8.º | 7 | Retiro de la V1 y publicación de la 2.0 | [fase-7-retiro.md](./fase-7-retiro.md) |
| 9.º | 8 | Capacidades nuevas | [fase-8-nuevas.md](./fase-8-nuevas.md) |

**Por qué este orden.** Lo irreversible va primero (licencia, datos, contratos). Después, lo que hace que la V2 se
pueda usar a diario: escuchar (Fase 2) y que el móvil no note el cambio (Fase 3). Al terminar la Fase 3, la V2 ya
puede sustituir a la V1 para escuchar y sincronizar, aunque la importación siga en la V1. La catalogación (Fase 4)
es lo más grande de portar y no bloquea escuchar. Los agregados (Fase 5) dependen del motor y de los datos. El DJ
(Fase 6) depende de todo lo anterior. **Nada nuevo entra antes de la paridad** (Fase 8).

---

## 1. Principios

1. **Nada se construye sobre una decisión no tomada.** Si una iteración depende de algo no decidido, se registra
   en [preguntas abiertas](../contextual/open-questions/README.md) y no se empieza.
2. **Cada iteración termina con algo verificable**, preferiblemente automático.
3. **La V1 es la especificación.** Su comportamiento se porta medido contra ella: respuestas doradas, pruebas
   traducidas y comparación sobre el corpus real. Lo que se rediseña a propósito está en el
   [inventario](../contextual/inventario-v1.md) con su motivo.
4. **Ninguna iteración deja `main` en rojo.**
5. **La documentación es parte de terminar.**

## 2. Nomenclatura

`F<fase>.<subfase>.<iteración>`, por ejemplo `F0.4.1`. El identificador es estable y se cita en los commits.

## 3. Anatomía de una iteración

| Campo | Significado |
|---|---|
| **Objetivo** | Qué capacidad añade, en una frase |
| **Criterio de aceptación** | Cómo se comprueba, de forma objetiva |
| **Depende de** | Iteraciones que deben estar hechas antes |

## 4. Estados

`Pendiente`, `En curso`, `Bloqueada` (con motivo), `Parcial` (con lo que falta), `Hecha`. El estado vive **solo**
en la tabla de cada documento de fase.

## 5. Definición de terminado

Una iteración está terminada cuando:

1. Cumple su criterio de aceptación.
2. Pasa la verificación completa: `pnpm verify`, `cargo fmt --check`, `cargo clippy --all-targets --all-features
   -- -D warnings` y `cargo test`.
3. Tiene pruebas de la lógica añadida y una de regresión por cada defecto corregido.
4. Su documento en `docs/` está al día, en el mismo commit.
5. El commit sigue Conventional Commits, va firmado (`-s`) y cita su identificador.

### 5.1 La puerta de empaquetado

**Ninguna fase se cierra sin comprobar que la aplicación se empaqueta e instala.** Se cruza al final de cada fase:

1. El empaquetado produce los instaladores (Linux siempre; Windows y macOS cuando haya CI o máquina, y si no, se
   dice explícitamente qué quedó sin comprobar).
2. Todo viaja dentro: motor, decodificadores, `ffmpeg`, la huella acústica, ONNX Runtime, fuentes e iconos.
3. Instala y arranca en una **máquina limpia** sin instalar nada más (en Linux, un contenedor o una máquina virtual
   sin VLC, sin Python y sin `ffmpeg`).
4. Desinstalar no se lleva la biblioteca del usuario.

Es exactamente lo que la V1 incumplía, y es la [regla 1](../contextual/constitution/README.md) de la Constitución.

## 6. Los dos corpus

| Corpus | Dónde | Qué tiene |
|---|---|---|
| Música | `/home/nathan/Música/biblioteca/` | 2.397 MP3, 14 GB, organizados por la V1 |
| Base de la V1 | `/home/nathan/.local/share/nb_sound/biblioteca/nb_sound.sqlite3` | 464 MB; 407 pistas con análisis profundo, 323 trabajos de karaoke, 12 dispositivos |

**Jamás se escribe en esas rutas** durante el desarrollo; se abren en solo lectura. Las pruebas que las usan se
saltan solas si no existen. Nada derivado de ellas (títulos, rutas, portadas) entra al repositorio ni a los
registros. El simulador que las sustituye en `pnpm verify` conserva la variedad: títulos, duraciones, portadas y
formatos distintos, y un modo de 100.000 pistas para medir rendimiento.
