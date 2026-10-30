# Prototipo F0.4.7: listas largas en WebKitGTK (2026-10-29)

> Mide la lista de canciones en el motor real de Tauri en Linux. Código en `scripts/prototipos/lista/`.

## Qué se midió

Una lista con la forma que tendrá la biblioteca (número, portada, título, artista, álbum y duración, filas de 56 px)
alimentada por una fuente simulada con **datos y portadas distintos por fila**. El banco carga la página en
WebKitGTK 2.54 (el mismo que usa Tauri), la desplaza 8 s a velocidad constante y cuenta los fotogramas. Un
fotograma "largo" pasa de 25 ms (1,5 veces el de 60 Hz).

La técnica no es la de NB Books. NB Books cambió su ventana virtual por **páginas** (su F1.6.16) porque el tamaño
del bloque pedido dependía de la altura de la ventana: al desplazarse cambiaba el origen de la petición y la lista se
rehacía sola. Para una lista de canciones, que se espera desplazar de corrido, aquí se prueba una ventana virtual que
evita ese defecto por construcción:

* filas de **alto fijo**, así que la posición de cualquier fila es una multiplicación;
* datos pedidos en **bloques de 256 alineados** a su tamaño: desplazarse dentro de un bloque no vuelve a pedir nada
  (una prueba lo fija).

## Resultados

| Filas | Velocidad | Mediana | p95 | Fotogramas largos | Nodos |
|---|---|---|---|---|---|
| 2.397 (la biblioteca real) | 12.000 px/s | 17 ms | 18 ms | 0 de 481 | 268 |
| 100.000 | 3.000 px/s (arrastre rápido) | 17 ms | 18 ms | 0 de 480 | 268 |
| 100.000 | 12.000 px/s | 17 ms | 18 ms | 0 de 481 | 268 |
| 100.000 | 30.000 px/s (lanzar la barra) | 17 ms | 18 ms | 1 de 480 | 268 |

El número de nodos no depende del total: 268 con 2.397 filas y con 100.000.

## Lo que costó encontrar

1. **El primer banco medía al simulador.** Generar cada portada con un lienzo y codificarla en JPEG en el momento
   llevaba el p95 a 147 ms a alta velocidad. Con el truco de NB Books (un JPEG base y ocho bytes distintos al final,
   que el decodificador ignora) el coste desaparece y lo que se mide es la lista.
2. **El coste real son las portadas nuevas a alta velocidad.** Sin portadas, 12.000 px/s salen limpios; con ellas,
   el p95 subía a 98 ms: en WebKitGTK cada imagen nueva pasa por el proceso de red, y a cuatro filas nuevas por
   fotograma eso es lo que tira los fotogramas. **Solución:** mientras la lista va a más de dos filas por fotograma
   no se piden portadas, y aparecen al frenar 120 ms. Con eso, 0 fotogramas largos a cualquier velocidad.
3. Recompilar con el servidor de vista previa en marcha puede servir la compilación anterior (lo documentó NB
   Books): las cifras de arriba se repitieron tras reiniciarlo.

## Conclusión

La ventana virtual de alto fijo con bloques alineados basta para la biblioteca, también con 100.000 canciones, y
conserva el desplazamiento continuo. Se propone **enmendar ADR-008**, que decía "la solución que NB Books ya midió"
(las páginas), para adoptar esta, con la regla de no pedir portadas durante el desplazamiento rápido. La enmienda
queda pendiente de que Nathan la acepte, porque cambia un ADR.

Lo que no se midió aquí: la carga real de portadas desde el protocolo `asset://` de Tauri, que llega en F2.2.3 con
la biblioteca de verdad.
