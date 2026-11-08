# Plan de ejecución de NB Sound

> **Estado:** Vigente desde el 2026-10-29.
> Describe **en qué orden se construye NB Sound, con qué criterio se da algo por terminado y por qué ese orden**.
> Las decisiones que lo sostienen están en los [ADR](../adr/README.md); las reglas que no se negocian, en la
> [Constitución](../contextual/constitution/README.md).

## Fases

| Orden | Fase | Objetivo | Documento |
|---|---|---|---|
| 1.º | 0 | Fundaciones y prototipos que deciden (**cerrada el 2026-10-30**) | [fase-0-fundaciones.md](./fase-0-fundaciones.md) |
| 2.º | 1 | Datos: el esquema y la búsqueda | [fase-1-datos.md](./fase-1-datos.md) |
| 3.º | 2 | Escuchar: reproductor, biblioteca y la carcasa completa | [fase-2-escuchar.md](./fase-2-escuchar.md) |
| 4.º | 3 | El teléfono: servidor compatible con NB Sound Mobile | [fase-3-movil.md](./fase-3-movil.md) |
| 5.º | 4 | Importar y catalogar sin vista de importación | [fase-4-catalogar.md](./fase-4-catalogar.md) |
| 6.º | 5 | Agregados: karaoke y análisis musical | [fase-5-agregados.md](./fase-5-agregados.md) |
| 7.º | 6 | DJ Privado y A ciegas | [fase-6-dj.md](./fase-6-dj.md) |
| 8.º | 7 | Publicación de la 2.0 | [fase-7-retiro.md](./fase-7-retiro.md) |
| 9.º | 8 | Capacidades nuevas (**cerrada el 2026-10-31**) | [fase-8-nuevas.md](./fase-8-nuevas.md) |

Lo que se hace en cada sesión, con sus commits y lo que quedó pendiente, se registra en la
[bitácora](./bitacora.md).

**Por qué este orden.** Lo irreversible va primero (licencia, datos, contratos). Después, lo que hace que NB Sound se
pueda usar a diario: escuchar (Fase 2) y el teléfono (Fase 3). La catalogación (Fase 4) es lo más grande y no bloquea
escuchar. Los agregados (Fase 5) dependen del motor y de los datos. El DJ (Fase 6) depende de todo lo anterior. Las
capacidades nuevas van al final (Fase 8).

---

## 1. Principios

1. **Nada se construye sobre una decisión no tomada.** Si una iteración depende de algo no decidido, se registra
   en [preguntas abiertas](../contextual/open-questions/README.md) y no se empieza.
2. **Cada iteración termina con algo verificable**, preferiblemente automático.
3. **Lo que tiene referencia se mide contra ella**: respuestas doradas, pruebas y comparación sobre el corpus real.
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

> **Decisión de Nathan (2026-11-08):** no se instala en máquina limpia ni se comprueban Windows y macOS (Nathan lo
> probó en Windows). Las pruebas finales son solo las que puede hacer una IA sobre la aplicación compilada y una
> copia de los datos. Los puntos 1 y 3 de abajo quedan sin efecto salvo para Linux en la CI.

> **Decisión de Nathan (2026-10-30):** las puertas de cada fase y todo lo que solo se puede comprobar a mano o en el
> entorno real **se acumulan** en [pruebas finales](./pruebas-finales.md) y se ejecutan juntas al terminar la Fase 8,
> en la máquina de Nathan. Hasta entonces, una fase se cierra con sus pruebas automáticas en verde en las tres
> plataformas del CI; lo que queda por comprobar a mano se apunta en ese documento al cerrar cada iteración.

**Ninguna versión se publica sin comprobar que la aplicación se empaqueta e instala:**

1. El empaquetado produce los instaladores (Linux siempre; Windows y macOS cuando haya CI o máquina, y si no, se
   dice explícitamente qué quedó sin comprobar).
2. Todo viaja dentro: motor, decodificadores, la huella acústica, ONNX Runtime, fuentes e iconos (`ffmpeg` no, por
   la enmienda de ADR-006).
3. Instala y arranca en una **máquina limpia** sin instalar nada más (en Linux, un contenedor o una máquina virtual
   sin VLC, sin Python y sin `ffmpeg`).
4. Desinstalar no se lleva la biblioteca del usuario.

Es la [regla 1](../contextual/constitution/README.md) de la Constitución.

## 6. Los corpus reales

Las pruebas que miden rendimiento o resultados reales usan la música de la máquina de desarrollo. Dónde está y qué
reglas la protegen está en [CLAUDE.md](../../CLAUDE.md), sección 7: **jamás se escribe en ella**, se abre en solo
lectura, nada derivado entra al repositorio ni a los registros, y las pruebas que la usan se saltan solas si no
existe. El simulador que la sustituye en `pnpm verify` conserva la variedad (títulos, duraciones, portadas y
formatos distintos) y tiene un modo de 100.000 pistas para medir rendimiento.