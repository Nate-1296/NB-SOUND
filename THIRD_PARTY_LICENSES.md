# Componentes de terceros

<!-- GENERADO AUTOMÁTICAMENTE por scripts/generate-notices.mjs. No editar a mano. -->

NB Sound se distribuye bajo GPL-3.0-or-later e incluye software de terceros. Este archivo enumera esos
componentes y sus licencias, en cumplimiento de las obligaciones de atribución de cada una.

Regenerar: `node scripts/generate-notices.mjs`

## Binarios que viajan en el instalador

| Componente | Versión | Licencia | Origen | Para qué |
|---|---|---|---|---|
| Chromaprint (`fpcalc`) | 1.6.2 | LGPL-2.1-or-later | https://github.com/acoustid/chromaprint | Huella acústica para AcoustID |
| ONNX Runtime | 1.31.1 | MIT | https://github.com/microsoft/onnxruntime | Inferencia de los agregados |
| IBM Plex Sans | 6.x | OFL-1.1 | https://github.com/IBM/plex | Tipografía de la interfaz (`static/fuentes/LICENCIAS.md`) |

Los modelos de los agregados no viajan en el instalador: cada uno muestra su licencia en Ajustes > Agregados
(ADR-010).

## Componentes de Rust (580)

| Componente | Versión | Licencia | Origen |
|---|---|---|---|
| `adler2` | 2.0.1 | 0BSD OR MIT OR Apache-2.0 | https://github.com/oyvindln/adler2 |
| `aes` | 0.9.3 | MIT OR Apache-2.0 | https://github.com/RustCrypto/block-ciphers |
| `aho-corasick` | 1.1.5 | Unlicense OR MIT | https://github.com/BurntSushi/aho-corasick |
| `alloc-no-stdlib` | 3.0.0 | BSD-3-Clause | https://github.com/dropbox/rust-alloc-no-stdlib |
| `alloc-stdlib` | 0.3.0 | BSD-3-Clause | https://github.com/dropbox/rust-alloc-no-stdlib |
| `alsa` | 0.11.0 | Apache-2.0/MIT | https://github.com/diwic/alsa-rs |
| `alsa-sys` | 0.4.0 | MIT | https://github.com/diwic/alsa-sys |
| `android_system_properties` | 0.1.6 | MIT OR Apache-2.0 | https://github.com/nical/android_system_properties |
| `anyhow` | 1.0.104 | MIT OR Apache-2.0 | https://github.com/dtolnay/anyhow |
| `apple-native-keyring-store` | 1.0.2 | MIT OR Apache-2.0 | https://github.com/open-source-cooperative/apple-native-keyring-store.git |
| `async-broadcast` | 0.7.2 | MIT OR Apache-2.0 | https://github.com/smol-rs/async-broadcast |
| `async-channel` | 2.5.0 | Apache-2.0 OR MIT | https://github.com/smol-rs/async-channel |
| `async-executor` | 1.14.0 | Apache-2.0 OR MIT | https://github.com/smol-rs/async-executor |
| `async-io` | 2.6.0 | Apache-2.0 OR MIT | https://github.com/smol-rs/async-io |
| `async-lock` | 3.4.2 | Apache-2.0 OR MIT | https://github.com/smol-rs/async-lock |
| `async-process` | 2.5.0 | Apache-2.0 OR MIT | https://github.com/smol-rs/async-process |
| `async-recursion` | 1.2.0 | MIT OR Apache-2.0 | https://github.com/dcchut/async-recursion |
| `async-signal` | 0.2.14 | Apache-2.0 OR MIT | https://github.com/smol-rs/async-signal |
| `async-task` | 4.7.1 | Apache-2.0 OR MIT | https://github.com/smol-rs/async-task |
| `async-trait` | 0.1.92 | MIT OR Apache-2.0 | https://github.com/dtolnay/async-trait |
| `atk` | 0.18.2 | MIT | https://github.com/gtk-rs/gtk3-rs |
| `atk-sys` | 0.18.2 | MIT | https://github.com/gtk-rs/gtk3-rs |
| `atomic-arena` | 0.1.2 | MIT OR Apache-2.0 | https://github.com/tesselode/atomic-arena |
| `atomic-waker` | 1.1.2 | Apache-2.0 OR MIT | https://github.com/smol-rs/atomic-waker |
| `autocfg` | 1.5.1 | Apache-2.0 OR MIT | https://github.com/cuviper/autocfg |
| `base64` | 0.21.7 | MIT OR Apache-2.0 | https://github.com/marshallpierce/rust-base64 |
| `base64` | 0.23.1 | MIT OR Apache-2.0 | https://github.com/marshallpierce/rust-base64 |
| `bit-set` | 0.8.0 | Apache-2.0 OR MIT | https://github.com/contain-rs/bit-set |
| `bit-vec` | 0.8.0 | Apache-2.0 OR MIT | https://github.com/contain-rs/bit-vec |
| `bitflags` | 1.3.2 | MIT/Apache-2.0 | https://github.com/bitflags/bitflags |
| `bitflags` | 2.13.2 | MIT OR Apache-2.0 | https://github.com/bitflags/bitflags |
| `block-buffer` | 0.10.4 | MIT OR Apache-2.0 | https://github.com/RustCrypto/utils |
| `block-buffer` | 0.12.1 | MIT OR Apache-2.0 | https://github.com/RustCrypto/utils |
| `block-padding` | 0.4.2 | MIT OR Apache-2.0 | https://github.com/RustCrypto/utils |
| `block2` | 0.6.2 | MIT | https://github.com/madsmtm/objc2 |
| `blocking` | 1.7.0 | Apache-2.0 OR MIT | https://github.com/smol-rs/blocking |
| `brotli` | 9.1.1 | BSD-3-Clause AND MIT | https://github.com/dropbox/rust-brotli |
| `brotli-decompressor` | 6.2.0 | BSD-3-Clause/MIT | https://github.com/dropbox/rust-brotli-decompressor |
| `bs58` | 0.5.1 | MIT/Apache-2.0 | https://github.com/Nullus157/bs58-rs |
| `bumpalo` | 3.20.3 | MIT OR Apache-2.0 | https://github.com/fitzgen/bumpalo |
| `bytemuck` | 1.25.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/Lokathor/bytemuck |
| `byteorder` | 1.5.0 | Unlicense OR MIT | https://github.com/BurntSushi/byteorder |
| `bytes` | 1.12.1 | MIT | https://github.com/tokio-rs/bytes |
| `cairo-rs` | 0.18.5 | MIT | https://github.com/gtk-rs/gtk-rs-core |
| `cairo-sys-rs` | 0.18.2 | MIT | https://github.com/gtk-rs/gtk-rs-core |
| `camino` | 1.2.6 | MIT OR Apache-2.0 | https://github.com/camino-rs/camino |
| `cargo_metadata` | 0.19.2 | MIT | https://github.com/oli-obk/cargo_metadata |
| `cargo_toml` | 1.0.1 | Apache-2.0 OR MIT | https://gitlab.com/lib.rs/cargo_toml |
| `cargo-platform` | 0.1.9 | MIT OR Apache-2.0 | https://github.com/rust-lang/cargo |
| `cbc` | 0.2.1 | MIT OR Apache-2.0 | https://github.com/RustCrypto/block-modes |
| `cc` | 1.10.0 | MIT OR Apache-2.0 | https://github.com/rust-lang/cc-rs |
| `cesu8` | 1.1.0 | Apache-2.0/MIT | https://github.com/emk/cesu8-rs |
| `cfb` | 0.14.0 | MIT | https://github.com/mdsteele/rust-cfb |
| `cfg-expr` | 0.15.8 | MIT OR Apache-2.0 | https://github.com/EmbarkStudios/cfg-expr |
| `cfg-if` | 1.0.5 | MIT OR Apache-2.0 | https://github.com/rust-lang/cfg-if |
| `chacha20` | 0.10.2 | MIT OR Apache-2.0 | https://github.com/RustCrypto/stream-ciphers |
| `chrono` | 0.4.45 | MIT OR Apache-2.0 | https://github.com/chronotope/chrono |
| `cipher` | 0.5.2 | MIT OR Apache-2.0 | https://github.com/RustCrypto/traits |
| `cmov` | 0.5.4 | Apache-2.0 OR MIT | https://github.com/RustCrypto/utils |
| `combine` | 4.6.9 | MIT | https://github.com/Marwes/combine |
| `concurrent-queue` | 2.5.0 | Apache-2.0 OR MIT | https://github.com/smol-rs/concurrent-queue |
| `const-oid` | 0.10.2 | Apache-2.0 OR MIT | https://github.com/RustCrypto/formats |
| `cookie` | 0.18.2 | MIT OR Apache-2.0 | https://github.com/SergioBenitez/cookie-rs |
| `core-foundation` | 0.10.1 | MIT OR Apache-2.0 | https://github.com/servo/core-foundation-rs |
| `core-foundation-sys` | 0.8.7 | MIT OR Apache-2.0 | https://github.com/servo/core-foundation-rs |
| `core-graphics` | 0.25.0 | MIT OR Apache-2.0 | https://github.com/servo/core-foundation-rs |
| `core-graphics-types` | 0.2.0 | MIT OR Apache-2.0 | https://github.com/servo/core-foundation-rs |
| `coreaudio-rs` | 0.14.2 | MIT/Apache-2.0 | https://github.com/RustAudio/coreaudio-rs.git |
| `cpal` | 0.18.2 | Apache-2.0 | https://github.com/RustAudio/cpal |
| `cpubits` | 0.1.1 | MIT OR Apache-2.0 | https://github.com/RustCrypto/utils |
| `cpufeatures` | 0.2.17 | MIT OR Apache-2.0 | https://github.com/RustCrypto/utils |
| `cpufeatures` | 0.3.1 | MIT OR Apache-2.0 | https://github.com/RustCrypto/utils |
| `crc32fast` | 1.5.3 | MIT OR Apache-2.0 | https://github.com/srijs/rust-crc32fast |
| `crossbeam-channel` | 0.5.17 | MIT OR Apache-2.0 | https://github.com/crossbeam-rs/crossbeam |
| `crossbeam-utils` | 0.8.23 | MIT OR Apache-2.0 | https://github.com/crossbeam-rs/crossbeam |
| `crypto-common` | 0.1.7 | MIT OR Apache-2.0 | https://github.com/RustCrypto/traits |
| `crypto-common` | 0.2.2 | MIT OR Apache-2.0 | https://github.com/RustCrypto/traits |
| `cssparser` | 0.37.0 | MPL-2.0 | https://github.com/servo/rust-cssparser |
| `cssparser-macros` | 0.7.1 | MPL-2.0 | https://github.com/servo/rust-cssparser |
| `ctor` | 1.0.13 | Apache-2.0 OR MIT | https://github.com/mmastrac/linktime |
| `ctutils` | 0.4.7 | Apache-2.0 OR MIT | https://github.com/RustCrypto/utils |
| `darling` | 0.24.1 | MIT | https://github.com/TedDriggs/darling |
| `darling_core` | 0.24.1 | MIT | https://github.com/TedDriggs/darling |
| `darling_macro` | 0.24.1 | MIT | https://github.com/TedDriggs/darling |
| `dasp_frame` | 0.11.0 | MIT OR Apache-2.0 | https://github.com/rustaudio/dasp.git |
| `dasp_sample` | 0.11.0 | MIT OR Apache-2.0 | https://github.com/rustaudio/sample.git |
| `dbus` | 0.9.12 | Apache-2.0/MIT | https://github.com/diwic/dbus-rs |
| `defmt` | 1.2.0 | MIT OR Apache-2.0 | https://github.com/knurling-rs/defmt |
| `defmt-macros` | 1.2.0 | MIT OR Apache-2.0 | https://github.com/knurling-rs/defmt |
| `defmt-parser` | 1.1.0 | MIT OR Apache-2.0 | https://github.com/knurling-rs/defmt |
| `deranged` | 0.5.9 | MIT OR Apache-2.0 | https://github.com/jhpratt/deranged |
| `derive_more` | 2.1.1 | MIT | https://github.com/JelteF/derive_more |
| `derive_more-impl` | 2.1.1 | MIT | https://github.com/JelteF/derive_more |
| `digest` | 0.10.7 | MIT OR Apache-2.0 | https://github.com/RustCrypto/traits |
| `digest` | 0.11.3 | MIT OR Apache-2.0 | https://github.com/RustCrypto/traits |
| `dirs` | 7.0.0 | MIT OR Apache-2.0 | https://codeberg.org/dirs/dirs-rs |
| `dirs-sys` | 0.5.0 | MIT OR Apache-2.0 | https://github.com/dirs-dev/dirs-sys-rs |
| `dispatch2` | 0.3.1 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `displaydoc` | 0.2.7 | MIT OR Apache-2.0 | https://github.com/yaahc/displaydoc |
| `dlopen2` | 0.8.2 | MIT | https://github.com/OpenByteDev/dlopen2 |
| `dlopen2_derive` | 0.4.3 | MIT | https://github.com/OpenByteDev/dlopen2 |
| `dom_query` | 0.28.0 | MIT | https://github.com/niklak/dom_query |
| `dpi` | 0.1.2 | Apache-2.0 AND MIT | https://github.com/rust-windowing/winit |
| `dtoa` | 1.0.11 | MIT OR Apache-2.0 | https://github.com/dtolnay/dtoa |
| `dtoa-short` | 0.3.5 | MPL-2.0 | https://github.com/upsuper/dtoa-short |
| `dunce` | 1.0.5 | CC0-1.0 OR MIT-0 OR Apache-2.0 | https://gitlab.com/kornelski/dunce |
| `dyn-clone` | 1.0.20 | MIT OR Apache-2.0 | https://github.com/dtolnay/dyn-clone |
| `ebur128` | 0.1.11 | MIT | https://github.com/sdroege/ebur128 |
| `embed_plist` | 1.2.2 | MIT OR Apache-2.0 | https://github.com/nvzqz/embed-plist-rs |
| `embed-resource` | 3.0.12 | MIT | https://github.com/nabijaczleweli/rust-embed-resource |
| `endi` | 1.1.1 | MIT | https://github.com/zeenix/endi |
| `enumflags2` | 0.7.12 | MIT OR Apache-2.0 | https://github.com/meithecatte/enumflags2 |
| `enumflags2_derive` | 0.7.12 | MIT OR Apache-2.0 | https://github.com/meithecatte/enumflags2 |
| `equivalent` | 1.0.3 | Apache-2.0 OR MIT | https://github.com/indexmap-rs/equivalent |
| `erased-serde` | 0.4.11 | MIT OR Apache-2.0 | https://github.com/dtolnay/erased-serde |
| `errno` | 0.3.14 | MIT OR Apache-2.0 | https://github.com/lambda-fairy/rust-errno |
| `event-listener` | 5.4.2 | Apache-2.0 OR MIT | https://github.com/smol-rs/event-listener |
| `event-listener-strategy` | 0.5.4 | Apache-2.0 OR MIT | https://github.com/smol-rs/event-listener-strategy |
| `extended` | 0.1.0 | MIT | https://github.com/depp/extended-rs |
| `fallible-iterator` | 0.3.0 | MIT/Apache-2.0 | https://github.com/sfackler/rust-fallible-iterator |
| `fallible-streaming-iterator` | 0.1.9 | MIT/Apache-2.0 | https://github.com/sfackler/fallible-streaming-iterator |
| `fastrand` | 2.5.0 | Apache-2.0 OR MIT | https://github.com/smol-rs/fastrand |
| `fdeflate` | 0.3.7 | MIT OR Apache-2.0 | https://github.com/image-rs/fdeflate |
| `field-offset` | 0.3.6 | MIT OR Apache-2.0 | https://github.com/Diggsey/rust-field-offset |
| `find-msvc-tools` | 0.1.15 | MIT OR Apache-2.0 | https://github.com/rust-lang/cc-rs |
| `flate2` | 1.1.10 | MIT OR Apache-2.0 | https://github.com/rust-lang/flate2-rs |
| `fnv` | 1.0.7 | Apache-2.0 / MIT | https://github.com/servo/rust-fnv |
| `foldhash` | 0.2.0 | Zlib | https://github.com/orlp/foldhash |
| `foreign-types` | 0.5.0 | MIT/Apache-2.0 | https://github.com/sfackler/foreign-types |
| `foreign-types-macros` | 0.2.4 | MIT/Apache-2.0 | https://github.com/sfackler/foreign-types |
| `foreign-types-shared` | 0.3.1 | MIT/Apache-2.0 | https://github.com/sfackler/foreign-types |
| `form_urlencoded` | 1.2.2 | MIT OR Apache-2.0 | https://github.com/servo/rust-url |
| `futures-channel` | 0.3.34 | MIT OR Apache-2.0 | https://github.com/rust-lang/futures-rs |
| `futures-core` | 0.3.34 | MIT OR Apache-2.0 | https://github.com/rust-lang/futures-rs |
| `futures-executor` | 0.3.34 | MIT OR Apache-2.0 | https://github.com/rust-lang/futures-rs |
| `futures-io` | 0.3.34 | MIT OR Apache-2.0 | https://github.com/rust-lang/futures-rs |
| `futures-lite` | 2.6.1 | Apache-2.0 OR MIT | https://github.com/smol-rs/futures-lite |
| `futures-macro` | 0.3.34 | MIT OR Apache-2.0 | https://github.com/rust-lang/futures-rs |
| `futures-sink` | 0.3.34 | MIT OR Apache-2.0 | https://github.com/rust-lang/futures-rs |
| `futures-task` | 0.3.34 | MIT OR Apache-2.0 | https://github.com/rust-lang/futures-rs |
| `futures-util` | 0.3.34 | MIT OR Apache-2.0 | https://github.com/rust-lang/futures-rs |
| `gdk` | 0.18.2 | MIT | https://github.com/gtk-rs/gtk3-rs |
| `gdk-pixbuf` | 0.18.5 | MIT | https://github.com/gtk-rs/gtk-rs-core |
| `gdk-pixbuf-sys` | 0.18.0 | MIT | https://github.com/gtk-rs/gtk-rs-core |
| `gdk-sys` | 0.18.2 | MIT | https://github.com/gtk-rs/gtk3-rs |
| `gdkwayland-sys` | 0.18.2 | MIT | https://github.com/gtk-rs/gtk3-rs |
| `gdkx11` | 0.18.2 | MIT | https://github.com/gtk-rs/gtk3-rs |
| `gdkx11-sys` | 0.18.2 | MIT | https://github.com/gtk-rs/gtk3-rs |
| `generic-array` | 0.14.7 | MIT | https://github.com/fizyk20/generic-array.git |
| `getrandom` | 0.2.17 | MIT OR Apache-2.0 | https://github.com/rust-random/getrandom |
| `getrandom` | 0.3.4 | MIT OR Apache-2.0 | https://github.com/rust-random/getrandom |
| `getrandom` | 0.4.3 | MIT OR Apache-2.0 | https://github.com/rust-random/getrandom |
| `gio` | 0.18.4 | MIT | https://github.com/gtk-rs/gtk-rs-core |
| `gio-sys` | 0.18.1 | MIT | https://github.com/gtk-rs/gtk-rs-core |
| `glam` | 0.34.1 | MIT OR Apache-2.0 | https://github.com/bitshifter/glam-rs |
| `glib` | 0.18.5 | MIT | https://github.com/gtk-rs/gtk-rs-core |
| `glib-macros` | 0.18.5 | MIT | https://github.com/gtk-rs/gtk-rs-core |
| `glib-sys` | 0.18.1 | MIT | https://github.com/gtk-rs/gtk-rs-core |
| `glob` | 0.3.4 | MIT OR Apache-2.0 | https://github.com/rust-lang/glob |
| `gobject-sys` | 0.18.0 | MIT | https://github.com/gtk-rs/gtk-rs-core |
| `gtk` | 0.18.2 | MIT | https://github.com/gtk-rs/gtk3-rs |
| `gtk-sys` | 0.18.2 | MIT | https://github.com/gtk-rs/gtk3-rs |
| `gtk3-macros` | 0.18.2 | MIT | https://github.com/gtk-rs/gtk3-rs |
| `hashbrown` | 0.12.3 | MIT OR Apache-2.0 | https://github.com/rust-lang/hashbrown |
| `hashbrown` | 0.16.1 | MIT OR Apache-2.0 | https://github.com/rust-lang/hashbrown |
| `hashbrown` | 0.17.1 | MIT OR Apache-2.0 | https://github.com/rust-lang/hashbrown |
| `hashlink` | 0.12.2 | MIT OR Apache-2.0 | https://github.com/djc/hashlink |
| `heck` | 0.4.1 | MIT OR Apache-2.0 | https://github.com/withoutboats/heck |
| `heck` | 0.5.0 | MIT OR Apache-2.0 | https://github.com/withoutboats/heck |
| `hermit-abi` | 0.5.3 | MIT OR Apache-2.0 | https://github.com/hermit-os/hermit-rs |
| `hex` | 0.4.3 | MIT OR Apache-2.0 | https://github.com/KokaKiwi/rust-hex |
| `hkdf` | 0.13.0 | MIT OR Apache-2.0 | https://github.com/RustCrypto/KDFs/ |
| `hmac` | 0.13.0 | MIT OR Apache-2.0 | https://github.com/RustCrypto/MACs |
| `html5ever` | 0.39.0 | MIT OR Apache-2.0 | https://github.com/servo/html5ever |
| `http` | 1.5.0 | MIT OR Apache-2.0 | https://github.com/hyperium/http |
| `http-body` | 1.1.0 | MIT | https://github.com/hyperium/http-body |
| `http-body-util` | 0.1.5 | MIT | https://github.com/hyperium/http-body |
| `httparse` | 1.10.1 | MIT OR Apache-2.0 | https://github.com/seanmonstar/httparse |
| `hybrid-array` | 0.4.15 | MIT OR Apache-2.0 | https://github.com/RustCrypto/hybrid-array |
| `hyper` | 1.12.0 | MIT | https://github.com/hyperium/hyper |
| `hyper-util` | 0.1.21 | MIT | https://github.com/hyperium/hyper-util |
| `iana-time-zone` | 0.1.65 | MIT OR Apache-2.0 | https://github.com/strawlab/iana-time-zone |
| `iana-time-zone-haiku` | 0.1.2 | MIT OR Apache-2.0 | https://github.com/strawlab/iana-time-zone |
| `ico` | 0.6.0 | MIT | https://github.com/mdsteele/rust-ico |
| `icu_collections` | 2.4.0 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `icu_locale_core` | 2.4.0 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `icu_normalizer` | 2.4.0 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `icu_normalizer_data` | 2.4.0 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `icu_properties` | 2.4.0 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `icu_properties_data` | 2.4.0 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `icu_provider` | 2.4.0 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `ident_case` | 1.0.1 | MIT/Apache-2.0 | https://github.com/TedDriggs/ident_case |
| `idna` | 1.1.0 | MIT OR Apache-2.0 | https://github.com/servo/rust-url/ |
| `idna_adapter` | 1.2.2 | Apache-2.0 OR MIT | https://github.com/hsivonen/idna_adapter |
| `indexmap` | 1.9.3 | Apache-2.0 OR MIT | https://github.com/bluss/indexmap |
| `indexmap` | 2.14.2 | Apache-2.0 OR MIT | https://github.com/indexmap-rs/indexmap |
| `infer` | 0.22.0 | MIT | https://github.com/bojand/infer |
| `inout` | 0.2.5 | MIT OR Apache-2.0 | https://github.com/RustCrypto/utils |
| `ipnet` | 2.12.2 | MIT OR Apache-2.0 | https://github.com/krisprice/ipnet |
| `itoa` | 1.0.18 | MIT OR Apache-2.0 | https://github.com/dtolnay/itoa |
| `javascriptcore-rs` | 1.1.2 | MIT | https://github.com/tauri-apps/javascriptcore-rs |
| `javascriptcore-rs-sys` | 1.1.1 | MIT | https://github.com/tauri-apps/javascriptcore-rs |
| `jiff` | 0.2.38 | Unlicense OR MIT | https://github.com/BurntSushi/jiff |
| `jiff-core` | 0.1.1 | Unlicense OR MIT | https://github.com/BurntSushi/jiff |
| `jiff-static` | 0.2.38 | Unlicense OR MIT | https://github.com/BurntSushi/jiff |
| `jiff-tzdb` | 0.1.9 | Unlicense OR MIT | https://github.com/BurntSushi/jiff |
| `jiff-tzdb-platform` | 0.1.3 | Unlicense OR MIT | https://github.com/BurntSushi/jiff |
| `jni` | 0.21.1 | MIT/Apache-2.0 | https://github.com/jni-rs/jni-rs |
| `jni` | 0.22.4 | MIT OR Apache-2.0 | https://github.com/jni-rs/jni-rs |
| `jni-macros` | 0.22.4 | MIT OR Apache-2.0 | https://github.com/jni-rs/jni-rs |
| `jni-sys` | 0.3.1 | MIT OR Apache-2.0 | https://github.com/jni-rs/jni-sys |
| `jni-sys` | 0.4.1 | MIT OR Apache-2.0 | https://github.com/jni-rs/jni-sys |
| `jni-sys-macros` | 0.4.1 | MIT OR Apache-2.0 | https://github.com/jni-rs/jni-sys |
| `js-sys` | 0.3.106 | MIT OR Apache-2.0 | https://github.com/wasm-bindgen/wasm-bindgen/tree/master/crates/js-sys |
| `json-patch` | 4.2.0 | MIT/Apache-2.0 | https://github.com/idubrov/json-patch |
| `jsonptr` | 0.7.1 | MIT OR Apache-2.0 | https://github.com/chanced/jsonptr |
| `keyboard-types` | 0.8.3 | MIT OR Apache-2.0 | https://github.com/rust-windowing/keyboard-types |
| `keyring` | 4.2.0 | MIT OR Apache-2.0 | https://github.com/open-source-cooperative/keyring-rs |
| `keyring-core` | 1.0.1 | MIT OR Apache-2.0 | https://github.com/open-source-cooperative/keyring-core.git |
| `kira` | 0.12.6 | MIT OR Apache-2.0 | https://github.com/tesselode/kira |
| `lazy_static` | 1.5.1 | MIT OR Apache-2.0 | https://github.com/rust-lang-nursery/lazy-static.rs |
| `libappindicator` | 0.9.0 | Apache-2.0 OR MIT |  |
| `libappindicator-sys` | 0.9.0 | Apache-2.0 OR MIT |  |
| `libc` | 0.2.191 | MIT OR Apache-2.0 | https://github.com/rust-lang/libc |
| `libdbus-sys` | 0.2.7 | Apache-2.0/MIT | https://github.com/diwic/dbus-rs |
| `libloading` | 0.7.4 | ISC | https://github.com/nagisa/rust_libloading/ |
| `libredox` | 0.1.25 | MIT | https://gitlab.redox-os.org/redox-os/libredox.git |
| `libsqlite3-sys` | 0.38.2 | MIT | https://github.com/rusqlite/rusqlite |
| `linux-raw-sys` | 0.12.1 | Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT | https://github.com/sunfishcode/linux-raw-sys |
| `litemap` | 0.8.3 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `lock_api` | 0.4.14 | MIT OR Apache-2.0 | https://github.com/Amanieu/parking_lot |
| `lock_api` | 0.5.0 | MIT OR Apache-2.0 | https://github.com/Amanieu/parking_lot |
| `log` | 0.4.34 | MIT OR Apache-2.0 | https://github.com/rust-lang/log |
| `mach2` | 0.6.0 | BSD-2-Clause OR MIT OR Apache-2.0 | https://github.com/JohnTitor/mach2 |
| `markup5ever` | 0.39.0 | MIT OR Apache-2.0 | https://github.com/servo/html5ever |
| `matchers` | 0.2.0 | MIT | https://github.com/hawkw/matchers |
| `memchr` | 2.8.3 | Unlicense OR MIT | https://github.com/BurntSushi/memchr |
| `memoffset` | 0.9.1 | MIT | https://github.com/Gilnaa/memoffset |
| `mime` | 0.3.17 | MIT OR Apache-2.0 | https://github.com/hyperium/mime |
| `miniz_oxide` | 0.8.9 | MIT OR Zlib OR Apache-2.0 | https://github.com/Frommi/miniz_oxide/tree/master/miniz_oxide |
| `miniz_oxide` | 0.9.1 | MIT OR Zlib OR Apache-2.0 | https://github.com/Frommi/miniz_oxide/tree/master/miniz_oxide |
| `mint` | 0.5.9 | MIT | https://github.com/kvark/mint |
| `mio` | 1.2.4 | MIT | https://github.com/tokio-rs/mio |
| `muda` | 0.20.0 | Apache-2.0 OR MIT | https://github.com/tauri-apps/muda |
| `ndk` | 0.9.0 | MIT OR Apache-2.0 | https://github.com/rust-mobile/ndk |
| `ndk-context` | 0.1.1 | MIT OR Apache-2.0 | https://github.com/rust-windowing/android-ndk-rs |
| `ndk-sys` | 0.6.0+11769913 | MIT OR Apache-2.0 | https://github.com/rust-mobile/ndk |
| `new_debug_unreachable` | 1.0.6 | MIT | https://github.com/mbrubeck/rust-debug-unreachable |
| `nu-ansi-term` | 0.50.3 | MIT | https://github.com/nushell/nu-ansi-term |
| `num` | 0.4.3 | MIT OR Apache-2.0 | https://github.com/rust-num/num |
| `num_enum` | 0.7.6 | BSD-3-Clause OR MIT OR Apache-2.0 | https://github.com/illicitonion/num_enum |
| `num_enum_derive` | 0.7.6 | BSD-3-Clause OR MIT OR Apache-2.0 | https://github.com/illicitonion/num_enum |
| `num-bigint` | 0.4.8 | MIT OR Apache-2.0 | https://github.com/rust-num/num-bigint |
| `num-complex` | 0.4.6 | MIT OR Apache-2.0 | https://github.com/rust-num/num-complex |
| `num-conv` | 0.2.2 | MIT OR Apache-2.0 | https://github.com/jhpratt/num-conv |
| `num-derive` | 0.4.2 | MIT OR Apache-2.0 | https://github.com/rust-num/num-derive |
| `num-integer` | 0.1.47 | MIT OR Apache-2.0 | https://github.com/rust-num/num-integer |
| `num-iter` | 0.1.46 | MIT OR Apache-2.0 | https://github.com/rust-num/num-iter |
| `num-rational` | 0.4.2 | MIT OR Apache-2.0 | https://github.com/rust-num/num-rational |
| `num-traits` | 0.2.19 | MIT OR Apache-2.0 | https://github.com/rust-num/num-traits |
| `objc2` | 0.6.5 | MIT | https://github.com/madsmtm/objc2 |
| `objc2-app-kit` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-audio-toolbox` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-avf-audio` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-cloud-kit` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-core-audio` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-core-audio-types` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-core-data` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-core-foundation` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-core-graphics` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-core-image` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-core-location` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-core-text` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-encode` | 4.1.0 | MIT | https://github.com/madsmtm/objc2 |
| `objc2-exception-helper` | 0.1.1 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-foundation` | 0.3.2 | MIT | https://github.com/madsmtm/objc2 |
| `objc2-io-surface` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-quartz-core` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-ui-kit` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-user-notifications` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `objc2-web-kit` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | https://github.com/madsmtm/objc2 |
| `once_cell` | 1.21.4 | MIT OR Apache-2.0 | https://github.com/matklad/once_cell |
| `openssl-probe` | 0.2.2 | MIT OR Apache-2.0 | https://github.com/rustls/openssl-probe |
| `option-ext` | 0.2.0 | MPL-2.0 | https://github.com/soc/option-ext.git |
| `ordered-stream` | 0.2.0 | MIT OR Apache-2.0 | https://github.com/danieldg/ordered-stream |
| `pango` | 0.18.3 | MIT | https://github.com/gtk-rs/gtk-rs-core |
| `pango-sys` | 0.18.0 | MIT | https://github.com/gtk-rs/gtk-rs-core |
| `parking` | 2.2.1 | Apache-2.0 OR MIT | https://github.com/smol-rs/parking |
| `parking_lot` | 0.12.5 | MIT OR Apache-2.0 | https://github.com/Amanieu/parking_lot |
| `parking_lot` | 0.13.0 | MIT OR Apache-2.0 | https://github.com/Amanieu/parking_lot |
| `parking_lot_core` | 0.9.12 | MIT OR Apache-2.0 | https://github.com/Amanieu/parking_lot |
| `parking_lot_core` | 0.10.0 | MIT OR Apache-2.0 | https://github.com/Amanieu/parking_lot |
| `pastey` | 0.2.3 | MIT OR Apache-2.0 | https://github.com/as1100k/pastey |
| `percent-encoding` | 2.3.2 | MIT OR Apache-2.0 | https://github.com/servo/rust-url/ |
| `phf` | 0.13.1 | MIT | https://github.com/rust-phf/rust-phf |
| `phf_codegen` | 0.13.1 | MIT | https://github.com/rust-phf/rust-phf |
| `phf_generator` | 0.13.1 | MIT | https://github.com/rust-phf/rust-phf |
| `phf_macros` | 0.13.1 | MIT | https://github.com/rust-phf/rust-phf |
| `phf_shared` | 0.13.1 | MIT | https://github.com/rust-phf/rust-phf |
| `pin-project-lite` | 0.2.17 | Apache-2.0 OR MIT | https://github.com/taiki-e/pin-project-lite |
| `piper` | 0.2.5 | MIT OR Apache-2.0 | https://github.com/smol-rs/piper |
| `pkg-config` | 0.3.34 | MIT OR Apache-2.0 | https://github.com/rust-lang/pkg-config-rs |
| `plist` | 1.10.3 | MIT | https://github.com/ebarnard/rust-plist/ |
| `png` | 0.18.1 | MIT OR Apache-2.0 | https://github.com/image-rs/image-png |
| `polling` | 3.11.0 | Apache-2.0 OR MIT | https://github.com/smol-rs/polling |
| `portable-atomic` | 1.15.0 | Apache-2.0 OR MIT | https://github.com/taiki-e/portable-atomic |
| `portable-atomic-util` | 0.2.8 | Apache-2.0 OR MIT | https://github.com/taiki-e/portable-atomic-util |
| `potential_utf` | 0.1.6 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `powerfmt` | 0.2.1 | MIT OR Apache-2.0 | https://github.com/jhpratt/powerfmt |
| `precomputed-hash` | 0.1.1 | MIT | https://github.com/emilio/precomputed-hash |
| `primal-check` | 0.3.4 | MIT OR Apache-2.0 | https://github.com/huonw/primal |
| `proc-macro-crate` | 1.3.1 | MIT OR Apache-2.0 | https://github.com/bkchr/proc-macro-crate |
| `proc-macro-crate` | 2.0.2 | MIT OR Apache-2.0 | https://github.com/bkchr/proc-macro-crate |
| `proc-macro-crate` | 3.5.0 | MIT OR Apache-2.0 | https://github.com/bkchr/proc-macro-crate |
| `proc-macro-error` | 1.0.4 | MIT OR Apache-2.0 | https://gitlab.com/CreepySkeleton/proc-macro-error |
| `proc-macro-error-attr` | 1.0.4 | MIT OR Apache-2.0 | https://gitlab.com/CreepySkeleton/proc-macro-error |
| `proc-macro2` | 1.0.107 | MIT OR Apache-2.0 | https://github.com/dtolnay/proc-macro2 |
| `quick-xml` | 0.42.0 | MIT | https://github.com/tafia/quick-xml |
| `quote` | 1.0.47 | MIT OR Apache-2.0 | https://github.com/dtolnay/quote |
| `r-efi` | 5.3.0 | MIT OR Apache-2.0 OR LGPL-2.1-or-later | https://github.com/r-efi/r-efi |
| `r-efi` | 6.0.0 | MIT OR Apache-2.0 OR LGPL-2.1-or-later | https://github.com/r-efi/r-efi |
| `r2d2` | 0.8.10 | MIT/Apache-2.0 | https://github.com/sfackler/r2d2 |
| `r2d2_sqlite` | 0.35.0 | MIT | https://github.com/ivanceras/r2d2-sqlite |
| `rand` | 0.10.3 | MIT OR Apache-2.0 | https://github.com/rust-random/rand |
| `rand_core` | 0.10.1 | MIT OR Apache-2.0 | https://github.com/rust-random/rand_core |
| `raw-window-handle` | 0.6.2 | MIT OR Apache-2.0 OR Zlib | https://github.com/rust-windowing/raw-window-handle |
| `redox_syscall` | 0.5.18 | MIT | https://gitlab.redox-os.org/redox-os/syscall |
| `redox_syscall` | 0.9.5 | MIT | https://gitlab.redox-os.org/redox-os/kernel |
| `redox_users` | 0.5.3 | MIT | https://gitlab.redox-os.org/redox-os/users |
| `ref-cast` | 1.0.27 | MIT OR Apache-2.0 | https://github.com/dtolnay/ref-cast |
| `ref-cast-impl` | 1.0.27 | MIT OR Apache-2.0 | https://github.com/dtolnay/ref-cast |
| `regex` | 1.13.1 | MIT OR Apache-2.0 | https://github.com/rust-lang/regex |
| `regex-automata` | 0.4.18 | MIT OR Apache-2.0 | https://github.com/rust-lang/regex |
| `regex-lite` | 0.1.9 | MIT OR Apache-2.0 | https://github.com/rust-lang/regex |
| `regex-syntax` | 0.8.11 | MIT OR Apache-2.0 | https://github.com/rust-lang/regex |
| `reqwest` | 0.13.5 | MIT OR Apache-2.0 | https://github.com/seanmonstar/reqwest |
| `ring` | 0.17.14 | Apache-2.0 AND ISC | https://github.com/briansmith/ring |
| `rsqlite-vfs` | 0.1.1 | MIT |  |
| `rtrb` | 0.4.1 | MIT OR Apache-2.0 | https://github.com/mgeier/rtrb |
| `rusqlite` | 0.40.2 | MIT | https://github.com/rusqlite/rusqlite |
| `rustc_version` | 0.4.1 | MIT OR Apache-2.0 | https://github.com/djc/rustc-version-rs |
| `rustc-hash` | 2.1.3 | Apache-2.0 OR MIT | https://github.com/rust-lang/rustc-hash |
| `rustfft` | 6.4.1 | MIT OR Apache-2.0 | https://github.com/ejmahler/RustFFT |
| `rustix` | 1.1.6 | Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT | https://github.com/bytecodealliance/rustix |
| `rustls` | 0.23.46 | Apache-2.0 OR ISC OR MIT | https://github.com/rustls/rustls |
| `rustls-native-certs` | 0.8.5 | Apache-2.0 OR ISC OR MIT | https://github.com/rustls/rustls-native-certs |
| `rustls-pki-types` | 1.15.1 | MIT OR Apache-2.0 | https://github.com/rustls/pki-types |
| `rustls-platform-verifier` | 0.7.1 | MIT OR Apache-2.0 | https://github.com/rustls/rustls-platform-verifier |
| `rustls-platform-verifier-android` | 0.2.0 | MIT OR Apache-2.0 | https://github.com/rustls/rustls-platform-verifier |
| `rustls-webpki` | 0.103.16 | ISC | https://github.com/rustls/webpki |
| `rustversion` | 1.0.23 | MIT OR Apache-2.0 | https://github.com/dtolnay/rustversion |
| `same-file` | 1.0.6 | Unlicense/MIT | https://github.com/BurntSushi/same-file |
| `schannel` | 0.1.30 | MIT | https://github.com/steffengy/schannel-rs |
| `scheduled-thread-pool` | 0.2.8 | MIT/Apache-2.0 | https://github.com/sfackler/scheduled-thread-pool |
| `schemars` | 0.8.22 | MIT | https://github.com/GREsau/schemars |
| `schemars` | 0.9.0 | MIT | https://github.com/GREsau/schemars |
| `schemars` | 1.2.3 | MIT | https://github.com/GREsau/schemars |
| `schemars_derive` | 0.8.22 | MIT | https://github.com/GREsau/schemars |
| `scopeguard` | 1.2.0 | MIT OR Apache-2.0 | https://github.com/bluss/scopeguard |
| `secret-service` | 5.2.0 | MIT OR Apache-2.0 | https://github.com/hwchen/secret-service-rs.git |
| `security-framework` | 3.7.0 | MIT OR Apache-2.0 | https://github.com/kornelski/rust-security-framework |
| `security-framework-sys` | 2.17.0 | MIT OR Apache-2.0 | https://github.com/kornelski/rust-security-framework |
| `selectors` | 0.38.0 | MPL-2.0 | https://github.com/servo/stylo |
| `semver` | 1.0.28 | MIT OR Apache-2.0 | https://github.com/dtolnay/semver |
| `send_wrapper` | 0.6.0 | MIT/Apache-2.0 | https://github.com/thk1/send_wrapper |
| `serde` | 1.0.229 | MIT OR Apache-2.0 | https://github.com/serde-rs/serde |
| `serde_core` | 1.0.229 | MIT OR Apache-2.0 | https://github.com/serde-rs/serde |
| `serde_derive` | 1.0.229 | MIT OR Apache-2.0 | https://github.com/serde-rs/serde |
| `serde_derive_internals` | 0.29.1 | MIT OR Apache-2.0 | https://github.com/serde-rs/serde |
| `serde_json` | 1.0.154 | MIT OR Apache-2.0 | https://github.com/serde-rs/json |
| `serde_repr` | 0.1.21 | MIT OR Apache-2.0 | https://github.com/dtolnay/serde-repr |
| `serde_spanned` | 0.6.9 | MIT OR Apache-2.0 | https://github.com/toml-rs/toml |
| `serde_spanned` | 1.1.2 | MIT OR Apache-2.0 | https://github.com/toml-rs/toml |
| `serde_with` | 3.24.0 | MIT OR Apache-2.0 | https://github.com/jonasbb/serde_with/ |
| `serde_with_macros` | 3.24.0 | MIT OR Apache-2.0 | https://github.com/jonasbb/serde_with/ |
| `serde-untagged` | 0.1.9 | MIT OR Apache-2.0 | https://github.com/dtolnay/serde-untagged |
| `serialize-to-javascript` | 0.1.2 | MIT OR Apache-2.0 | https://github.com/chippers/serialize-to-javascript |
| `serialize-to-javascript-impl` | 0.1.2 | MIT OR Apache-2.0 | https://github.com/chippers/serialize-to-javascript |
| `servo_arc` | 0.4.3 | MIT OR Apache-2.0 | https://github.com/servo/stylo |
| `sha2` | 0.10.9 | MIT OR Apache-2.0 | https://github.com/RustCrypto/hashes |
| `sha2` | 0.11.1 | MIT OR Apache-2.0 | https://github.com/RustCrypto/hashes |
| `sharded-slab` | 0.1.7 | MIT | https://github.com/hawkw/sharded-slab |
| `shlex` | 2.0.1 | MIT OR Apache-2.0 | https://github.com/comex/rust-shlex |
| `signal-hook-registry` | 1.4.8 | MIT OR Apache-2.0 | https://github.com/vorner/signal-hook |
| `simd_cesu8` | 1.2.0 | Apache-2.0 OR MIT | https://github.com/seancroach/simd_cesu8 |
| `simd-adler32` | 0.3.10 | MIT | https://github.com/mcountryman/simd-adler32 |
| `simdutf8` | 0.1.5 | MIT OR Apache-2.0 | https://github.com/rusticstuff/simdutf8 |
| `siphasher` | 1.0.4 | MIT OR Apache-2.0 | https://github.com/jedisct1/rust-siphash |
| `slab` | 0.4.12 | MIT | https://github.com/tokio-rs/slab |
| `smallvec` | 1.16.4 | MIT OR Apache-2.0 | https://github.com/servo/rust-smallvec |
| `socket2` | 0.6.5 | MIT OR Apache-2.0 | https://github.com/rust-lang/socket2 |
| `softbuffer` | 0.4.8 | MIT OR Apache-2.0 | https://github.com/rust-windowing/softbuffer |
| `soup3` | 0.5.0 | MIT | https://gitlab.gnome.org/World/Rust/soup3-rs |
| `soup3-sys` | 0.5.0 | MIT | https://gitlab.gnome.org/World/Rust/soup3-rs |
| `sqlite-wasm-rs` | 0.5.5 | MIT | https://github.com/Spxg/sqlite-wasm-rs |
| `stable_deref_trait` | 1.2.1 | MIT OR Apache-2.0 | https://github.com/storyyeller/stable_deref_trait |
| `static_vcruntime` | 3.0.0 | MIT OR Apache-2.0 OR Zlib | https://github.com/ChrisDenton/static_vcruntime |
| `strength_reduce` | 0.2.4 | MIT OR Apache-2.0 | http://github.com/ejmahler/strength_reduce |
| `string_cache` | 0.9.0 | MIT OR Apache-2.0 | https://github.com/servo/string-cache |
| `string_cache_codegen` | 0.6.1 | MIT OR Apache-2.0 | https://github.com/servo/string-cache |
| `strsim` | 0.11.1 | MIT | https://github.com/rapidfuzz/strsim-rs |
| `subtle` | 2.6.1 | BSD-3-Clause | https://github.com/dalek-cryptography/subtle |
| `swift-rs` | 1.0.9 | MIT OR Apache-2.0 | https://github.com/Brendonovich/swift-rs |
| `symlink` | 0.1.0 | MIT/Apache-2.0 | https://gitlab.com/chris-morgan/symlink |
| `symphonia` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `symphonia-bundle-flac` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `symphonia-bundle-mp3` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `symphonia-codec-aac` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `symphonia-codec-adpcm` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `symphonia-codec-alac` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `symphonia-codec-pcm` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `symphonia-codec-vorbis` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `symphonia-common` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `symphonia-core` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `symphonia-format-isomp4` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `symphonia-format-mkv` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `symphonia-format-ogg` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `symphonia-format-riff` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `symphonia-metadata` | 0.6.1 | MPL-2.0 | https://github.com/pdeljanov/Symphonia |
| `syn` | 1.0.109 | MIT OR Apache-2.0 | https://github.com/dtolnay/syn |
| `syn` | 2.0.119 | MIT OR Apache-2.0 | https://github.com/dtolnay/syn |
| `syn` | 3.0.9 | MIT OR Apache-2.0 | https://github.com/dtolnay/syn |
| `sync_wrapper` | 1.0.2 | Apache-2.0 | https://github.com/Actyx/sync_wrapper |
| `synstructure` | 0.14.0 | MIT | https://github.com/mystor/synstructure |
| `system-deps` | 6.2.2 | MIT OR Apache-2.0 | https://github.com/gdesmott/system-deps |
| `tao` | 0.37.2 | Apache-2.0 | https://github.com/tauri-apps/tao |
| `tao-macros` | 0.1.4 | MIT OR Apache-2.0 | https://github.com/tauri-apps/tao |
| `target-lexicon` | 0.12.16 | Apache-2.0 WITH LLVM-exception | https://github.com/bytecodealliance/target-lexicon |
| `tauri` | 2.12.5 | Apache-2.0 OR MIT | https://github.com/tauri-apps/tauri |
| `tauri-build` | 2.7.4 | Apache-2.0 OR MIT | https://github.com/tauri-apps/tauri |
| `tauri-codegen` | 2.7.4 | Apache-2.0 OR MIT | https://github.com/tauri-apps/tauri |
| `tauri-macros` | 2.7.4 | Apache-2.0 OR MIT | https://github.com/tauri-apps/tauri |
| `tauri-runtime` | 2.12.2 | Apache-2.0 OR MIT | https://github.com/tauri-apps/tauri |
| `tauri-runtime-wry` | 2.12.3 | Apache-2.0 OR MIT | https://github.com/tauri-apps/tauri |
| `tauri-utils` | 2.10.2 | Apache-2.0 OR MIT | https://github.com/tauri-apps/tauri |
| `tauri-winres` | 0.3.7 | MIT | https://github.com/tauri-apps/winres |
| `tempfile` | 3.27.0 | MIT OR Apache-2.0 | https://github.com/Stebalien/tempfile |
| `tendril` | 0.5.1 | MIT OR Apache-2.0 | https://github.com/servo/html5ever |
| `termcolor` | 1.4.1 | Unlicense OR MIT | https://github.com/BurntSushi/termcolor |
| `thiserror` | 1.0.69 | MIT OR Apache-2.0 | https://github.com/dtolnay/thiserror |
| `thiserror` | 2.0.21 | MIT OR Apache-2.0 | https://github.com/dtolnay/thiserror |
| `thiserror-impl` | 1.0.69 | MIT OR Apache-2.0 | https://github.com/dtolnay/thiserror |
| `thiserror-impl` | 2.0.21 | MIT OR Apache-2.0 | https://github.com/dtolnay/thiserror |
| `thread_local` | 1.1.10 | MIT OR Apache-2.0 | https://github.com/Amanieu/thread_local-rs |
| `time` | 0.3.55 | MIT OR Apache-2.0 | https://github.com/time-rs/time |
| `time-core` | 0.1.9 | MIT OR Apache-2.0 | https://github.com/time-rs/time |
| `time-macros` | 0.2.32 | MIT OR Apache-2.0 | https://github.com/time-rs/time |
| `tinystr` | 0.8.5 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `tinyvec` | 1.13.3 | Zlib OR Apache-2.0 OR MIT | https://github.com/Lokathor/tinyvec |
| `tokio` | 1.54.1 | MIT | https://github.com/tokio-rs/tokio |
| `tokio-util` | 0.7.20 | MIT | https://github.com/tokio-rs/tokio |
| `toml` | 0.8.2 | MIT OR Apache-2.0 | https://github.com/toml-rs/toml |
| `toml` | 1.1.8+spec-1.1.0 | MIT OR Apache-2.0 | https://github.com/toml-rs/toml |
| `toml_datetime` | 0.6.3 | MIT OR Apache-2.0 | https://github.com/toml-rs/toml |
| `toml_datetime` | 1.1.2+spec-1.1.0 | MIT OR Apache-2.0 | https://github.com/toml-rs/toml |
| `toml_edit` | 0.19.15 | MIT OR Apache-2.0 | https://github.com/toml-rs/toml |
| `toml_edit` | 0.20.2 | MIT OR Apache-2.0 | https://github.com/toml-rs/toml |
| `toml_edit` | 0.25.17+spec-1.1.0 | MIT OR Apache-2.0 | https://github.com/toml-rs/toml |
| `toml_parser` | 1.1.5+spec-1.1.0 | MIT OR Apache-2.0 | https://github.com/toml-rs/toml |
| `toml_writer` | 1.1.3+spec-1.1.0 | MIT OR Apache-2.0 | https://github.com/toml-rs/toml |
| `tower` | 0.5.3 | MIT | https://github.com/tower-rs/tower |
| `tower-http` | 0.6.11 | MIT | https://github.com/tower-rs/tower-http |
| `tower-layer` | 0.3.3 | MIT | https://github.com/tower-rs/tower |
| `tower-service` | 0.3.3 | MIT | https://github.com/tower-rs/tower |
| `tracing` | 0.1.44 | MIT | https://github.com/tokio-rs/tracing |
| `tracing-appender` | 0.2.5 | MIT | https://github.com/tokio-rs/tracing |
| `tracing-attributes` | 0.1.31 | MIT | https://github.com/tokio-rs/tracing |
| `tracing-core` | 0.1.36 | MIT | https://github.com/tokio-rs/tracing |
| `tracing-log` | 0.2.0 | MIT | https://github.com/tokio-rs/tracing |
| `tracing-subscriber` | 0.3.23 | MIT | https://github.com/tokio-rs/tracing |
| `transpose` | 0.2.3 | MIT OR Apache-2.0 | https://github.com/ejmahler/transpose |
| `tray-icon` | 0.25.1 | MIT OR Apache-2.0 | https://github.com/tauri-apps/tray-icon |
| `triple_buffer` | 9.0.0 | MPL-2.0 | https://github.com/HadrienG2/triple-buffer |
| `try-lock` | 0.2.5 | MIT | https://github.com/seanmonstar/try-lock |
| `ts-rs` | 12.0.1 | MIT | https://github.com/Aleph-Alpha/ts-rs |
| `ts-rs-macros` | 12.0.1 | MIT | https://github.com/Aleph-Alpha/ts-rs |
| `typeid` | 1.0.3 | MIT OR Apache-2.0 | https://github.com/dtolnay/typeid |
| `typenum` | 1.20.1 | MIT OR Apache-2.0 | https://github.com/paholg/typenum |
| `uds_windows` | 1.2.1 | MIT | https://github.com/haraldh/rust_uds_windows |
| `unicode-ident` | 1.0.27 | (MIT OR Apache-2.0) AND Unicode-3.0 | https://github.com/dtolnay/unicode-ident |
| `unicode-segmentation` | 1.13.3 | MIT OR Apache-2.0 | https://github.com/unicode-rs/unicode-segmentation |
| `untrusted` | 0.9.0 | ISC | https://github.com/briansmith/untrusted |
| `ureq` | 3.5.0 | MIT OR Apache-2.0 | https://github.com/algesten/ureq |
| `ureq-proto` | 0.6.5 | MIT OR Apache-2.0 | https://github.com/algesten/ureq-proto |
| `url` | 2.5.8 | MIT OR Apache-2.0 | https://github.com/servo/rust-url |
| `urlpattern` | 0.6.0 | MIT | https://github.com/denoland/rust-urlpattern |
| `utf_types` | 1.0.0 | Apache-2.0 OR MIT | https://github.com/hsivonen/utf_types |
| `utf8_iter` | 1.1.0 | Apache-2.0 OR MIT | https://github.com/hsivonen/utf8_iter |
| `utf8-zero` | 0.8.1 | MIT OR Apache-2.0 | https://github.com/algesten/utf8-zero |
| `uuid` | 1.29.0 | Apache-2.0 OR MIT | https://github.com/uuid-rs/uuid |
| `valuable` | 0.1.1 | MIT | https://github.com/tokio-rs/valuable |
| `vcpkg` | 0.2.15 | MIT/Apache-2.0 | https://github.com/mcgoo/vcpkg-rs |
| `version_check` | 0.9.5 | MIT/Apache-2.0 | https://github.com/SergioBenitez/version_check |
| `version-compare` | 0.2.1 | MIT | https://gitlab.com/timvisee/version-compare |
| `vswhom` | 0.1.0 | MIT | https://github.com/nabijaczleweli/vswhom.rs |
| `vswhom-sys` | 0.1.3 | MIT | https://github.com/nabijaczleweli/vswhom-sys.rs |
| `walkdir` | 2.5.0 | Unlicense/MIT | https://github.com/BurntSushi/walkdir |
| `want` | 0.3.2 | MIT | https://github.com/seanmonstar/want |
| `wasi` | 0.11.1+wasi-snapshot-preview1 | Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT | https://github.com/bytecodealliance/wasi |
| `wasip2` | 1.0.4+wasi-0.2.12 | Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT | https://github.com/bytecodealliance/wasi-rs |
| `wasm-bindgen` | 0.2.129 | MIT OR Apache-2.0 | https://github.com/wasm-bindgen/wasm-bindgen |
| `wasm-bindgen-futures` | 0.4.79 | MIT OR Apache-2.0 | https://github.com/wasm-bindgen/wasm-bindgen/tree/master/crates/futures |
| `wasm-bindgen-macro` | 0.2.129 | MIT OR Apache-2.0 | https://github.com/wasm-bindgen/wasm-bindgen/tree/master/crates/macro |
| `wasm-bindgen-macro-support` | 0.2.129 | MIT OR Apache-2.0 | https://github.com/wasm-bindgen/wasm-bindgen/tree/main/crates/macro-support |
| `wasm-bindgen-shared` | 0.2.129 | MIT OR Apache-2.0 | https://github.com/wasm-bindgen/wasm-bindgen/tree/master/crates/shared |
| `wasm-streams` | 0.5.0 | MIT OR Apache-2.0 | https://github.com/MattiasBuelens/wasm-streams/ |
| `web_atoms` | 0.2.6 | MIT OR Apache-2.0 | https://github.com/servo/html5ever |
| `web-sys` | 0.3.106 | MIT OR Apache-2.0 | https://github.com/wasm-bindgen/wasm-bindgen/tree/master/crates/web-sys |
| `web-time` | 1.1.0 | MIT OR Apache-2.0 | https://github.com/daxpedda/web-time |
| `webkit2gtk` | 2.0.2 | MIT | https://github.com/tauri-apps/webkit2gtk-rs |
| `webkit2gtk-sys` | 2.0.2 | MIT | https://github.com/tauri-apps/webkit2gtk-rs |
| `webpki-root-certs` | 1.0.11 | CDLA-Permissive-2.0 | https://github.com/rustls/webpki-roots |
| `webpki-roots` | 1.0.11 | CDLA-Permissive-2.0 | https://github.com/rustls/webpki-roots |
| `webview2-com` | 0.39.1 | MIT | https://github.com/wravery/webview2-rs |
| `webview2-com-macros` | 0.8.1 | MIT | https://github.com/wravery/webview2-rs |
| `webview2-com-sys` | 0.39.1 | MIT | https://github.com/wravery/webview2-rs |
| `winapi` | 0.3.9 | MIT/Apache-2.0 | https://github.com/retep998/winapi-rs |
| `winapi-i686-pc-windows-gnu` | 0.4.0 | MIT/Apache-2.0 | https://github.com/retep998/winapi-rs |
| `winapi-util` | 0.1.11 | Unlicense OR MIT | https://github.com/BurntSushi/winapi-util |
| `winapi-x86_64-pc-windows-gnu` | 0.4.0 | MIT/Apache-2.0 | https://github.com/retep998/winapi-rs |
| `window-vibrancy` | 0.8.1 | Apache-2.0 OR MIT | https://github.com/tauri-apps/tauri-plugin-vibrancy |
| `windows` | 0.62.2 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_aarch64_gnullvm` | 0.42.2 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_aarch64_gnullvm` | 0.52.6 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_aarch64_msvc` | 0.42.2 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_aarch64_msvc` | 0.52.6 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_i686_gnu` | 0.42.2 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_i686_gnu` | 0.52.6 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_i686_gnullvm` | 0.52.6 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_i686_msvc` | 0.42.2 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_i686_msvc` | 0.52.6 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_x86_64_gnu` | 0.42.2 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_x86_64_gnu` | 0.52.6 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_x86_64_gnullvm` | 0.42.2 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_x86_64_gnullvm` | 0.52.6 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_x86_64_msvc` | 0.42.2 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows_x86_64_msvc` | 0.52.6 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-collections` | 0.3.2 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-core` | 0.62.2 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-future` | 0.3.2 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-implement` | 0.60.2 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-interface` | 0.59.3 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-link` | 0.2.1 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-native-keyring-store` | 1.1.0 | MIT OR Apache-2.0 | https://github.com/open-source-cooperative/windows-native-keyring-store.git |
| `windows-numerics` | 0.3.1 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-result` | 0.4.1 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-strings` | 0.5.1 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-sys` | 0.45.0 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-sys` | 0.52.0 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-sys` | 0.61.2 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-targets` | 0.42.2 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-targets` | 0.52.6 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-threading` | 0.2.1 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `windows-version` | 0.1.7 | MIT OR Apache-2.0 | https://github.com/microsoft/windows-rs |
| `winnow` | 0.5.40 | MIT | https://github.com/winnow-rs/winnow |
| `winnow` | 1.0.4 | MIT | https://github.com/winnow-rs/winnow |
| `winreg` | 0.56.0 | MIT | https://github.com/gentoo90/winreg-rs |
| `wit-bindgen` | 0.57.1 | Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT | https://github.com/bytecodealliance/wit-bindgen |
| `writeable` | 0.6.4 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `wry` | 0.57.1 | Apache-2.0 OR MIT | https://github.com/tauri-apps/wry |
| `x11` | 2.21.0 | MIT | https://github.com/AltF02/x11-rs.git |
| `x11-dl` | 2.21.0 | MIT | https://github.com/AltF02/x11-rs.git |
| `yoke` | 0.8.4 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `yoke-derive` | 0.8.4 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `zbus` | 5.19.0 | MIT | https://github.com/z-galaxy/zbus/ |
| `zbus_macros` | 5.19.0 | MIT | https://github.com/z-galaxy/zbus/ |
| `zbus_names` | 4.3.5 | MIT | https://github.com/z-galaxy/zbus/ |
| `zbus-secret-service-keyring-store` | 1.0.1 | MIT OR Apache-2.0 | https://github.com/open-source-cooperative/zbus-secret-service-keyring-store.git |
| `zcheapstr` | 1.2.0 | MIT | https://github.com/z-galaxy/zcheapstr/ |
| `zerofrom` | 0.1.8 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `zerofrom-derive` | 0.1.8 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `zeroize` | 1.9.1 | Apache-2.0 OR MIT | https://github.com/RustCrypto/utils |
| `zerotrie` | 0.2.5 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `zerovec` | 0.11.9 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `zerovec-derive` | 0.11.7 | Unicode-3.0 | https://github.com/unicode-org/icu4x |
| `zlib-rs` | 0.6.8 | Zlib | https://github.com/trifectatechfoundation/zlib-rs |
| `zmij` | 1.0.23 | MIT | https://github.com/dtolnay/zmij |
| `zvariant` | 5.15.1 | MIT | https://github.com/z-galaxy/zbus/ |
| `zvariant_derive` | 5.15.1 | MIT | https://github.com/z-galaxy/zbus/ |
| `zvariant_utils` | 4.2.0 | MIT | https://github.com/z-galaxy/zbus/ |

