/**
 * Los acentos de NB Sound.
 *
 * Son los 63 temas de la V1 (`legado/ui/modelos_qml.py`, `_TEMAS`) reducidos a lo
 * que Material 3 necesita de ellos: una semilla. En la V2 el tema es claro, oscuro
 * o el del sistema, y el color sale de la portada que suena o de uno de estos
 * acentos (ADR-008). Se conservan id y nombre para que el importador traduzca la
 * preferencia de la V1 sin perderla.
 */

export interface Acento {
  readonly id: string;
  readonly nombre: string;
  readonly semilla: string;
}

export const ACENTOS: readonly Acento[] = [
  { id: 'negro_puro', nombre: 'Negro Puro (OLED)', semilla: '#00e5ff' },
  { id: 'arcilla_nocturna', nombre: 'Arcilla Nocturna', semilla: '#e07a52' },
  { id: 'arcilla_calida', nombre: 'Arcilla Cálida', semilla: '#c15f3c' },
  { id: 'oro_liquido', nombre: 'Oro Líquido', semilla: '#f2b90f' },
  { id: 'oscuro_profundo', nombre: 'Abismo Profundo', semilla: '#4fc3f7' },
  { id: 'electrico_voltaje', nombre: 'Voltaje Azul', semilla: '#00f0ff' },
  { id: 'lima_suave', nombre: 'Lima Láser', semilla: '#7fff7f' },
  { id: 'carmesi_nocturno', nombre: 'Carmesí Nocturno', semilla: '#ff4d73' },
  { id: 'aurora_boreal', nombre: 'Aurora Boreal', semilla: '#4db8ff' },
  { id: 'selva_neon', nombre: 'Selva Neón', semilla: '#5effb3' },
  { id: 'crepusculo_violeta', nombre: 'Crepúsculo Violeta', semilla: '#d77dff' },
  { id: 'cobalto_night', nombre: 'Cobalto Nocturno', semilla: '#7ab0ff' },
  { id: 'menta_fresh', nombre: 'Menta Fresh', semilla: '#1abc9c' },
  { id: 'carbono', nombre: 'Carbono Frío', semilla: '#aab5c8' },
  { id: 'vampiro_royal', nombre: 'Vampiro Royal', semilla: '#c49bff' },
  { id: 'ambar_calido', nombre: 'Ámbar Cálido', semilla: '#ffb073' },
  { id: 'nieve', nombre: 'Nieve', semilla: '#1ab0ff' },
  { id: 'ocean_profundo', nombre: 'Océano Abisal', semilla: '#00bcd4' },
  { id: 'galaxia', nombre: 'Galaxia Púrpura', semilla: '#d580ff' },
  { id: 'desierto_dorado', nombre: 'Desierto Dorado', semilla: '#ffd54f' },
  { id: 'bosque_mistico', nombre: 'Bosque Místico', semilla: '#80cbc4' },
  { id: 'fuego_solar', nombre: 'Fuego Solar', semilla: '#ff8c00' },
  { id: 'sakura_nocturno', nombre: 'Sakura Nocturno', semilla: '#ff80c0' },
  { id: 'glacial', nombre: 'Glaciar Azul', semilla: '#0096c7' },
  { id: 'terminal_verde', nombre: 'Terminal Verde', semilla: '#39ff14' },
  { id: 'sangre_dragon', nombre: 'Sangre de Dragón', semilla: '#ff2020' },
  { id: 'prisma', nombre: 'Prisma', semilla: '#00e5c8' },
  { id: 'lava', nombre: 'Lava Negra', semilla: '#ff6600' },
  { id: 'sepia', nombre: 'Sepia Imperial', semilla: '#8b5e3c' },
  { id: 'medianoche', nombre: 'Medianoche Azul', semilla: '#4888b8' },
  { id: 'esmeralda', nombre: 'Esmeralda', semilla: '#00e080' },
  { id: 'titanio', nombre: 'Titanio', semilla: '#8cb4c8' },
  { id: 'coral_sunrise', nombre: 'Coral Amanecer', semilla: '#e84c2c' },
  { id: 'indigo_profundo', nombre: 'Índigo Profundo', semilla: '#8080ff' },
  { id: 'aurora_rosa', nombre: 'Aurora Rosa', semilla: '#ff40ff' },
  { id: 'cafe_nocturno', nombre: 'Café Nocturno', semilla: '#c49a50' },
  { id: 'obsidiana_neon', nombre: 'Obsidiana Neón', semilla: '#20f0ff' },
  { id: 'hielo_oled', nombre: 'Hielo OLED', semilla: '#8ee8ff' },
  { id: 'blanco_editorial', nombre: 'Blanco Editorial', semilla: '#1f6feb' },
  { id: 'oro_negro', nombre: 'Oro Negro', semilla: '#f4c84a' },
  { id: 'jade_nocturno', nombre: 'Jade Nocturno', semilla: '#35f0a0' },
  { id: 'plasma_morado', nombre: 'Plasma Morado', semilla: '#d95cff' },
  { id: 'amanecer_sintetico', nombre: 'Amanecer Sintético', semilla: '#ff7a59' },
  { id: 'tinta_marina', nombre: 'Tinta Marina', semilla: '#4da3ff' },
  { id: 'frambuesa_dark', nombre: 'Frambuesa Dark', semilla: '#ff4f93' },
  { id: 'cielo_coral', nombre: 'Cielo Coral', semilla: '#ff6b58' },
  { id: 'violeta_laser', nombre: 'Violeta Láser', semilla: '#9b7cff' },
  { id: 'acero_azul', nombre: 'Acero Azul', semilla: '#7fb6d6' },
  { id: 'rosa_polar', nombre: 'Rosa Polar', semilla: '#c65acb' },
  { id: 'circuito_verde', nombre: 'Circuito Verde', semilla: '#48ff6a' },
  { id: 'ultra_violeta', nombre: 'Ultra Violeta', semilla: '#bf5cff' },
  { id: 'marfil_grafito', nombre: 'Marfil Grafito', semilla: '#2f6f7e' },
  { id: 'noche_arcade', nombre: 'Noche Arcade', semilla: '#00d9ff' },
  { id: 'neon_citrico', nombre: 'Neón Cítrico', semilla: '#d7ff3f' },
  { id: 'cosmic_latte', nombre: 'Latte Cósmico', semilla: '#d4a574' },
  { id: 'turquesa_electrica', nombre: 'Turquesa Eléctrica', semilla: '#00e0e8' },
  { id: 'magma_violeta', nombre: 'Magma Violeta', semilla: '#ff40c0' },
  { id: 'bruma_artica', nombre: 'Bruma Ártica', semilla: '#70c0d0' },
  { id: 'cobre_oxidado', nombre: 'Cobre Oxidado', semilla: '#c87840' },
  { id: 'sombra_lima', nombre: 'Sombra Lima', semilla: '#a8e840' },
  { id: 'zafiro_medianoche', nombre: 'Zafiro Medianoche', semilla: '#5080e0' },
  { id: 'rosa_quimera', nombre: 'Rosa Quimera', semilla: '#ff5090' },
  { id: 'grafito_radioactivo', nombre: 'Grafito Radioactivo', semilla: '#90e040' }
];

/** El acento de fábrica: el tema por defecto de la V1, `negro_puro`. */
export const ACENTO_POR_DEFECTO: Acento = ACENTOS[0] as Acento;

/** El acento de la V1 con ese id, o el de fábrica si ya no existe. */
export function acentoPorId(id: string | null | undefined): Acento {
  return ACENTOS.find((a) => a.id === id) ?? ACENTO_POR_DEFECTO;
}
