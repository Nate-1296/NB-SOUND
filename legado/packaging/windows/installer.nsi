; ============================================================================
;  installer.nsi
;
;  Script NSIS para construir el instalador .exe de NB Sound en Windows.
;
;  Compilacion: makensis /DVERSION=1.0.0 /DSRC_DIR=..\..\dist\nb_sound installer.nsi
;
;  Variables esperadas (definidas con /D en linea de comandos):
;    VERSION       Version del producto, p.ej. 1.0.0
;    SRC_DIR       Ruta absoluta a la salida de PyInstaller (dist\nb_sound)
; ============================================================================

!ifndef VERSION
  !define VERSION "1.0.0"
!endif

!ifndef SRC_DIR
  !error "Define SRC_DIR via /DSRC_DIR=ruta\\al\\bundle al invocar makensis"
!endif

!define APP_NAME      "NB Sound"
!define APP_ID        "NBSound"
!define PUBLISHER     "Nathan"
!define APP_URL       "https://github.com/Nate-1296/NB-SOUND"
!define APP_EXE       "nb_sound.exe"
!define UNINST_KEY    "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"

SetCompressor /SOLID lzma

Name "${APP_NAME} ${VERSION}"
OutFile "..\..\dist\nb-sound-windows-x64-setup.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "Software\${APP_ID}" "InstallDir"
RequestExecutionLevel admin
Unicode true
ShowInstDetails show
ShowUnInstDetails show

; VIProductVersion requiere formato estricto X.X.X.X.
; Se inyecta desde el workflow como VIVERSION (ya sanitizado a X.X.X.X).
; Si no se define (builds manuales sin sanitizar), se omite.
!ifdef VIVERSION
  VIProductVersion "${VIVERSION}"
!endif
VIAddVersionKey "ProductName"     "${APP_NAME}"
VIAddVersionKey "CompanyName"     "${PUBLISHER}"
VIAddVersionKey "FileDescription" "Catalogador y reproductor de musica local"
VIAddVersionKey "FileVersion"     "${VERSION}"
VIAddVersionKey "ProductVersion"  "${VERSION}"
VIAddVersionKey "LegalCopyright"  "GPL-3.0-or-later"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON   "..\..\ui\qml\assets\logo\logo.ico"
!define MUI_UNICON "..\..\ui\qml\assets\logo\logo.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Ejecutar ${APP_NAME} al cerrar"
!define MUI_FINISHPAGE_RUN_FUNCTION "LaunchApp"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Ver guia rapida"
!define MUI_FINISHPAGE_SHOWREADME "${APP_URL}#inicio-rápido"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Spanish"
!insertmacro MUI_LANGUAGE "English"

; ----------------------------------------------------------------------------
;  Deteccion de VLC instalado
;
;  VLC escribe su clave en HKLM\Software\VideoLAN\VLC en el registro de
;  64 bits. Sin SetRegView 64 un NSIS de 32 bits solo lee el registro de
;  32 bits (WOW6432Node), por lo que nunca encuentra una instalacion de
;  VLC 64-bit aunque exista.
; ----------------------------------------------------------------------------

Function DetectarVLC
  ; Leer primero el registro de 64 bits (instalacion estandar de VLC x64)
  SetRegView 64
  ReadRegStr $0 HKLM "Software\VideoLAN\VLC" "InstallDir"
  ${If} $0 != ""
    SetRegView 32
    Return
  ${EndIf}

  ; Luego el registro de 32 bits (VLC x86 en sistema x64)
  SetRegView 32
  ReadRegStr $0 HKLM "Software\VideoLAN\VLC" "InstallDir"
  ${If} $0 != ""
    Return
  ${EndIf}

  ReadRegStr $0 HKLM "Software\WOW6432Node\VideoLAN\VLC" "InstallDir"
  ${If} $0 != ""
    Return
  ${EndIf}

  ReadRegStr $0 HKCU "Software\VideoLAN\VLC" "InstallDir"
  ${If} $0 != ""
    Return
  ${EndIf}

  ; Verificar por libvlc.dll directamente en rutas comunes
  ${If} ${FileExists} "$PROGRAMFILES64\VideoLAN\VLC\libvlc.dll"
    Return
  ${EndIf}
  ${If} ${FileExists} "$PROGRAMFILES\VideoLAN\VLC\libvlc.dll"
    Return
  ${EndIf}

  MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
    "${APP_NAME} requiere VLC instalado para reproducir audio.$\r$\n$\r$\n\
Aun no se detecto VLC en el sistema.$\r$\n$\r$\n\
Instalalo con uno de estos comandos en PowerShell:$\r$\n\
   winget install --id VideoLAN.VLC$\r$\n\
   choco install -y vlc$\r$\n$\r$\n\
O descargalo desde:$\r$\n\
   https://www.videolan.org/vlc/$\r$\n$\r$\n\
Aceptar continua con la instalacion de ${APP_NAME}; Cancelar la aborta." \
    IDOK +2
    Abort
