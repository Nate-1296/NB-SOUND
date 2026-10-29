import {
  argbFromHex,
  ContrastCurve,
  DynamicColor,
  DynamicScheme,
  Hct,
  MaterialDynamicColors,
  SchemeTonalSpot,
  TonalPalette
} from '@ktibow/material-color-utilities-nightly';

const materialColors = new MaterialDynamicColors();

const onOnPrimary = DynamicColor.fromPalette({
  name: 'on_on_primary',
  palette: (s) => s.primaryPalette,
  background: () => materialColors.onPrimary(),
  contrastCurve: () => new ContrastCurve(6, 6, 7, 11)
});

const primaryContainerSubtle = DynamicColor.fromPalette({
  name: 'primary_container_subtle',
  palette: (s) => s.primaryPalette,
  isBackground: true,
  background: (s) => materialColors.highestSurface(s),
  contrastCurve: () => undefined
});
const onPrimaryContainerSubtle = DynamicColor.fromPalette({
  name: 'on_primary_container_subtle',
  palette: (s) => s.primaryPalette,
  background: () => primaryContainerSubtle,
  contrastCurve: () => new ContrastCurve(6, 6, 7, 11)
});

const secondaryContainerSubtle = DynamicColor.fromPalette({
  name: 'secondary_container_subtle',
  palette: (s) => s.secondaryPalette,
  isBackground: true,
  background: (s) => materialColors.highestSurface(s),
  contrastCurve: () => undefined
});
const onSecondaryContainerSubtle = DynamicColor.fromPalette({
  name: 'on_secondary_container_subtle',
  palette: (s) => s.secondaryPalette,
  background: () => secondaryContainerSubtle,
  contrastCurve: () => new ContrastCurve(6, 6, 7, 11)
});

const tertiaryContainerSubtle = DynamicColor.fromPalette({
  name: 'tertiary_container_subtle',
  palette: (s) => s.tertiaryPalette,
  isBackground: true,
  background: (s) => materialColors.highestSurface(s),
  contrastCurve: () => undefined
});
const onTertiaryContainerSubtle = DynamicColor.fromPalette({
  name: 'on_tertiary_container_subtle',
  palette: (s) => s.tertiaryPalette,
  background: () => tertiaryContainerSubtle,
  contrastCurve: () => new ContrastCurve(6, 6, 7, 11)
});

const errorContainerSubtle = DynamicColor.fromPalette({
  name: 'error_container_subtle',
  palette: (s) => s.errorPalette,
  isBackground: true,
  background: (s) => materialColors.highestSurface(s),
  contrastCurve: () => undefined
});
const onErrorContainerSubtle = DynamicColor.fromPalette({
  name: 'on_error_container_subtle',
  palette: (s) => s.errorPalette,
  background: () => errorContainerSubtle,
  contrastCurve: () => new ContrastCurve(6, 6, 7, 11)
});

const colors = [
  ...materialColors.allColors.filter((c) => c.name !== 'background' && c.name !== 'on_background'),
  materialColors.shadow(),
  materialColors.scrim(),
  onOnPrimary,
  primaryContainerSubtle,
  onPrimaryContainerSubtle,
  secondaryContainerSubtle,
  onSecondaryContainerSubtle,
  tertiaryContainerSubtle,
  onTertiaryContainerSubtle,
  errorContainerSubtle,
  onErrorContainerSubtle
];

/**
 * Deriva la paleta de Material 3 de una semilla.
 *
 * `contraste` es el nivel de contraste del propio Material, de -1 a 1, y es lo
 * que hace de verdad el alto contraste: recalcula cada par de colores contra su
 * fondo con una curva más exigente. Hasta el 2026-09-10 esto no se pasaba -iba
 * fijo en 0- y el alto contraste se simulaba cambiando la semilla por blanco o
 * negro puro. Medido, aquello no subía el contraste ni una décima -14,36 con y
 * sin él sobre Gabinete- y encima le cambiaba el tono al tema, porque una
 * semilla acromática no tiene matiz del que partir y sale el que sea.
 */
export function generarVariablesM3(
  semillaHex: string,
  oscuro: boolean,
  contraste = 0,
  neutrosGrises = false
): Record<string, string> {
  const argb = argbFromHex(semillaHex);
  const tonal = new SchemeTonalSpot(Hct.fromInt(argb), oscuro, contraste);

  /*
   * **Grises sin matiz, y el color solo en el acento.**
   *
   * Material deriva de la semilla cinco paletas y tiñe con ella hasta las
   * neutras: con una semilla naranja, el fondo sale café. Para un tema que pide
   * grises de verdad se conservan la primaria, la terciaria y la de error, y las
   * neutras y la secundaria pasan a croma cero. La secundaria va con ellas porque
   * es la de los contenedores de selección —chips, destinos activos de la
   * biblioteca—, y teñida devolvería el matiz por la puerta de al lado.
   *
   * Se descartó `SchemeMonochrome`: pone a croma cero también la primaria, y el
   * acento es justo lo que tiene que conservar su color.
   */
  const scheme = neutrosGrises
    ? new DynamicScheme({
        sourceColorHct: tonal.sourceColorHct,
        variant: tonal.variant,
        contrastLevel: contraste,
        isDark: oscuro,
        platform: tonal.platform,
        specVersion: tonal.specVersion,
        primaryPalette: tonal.primaryPalette,
        secondaryPalette: TonalPalette.fromHueAndChroma(tonal.sourceColorHct.hue, 0),
        tertiaryPalette: tonal.tertiaryPalette,
        neutralPalette: TonalPalette.fromHueAndChroma(tonal.sourceColorHct.hue, 0),
        neutralVariantPalette: TonalPalette.fromHueAndChroma(tonal.sourceColorHct.hue, 0),
        errorPalette: tonal.errorPalette
      })
    : tonal;

  const vars: Record<string, string> = {};
  for (const c of colors) {
    const valArgb = c.getArgb(scheme);
    const kebabCase = c.name.replaceAll('_', '-');

    const rgb = valArgb & 0xffffff;
    const hex = rgb.toString(16).padStart(6, '0');
    let hexStr = `#${hex}`;
    if (hex[0] === hex[1] && hex[2] === hex[3] && hex[4] === hex[5]) {
      hexStr = `#${hex[0]}${hex[2]}${hex[4]}`;
    }
    vars[`--m3c-${kebabCase}`] = hexStr;
  }

  /*
   * `on-surface-container` no lo deriva Material: lo pide `NavigationRailToggle`
   * de m3-svelte y la propia librería no lo define en ninguna parte, así que
   * quien use ese componente pinta con una variable que no existe. Se alía a
   * `on-surface`, que es el color que Material destina a cualquiera de sus
   * superficies contenedoras. Cuesta una línea y cierra un agujero que solo se
   * vería el día que alguien monte el riel.
   */
  const onSurface = vars['--m3c-on-surface'];
  if (onSurface) vars['--m3c-on-surface-container'] = onSurface;

  return vars;
}
