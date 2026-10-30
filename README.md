# NB Sound

Aplicación de escritorio para tu música local: reproduce, cataloga, identifica, completa portadas y letras,
prepara karaoke y mezcla sesiones de DJ. Sin conexión por defecto, con todo dentro del instalador.

> **Estado:** en reconstrucción. La **V2** (Tauri 2 + Svelte 5 + Rust) se construye en la raíz siguiendo el
> [plan de ejecución](docs/plan/README.md). La **V1** está congelada en la etiqueta `v1.1.16` y su código vive en
> [`legado/`](legado/README.md) solo como referencia.

## Documentación

Todo lo que gobierna el proyecto está en [`docs/`](docs/README.md): la Constitución, las decisiones de
arquitectura, el plan y el inventario de lo que hacía la V1. El contrato de trabajo está en [CLAUDE.md](CLAUDE.md).

## Desarrollo

```bash
pnpm install
pnpm binarios       # fpcalc y ONNX Runtime con su huella fijada (una vez)
pnpm tauri dev      # la aplicación en modo de desarrollo
pnpm verify         # todas las comprobaciones
```

Requisitos: Node ≥ 22, pnpm ≥ 10 y Rust 1.98 o posterior. En Linux, las bibliotecas de desarrollo de WebKitGTK
4.1 que pide Tauri.

## Licencia

GPL-3.0-or-later. Ver [LICENSE](LICENSE) y [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
