# =============================================================================
# packaging/windows/build.ps1
#
# Genera el bundle Windows con PyInstaller y empaqueta como .zip + SHA256.
#
# Uso (PowerShell):
#   .\packaging\windows\build.ps1
# =============================================================================
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir '..\..')
Set-Location $Root

Write-Host "[nb_sound] Verificando PyInstaller..."
$pyinst = python -m pip show pyinstaller 2>$null
if (-not $pyinst) {
    python -m pip install 'pyinstaller>=6.0'
}

Write-Host "[nb_sound] Limpiando builds previos..."
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist)  { Remove-Item -Recurse -Force dist }

Write-Host "[nb_sound] Generando bundle..."
python -m PyInstaller packaging\windows\nb_sound.spec --noconfirm

$ArtifactDir = 'dist\nb_sound'
if (-not (Test-Path $ArtifactDir)) {
    throw "PyInstaller no produjo $ArtifactDir"
}

# ---------------------------------------------------------------------------
# Firma Authenticode (OPCIONAL).
#
# El .exe ya lleva metadatos de version (CompanyName/ProductName via el spec),
# por lo que el Explorador y UAC muestran un desarrollador. Para ELIMINAR del
# todo el aviso de SmartScreen "editor desconocido" hace falta FIRMAR con un
# certificado de firma de codigo. Si se proveen estas variables de entorno se
# firma automaticamente; si no, se omite sin fallar (build sin firmar valido).
#
#   $env:NB_SIGN_PFX   = ruta al certificado .pfx
#   $env:NB_SIGN_PASS  = contrasena del .pfx
#   $env:NB_SIGN_TS    = (opcional) URL de timestamp, por defecto DigiCert
# ---------------------------------------------------------------------------
function Invoke-FirmaOpcional {
    param([string]$Objetivo)
    if (-not $env:NB_SIGN_PFX) {
        Write-Host "[nb_sound] Firma omitida (define NB_SIGN_PFX/NB_SIGN_PASS para firmar)."
        return
    }
    if (-not (Test-Path $env:NB_SIGN_PFX)) {
        throw "NB_SIGN_PFX apunta a un archivo inexistente: $($env:NB_SIGN_PFX)"
    }
    $ts = if ($env:NB_SIGN_TS) { $env:NB_SIGN_TS } else { 'http://timestamp.digicert.com' }
    Write-Host "[nb_sound] Firmando $Objetivo ..."
    & signtool sign /f $env:NB_SIGN_PFX /p $env:NB_SIGN_PASS `
        /fd SHA256 /tr $ts /td SHA256 /d 'NB Sound' $Objetivo
    if ($LASTEXITCODE -ne 0) { throw "signtool fallo (codigo $LASTEXITCODE) al firmar $Objetivo" }
}

Invoke-FirmaOpcional "$ArtifactDir\nb_sound.exe"

$ZipName = 'nb_sound-windows-x64.zip'
$ZipPath = Join-Path 'dist' $ZipName
Write-Host "[nb_sound] Empaquetando $ZipPath..."
Compress-Archive -Path "$ArtifactDir\*" -DestinationPath $ZipPath -Force

$Hash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash
"$Hash  $ZipName" | Out-File -Encoding ASCII "$ZipPath.sha256"
Write-Host "[nb_sound] OK: $ZipPath"
