pragma Singleton
import QtQuick

QtObject {
    readonly property int iconXs: 14
    readonly property int iconSm: 16
    readonly property int iconMd: 18
    readonly property int iconLg: 22
    readonly property int iconXl: 28

    readonly property int fontSizeXs: 10
    readonly property int fontSizeSm: 11
    readonly property int fontSizeMd: 12
    readonly property int fontSizeBase: 13   // texto de cuerpo predominante
    readonly property int fontSizeLg: 14
    readonly property int fontSizeXl: 16
    readonly property int fontSize2xl: 18    // subtítulos de sección
    readonly property int fontSizeDisplay: 27

    readonly property int spacing2: 2
    readonly property int spacing4: 4
    readonly property int spacing6: 6
    readonly property int spacing8: 8
    readonly property int spacing10: 10
    readonly property int spacing12: 12
    readonly property int spacing14: 14
    readonly property int spacing16: 16
    readonly property int spacing20: 20
    readonly property int spacing24: 24
    readonly property int spacing32: 32

    readonly property int radiusSm: 8
    readonly property int radiusMd: 10
    readonly property int radiusLg: 14
    readonly property int radiusPill: 20

    readonly property int durationFast: 120
    readonly property int durationBase: 160
    readonly property int durationSlow: 220

    readonly property int controlHeightSm: 30
    readonly property int controlHeightMd: 36
    readonly property int controlHeightLg: 44
    readonly property int controlHeightXl: 52

    readonly property int breakpointCompact: 1120
    readonly property int breakpointMedium: 1440

    readonly property real shadowOpacitySoft: 0.12
    readonly property real shadowOpacityStrong: 0.24
}
