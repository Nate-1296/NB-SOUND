# NB Sound

Aplicación de escritorio para tu música local: reproduce, cataloga, identifica, completa portadas y letras,
prepara karaoke y mezcla sesiones de DJ. Sin conexión por defecto, con todo dentro del instalador.

Hecha con Tauri 2, Svelte 5 y Rust. Lo que hace, pantalla por pantalla, está en
[NB Sound, de punta a punta](docs/contextual/la-aplicacion.md).

## Documentación

Todo lo que gobierna el proyecto está en [`docs/`](docs/README.md): la Constitución, las decisiones de
arquitectura y el plan. El contrato de trabajo está en [CLAUDE.md](CLAUDE.md).

## Desarrollo

```bash
pnpm install
pnpm binarios       # fpcalc y ONNX Runtime con su huella fijada (una vez)
pnpm tauri dev      # la aplicación en modo de desarrollo
pnpm verify         # todas las comprobaciones
```

Requisitos: Node ≥ 22, pnpm ≥ 10 y Rust 1.98 o posterior. En Linux, las bibliotecas de desarrollo de WebKitGTK
4.1 que pide Tauri.

`pnpm verify` incluye el presupuesto de búsqueda sobre 100.000 pistas, ejecutado aislado
de los ensayos de DSP. También puede ejecutarse con `pnpm test:rendimiento`; mantiene el
límite de 30 ms. `cargo test` lo enumera como ignorado para no mezclar esa medición con
trabajo intensivo; la CI lo ejecuta obligatoriamente en un paso separado.

## Licencia

GPL-3.0-or-later. Ver [LICENSE](LICENSE) y [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
