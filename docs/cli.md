# CLI — El cerebro de NB SOUND

El CLI es el motor principal del proyecto. Procesa archivos de audio desde una carpeta de entrada y los cataloga en una biblioteca organizada.

```bash
python main.py [opciones]
```

---

## Ejecución básica

Con las rutas configuradas en `.env`:

```bash
python main.py
```

Con rutas por argumento (sobrescriben las del `.env`):

```bash
python main.py \
  --input /ruta/entrada \
  --library /ruta/biblioteca \
  --quarantine /ruta/cuarentena \
  --review /ruta/revision \
  --logs /ruta/logs \
  --processed /ruta/procesados
```

---

## Opciones de rutas

| Opción | Descripción |
|---|---|
| `--input`, `-i` | Carpeta de entrada con archivos a catalogar |
| `--library`, `-l` | Biblioteca de destino |
| `--quarantine`, `-q` | Carpeta de cuarentena |
| `--review` | Carpeta de revisión manual |
| `--logs` | Carpeta de logs y reportes |
| `--processed` | Archivos originales archivados |
| `--cache` | Caché de consultas externas |
| `--temp` | Archivos temporales |

---

## Opciones generales

| Opción | Qué hace |
|---|---|
| `--dry-run` | Analiza y decide sin escribir ni mover nada. Ideal para revisar qué pasaría antes de tocarlo. |
| `--clear-cache` | Limpia entradas expiradas de caché antes de ejecutar |
| `--no-hotkeys` | Desactiva las teclas `p` (pausar) y `c` (cancelar) |
| `--version` | Muestra la versión |
| `--help` | Muestra la ayuda completa |

**Atajos durante la ejecución:**

- `p` — pausar/reanudar
- `c` — cancelar e iniciar rollback controlado

---

## Modos especiales de pipeline

| Opción | Qué hace |
|---|---|
| `--assets-only` | Solo descarga assets (portadas, imágenes) sobre biblioteca existente |
| `--metadata-only` | Solo identificación y tags, sin descargar assets |
| `--rebuild-manifests` | Regenera todos los manifiestos canónicos |
| `--review-only` | Reprocesa los casos en revisión |
| `--duplicates-only` | Solo verifica duplicados, sin ingestar nuevos archivos |
| `--missing-assets-only` | Reintenta assets que fallaron |
| `--audit` | Audita consistencia entre biblioteca, manifiestos y assets |
| `--repair` | Aplica reparaciones seguras tras una auditoría |
| `--explain TARGET` | Explica la decisión tomada sobre una pista concreta |
| `--discography-organize` | Reorganiza biblioteca según discografía oficial (conservador) |

---

## Recuperación post-importación

Para completar lo que no se pudo hacer durante la importación principal:

```bash
python main.py --import-recovery-status       # Estado general de recuperación
python main.py --assets-retry-missing         # Reintenta todos los assets faltantes
python main.py --assets-retry-covers-only     # Solo portadas de álbum/pista
python main.py --assets-retry-artists-only    # Solo imágenes de artistas
python main.py --enrichment-retry-missing     # Reintenta enrichment pendiente
python main.py --lyrics-retry-missing         # Solo letras faltantes
python main.py --audio-features-retry-failed  # Features de audio fallidas
```

---

## Audio Features básico

```bash
python main.py --audio-features-status      # Estado actual del análisis
python main.py --audio-features-analyze     # Analiza pistas pendientes
python main.py --audio-features-reanalyze   # Fuerza reanálisis completo
python main.py --audio-features-analyze --all  # Todas las pistas de la biblioteca
```

---

## Audio Intelligence profunda

Para equipos con Essentia/TensorFlow configurado:

```bash
python main.py --audio-intelligence-deep                  # Inicia análisis profundo
python main.py --audio-intelligence-deep-status           # Estado del background deep
python main.py --audio-intelligence-deep-resume           # Reanuda jobs pendientes
python main.py --audio-intelligence-deep-pause            # Pausa el procesamiento
python main.py --audio-intelligence-deep-cancel-keep      # Cancela, conserva avances
python main.py --audio-intelligence-deep-cancel-discard   # Cancela, descarta avances
python main.py --audio-intelligence-deep-retry-failed     # Reintenta jobs fallidos
```

El análisis profundo es reanudable: si cierras la terminal o el proceso se interrumpe, puedes retomar con `--audio-intelligence-deep-resume`.

---

## Music Discovery (búsqueda natural)

```bash
python main.py --music-discovery "algo alegre para caminar" --limit 20
python main.py --music-discovery "rock tranquilo de noche"
python main.py --music-discovery "canciones tristes pero no lentas" --limit 10
```

Los resultados se muestran en terminal. La misma capacidad está disponible en la UI como "Háblale a tu biblioteca".

---

## Cómo decide el sistema

Cada archivo pasa por un proceso de identificación y scoring. El resultado es uno de estos estados:

| Estado | Significado |
|---|---|
| `aceptado` | Escrito y movido a biblioteca automáticamente |
| `aceptado_provisional` | Aceptado con trazabilidad especial por confianza media-alta |
| `revision` | Hay candidatos, pero la confianza no alcanza para automatizar |
| `cuarentena` | Falta evidencia crítica o hay problemas técnicos |
| `duplicado_exacto` | Mismo hash SHA256 ya conocido en la biblioteca |
| `duplicado_semantico` | Misma grabación probable por ISRC/recording ID |
| `omitido` | No corresponde procesarlo en ese modo |
| `error` | Error inesperado controlado y registrado |

**Umbrales de scoring:**

- Score ≥ 0.82 → aceptado automáticamente
- Score ≥ 0.55 → revisión manual
- Score < 0.55 → cuarentena

---

## Formatos soportados

**Entrada:** `.mp3`, `.flac`, `.m4a`, `.wav`, `.ogg`, `.aac`

**Salida:** `.mp3` (los demás formatos se convierten con FFmpeg)

---

← [Volver al README](../README.md)