FunctionEnd

; ----------------------------------------------------------------------------
;  Pasos del instalador
; ----------------------------------------------------------------------------

Function .onInit
  ; Si hay una instalacion previa cuyo ejecutable esta en uso (proceso corriendo),
  ; el instalador falla al sobrescribir el .exe. Detectar y pedir al usuario
  ; que cierre la aplicacion antes de continuar.
  ${If} ${FileExists} "$INSTDIR\${APP_EXE}"
    ; Intentar abrir el archivo para escritura: si falla, esta en uso.
    ClearErrors
    FileOpen $1 "$INSTDIR\${APP_EXE}" a
    ${If} ${Errors}
      MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION \
        "${APP_NAME} esta abierto. Cierralo antes de continuar con la instalacion.$\r$\n$\r$\nPresiona Reintentar despues de cerrarlo, o Cancelar para abortar." \
        IDRETRY CheckAgain IDCANCEL AbortInst
      CheckAgain:
        ClearErrors
        FileOpen $1 "$INSTDIR\${APP_EXE}" a
        ${If} ${Errors}
          MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION \
            "${APP_NAME} sigue abierto. Cierralo y presiona Reintentar." \
            IDRETRY CheckAgain IDCANCEL AbortInst
        ${Else}
          FileClose $1
        ${EndIf}
        Goto SkipAbort
      AbortInst:
        Abort
      SkipAbort:
    ${Else}
      FileClose $1
    ${EndIf}
  ${EndIf}
  Call DetectarVLC
FunctionEnd

Section "Aplicacion (requerido)" SecApp
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "${SRC_DIR}\*.*"

  WriteUninstaller "$INSTDIR\uninstall.exe"

  WriteRegStr HKLM "Software\${APP_ID}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "Software\${APP_ID}" "Version"    "${VERSION}"

  WriteRegStr HKLM "${UNINST_KEY}" "DisplayName"        "${APP_NAME}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion"     "${VERSION}"
  WriteRegStr HKLM "${UNINST_KEY}" "Publisher"          "${PUBLISHER}"
  WriteRegStr HKLM "${UNINST_KEY}" "URLInfoAbout"       "${APP_URL}"
  WriteRegStr HKLM "${UNINST_KEY}" "InstallLocation"    "$INSTDIR"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayIcon"        "$INSTDIR\${APP_EXE}"
  WriteRegStr HKLM "${UNINST_KEY}" "UninstallString"    "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "${UNINST_KEY}" "QuietUninstallString" "$INSTDIR\uninstall.exe /S"
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1

  ; Tamano estimado en KB (usado por "Programas y caracteristicas")
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKLM "${UNINST_KEY}" "EstimatedSize" "$0"
SectionEnd

Section "Acceso directo en el Menu Inicio" SecStart
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\Desinstalar.lnk" "$INSTDIR\uninstall.exe"
SectionEnd

Section "Acceso directo en el Escritorio" SecDesktop
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

LangString DESC_SecApp     ${LANG_SPANISH} "Archivos principales de la aplicacion."
LangString DESC_SecStart   ${LANG_SPANISH} "Crea entradas en el Menu Inicio."
LangString DESC_SecDesktop ${LANG_SPANISH} "Crea un acceso directo en el Escritorio."

LangString DESC_SecApp     ${LANG_ENGLISH} "Main application files."
LangString DESC_SecStart   ${LANG_ENGLISH} "Creates Start Menu shortcuts."
LangString DESC_SecDesktop ${LANG_ENGLISH} "Creates a Desktop shortcut."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecApp}     $(DESC_SecApp)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecStart}   $(DESC_SecStart)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_SecDesktop)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function LaunchApp
  ExecShell "" "$INSTDIR\${APP_EXE}"
FunctionEnd

; ----------------------------------------------------------------------------
;  Desinstalador
; ----------------------------------------------------------------------------

Section "Uninstall"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\Desinstalar.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"

  RMDir /r "$INSTDIR"

  DeleteRegKey HKLM "${UNINST_KEY}"
  DeleteRegKey HKLM "Software\${APP_ID}"
SectionEnd