## Componentes de JavaScript (24)

| Componente | Versión | Licencia | Origen |
|---|---|---|---|
| `@iconify/types` | 2.0.0 | MIT | https://github.com/iconify/iconify |
| `@jridgewell/gen-mapping` | 0.3.13 | MIT | https://github.com/jridgewell/sourcemaps/tree/main/packages/gen-mapping |
| `@jridgewell/remapping` | 2.3.5 | MIT | https://github.com/jridgewell/sourcemaps/tree/main/packages/remapping |
| `@jridgewell/resolve-uri` | 3.1.2 | MIT | https://github.com/jridgewell/resolve-uri#readme |
| `@jridgewell/sourcemap-codec` | 1.6.0 | MIT | https://github.com/jridgewell/sourcemaps/tree/main/packages/sourcemap-codec |
| `@jridgewell/trace-mapping` | 0.3.31 | MIT | https://github.com/jridgewell/sourcemaps/tree/main/packages/trace-mapping |
| `@ktibow/iconset-material-symbols` | 0.0.1764827375 | Apache-2.0 | https://github.com/KTibow/to-icon-sets |
| `@ktibow/material-color-utilities-nightly` | 0.4.1772748028000 | Apache-2.0 | https://github.com/material-foundation/material-color-utilities/tree/main/typescript |
| `@sveltejs/acorn-typescript` | 1.0.13 | MIT | https://github.com/sveltejs/acorn-typescript#readme |
| `@tauri-apps/api` | 2.12.4 | Apache-2.0 OR MIT | https://github.com/tauri-apps/tauri#readme |
| `@types/estree` | 1.0.9 | MIT | https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/estree |
| `acorn` | 8.19.0 | MIT | https://github.com/acornjs/acorn |
| `aria-query` | 5.3.1 | Apache-2.0 | https://github.com/A11yance/aria-query#readme |
| `axobject-query` | 4.1.0 | Apache-2.0 | https://github.com/A11yance/axobject-query#readme |
| `clsx` | 2.1.1 | MIT | https://github.com/lukeed/clsx#readme |
| `devalue` | 5.9.4 | MIT | https://github.com/sveltejs/devalue#readme |
| `esm-env` | 1.2.2 | MIT | https://github.com/benmccann/esm-env |
| `esrap` | 2.4.0 | MIT | https://github.com/sveltejs/esrap#readme |
| `is-reference` | 3.0.3 | MIT | https://github.com/Rich-Harris/is-reference#readme |
| `locate-character` | 3.0.0 | MIT | https://gitlab.com/Rich-Harris/locate-character#README |
| `m3-svelte` | 7.2.1 | Apache-2.0 OR GPL-3.0-only | https://github.com/KTibow/m3-svelte |
| `magic-string` | 0.30.21 | MIT | https://github.com/Rich-Harris/magic-string#readme |
| `svelte` | 5.57.3 | MIT | https://svelte.dev |
| `zimmerframe` | 1.1.5 | MIT | https://github.com/sveltejs/zimmerframe#readme |
