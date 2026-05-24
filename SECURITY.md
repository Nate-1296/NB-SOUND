# Política de seguridad

NB SOUND es una aplicación de escritorio local-first: no corre servidores ni
sincroniza datos a la nube. La superficie de ataque relevante proviene de:

- Manejo de archivos de audio y metadata (tags ID3, paths, portadas).
- Llamadas a APIs externas (MusicBrainz, AcoustID, Shazam, iTunes, Cover Art
  Archive, proveedores de IA opcionales).
- Dependencias nativas: FFmpeg, VLC (libVLC), Chromaprint (`fpcalc`), PyTorch,
  Demucs y Essentia/TensorFlow (opcional).
- Persistencia local: SQLite, archivos en el filesystem del usuario y el
  archivo `.env`.

## Versiones con soporte

Sólo la línea 1.x recibe parches de seguridad activos.

| Versión | Soporte de seguridad |
| --- | --- |
| 1.x.x | Soportada |
| < 1.0 | No soportada (pre-release) |

## Cómo reportar una vulnerabilidad

**No abras un issue público para reportar fallos de seguridad.** Usa uno de
estos canales privados:

1. **Recomendado** — GitHub Security Advisories:
   [Security → Report a vulnerability](https://github.com/Nate-1296/NB-SOUND/security/advisories/new).
   El canal es privado, queda asociado al repositorio y permite coordinar el
   fix sin exposición pública.
2. **Alternativa** — email a `digitalworldideascenter@gmail.com` con asunto
   `[SECURITY] NB SOUND`. Si vas a enviar detalles sensibles, podemos
   intercambiar claves PGP antes de cualquier contenido técnico.

En el reporte, por favor incluye:

- Versión afectada (`python main.py --version` o `python main_ui.py --version`).
- Sistema operativo, versión de Python y método de instalación.
- Descripción de la vulnerabilidad y su impacto técnico.
- Pasos para reproducir, idealmente con un *proof of concept* mínimo.
- Cualquier mitigación temporal que conozcas.

## Tiempos de respuesta

Como proyecto comunitario el equipo es pequeño. Hacemos nuestro mejor esfuerzo
para cumplir con:

| Etapa | Plazo objetivo |
| --- | --- |
| Acuse de recibo | 7 días |
| Triaje y confirmación | 14 días |
| Parche o mitigación pública | 60 días (negociable según severidad) |

Si la vulnerabilidad está siendo explotada o tiene impacto crítico, indícalo
explícitamente en el reporte para priorizar.

## Divulgación coordinada

Pedimos divulgación coordinada: no publicar detalles públicos hasta que la
release con el parche esté disponible y los usuarios tengan un margen
razonable para actualizar. Una vez liberado el parche se acreditará a quien
reportó en el [CHANGELOG](CHANGELOG.md), salvo que solicites lo contrario.

## Alcance

**En alcance:**

- Vulnerabilidades en el código fuente del repositorio.
- Configuraciones por defecto que expongan datos del usuario.
- Manejo inseguro de archivos, paths, metadata o subprocesos.
- Filtrado de claves de API a logs o reports.

**Fuera de alcance:**

- Vulnerabilidades de dependencias upstream (FFmpeg, VLC, PyTorch, Demucs,
  Essentia, etc.). Repórtalas al proyecto correspondiente. Si requieren un
  workaround en NB SOUND, abre un issue regular cuando ya estén divulgadas.
- Problemas que requieran acceso físico al equipo o privilegios root.
- Reportes generados únicamente por escáneres automáticos sin análisis
  manual ni *proof of concept*.
- Auto-DoS por sobrecargar el propio equipo del usuario (importar millones
  de archivos, modelos pesados sin GPU, etc.).

## Buenas prácticas para quien usa NB SOUND

- No commitear el archivo `.env`; ya está en `.gitignore`.
- Antes de compartir `tagger_run.log` o reports, revisar que no contengan
  claves de API ni rutas con datos personales.
- Mantener actualizados FFmpeg, VLC y Chromaprint con las versiones del
  repositorio oficial de tu sistema operativo.
- Verificar el checksum SHA256 publicado junto a cada release antes de
  ejecutar el bundle descargado.
- No descargar bundles desde mirrors no oficiales.
