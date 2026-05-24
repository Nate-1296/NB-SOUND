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

$ZipName = 'nb_sound-windows-x64.zip'
$ZipPath = Join-Path 'dist' $ZipName
Write-Host "[nb_sound] Empaquetando $ZipPath..."
Compress-Archive -Path "$ArtifactDir\*" -DestinationPath $ZipPath -Force

$Hash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash
"$Hash  $ZipName" | Out-File -Encoding ASCII "$ZipPath.sha256"
Write-Host "[nb_sound] OK: $ZipPath"
