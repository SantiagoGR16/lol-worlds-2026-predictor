# Instalador del Proyecto ML LOL para Windows.
# Instala (si faltan) Python 3.12 y Node.js LTS con winget, crea el entorno virtual
# FUERA de OneDrive, instala dependencias, corre los tests y compila la web.
$ErrorActionPreference = "Continue"
$Root = $PSScriptRoot
$Log  = Join-Path $Root "instalar_log.txt"
Start-Transcript -Path $Log -Force | Out-Null
# Fuera de OneDrive para no sincronizar miles de archivos. Se usa %USERPROFILE% y no
# %LOCALAPPDATA% porque Windows virtualiza AppData para apps empaquetadas (MSIX).
$Venv = Join-Path $env:USERPROFILE ".lolpred\.venv"

function Refrescar-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
}
function Paso($t) { Write-Host "`n==== $t ====" -ForegroundColor Cyan }

function Buscar-Python {
    # Devuelve la ruta de un python >= 3.11 (evita el atajo falso de Microsoft Store)
    $cands = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in "3.12","3.13","3.11") {
            # vía cmd para que el stderr de py (versión ausente) no se registre como error en PS 5.1
            $p = cmd /c "py -$v -c ""import sys;print(sys.executable)"" 2>nul"
            if ($LASTEXITCODE -eq 0 -and $p) { return $p.Trim() }
        }
    }
    $cands += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object FullName
    $cands += Get-ChildItem "C:\Program Files\Python3*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object FullName
    $g = Get-Command python -ErrorAction SilentlyContinue
    if ($g -and $g.Source -notlike "*WindowsApps*") { $cands += $g.Source }
    foreach ($c in $cands) {
        $ok = & $c -c "import sys;print(sys.version_info>=(3,11))" 2>$null
        if ($ok -eq "True") { return $c }
    }
    return $null
}

Paso "1/6 Python"
$py = Buscar-Python
if (-not $py) {
    Write-Host "Python >= 3.11 no encontrado. Instalando Python 3.12 con winget..."
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    Refrescar-Path
    $py = Buscar-Python
}
if (-not $py) { Write-Host "ERROR: no se pudo instalar Python. Instálalo desde python.org y vuelve a correr esto." -ForegroundColor Red; Stop-Transcript; exit 1 }
& $py --version

Paso "2/6 Node.js"
Refrescar-Path
$nodeOk = $false
if (Get-Command node -ErrorAction SilentlyContinue) {
    # Angular 22 exige node ^22.22.3 || ^24.15.0 || >=26.0.0 (campo engines de @angular/core)
    $p = (& node --version).TrimStart("v").Split(".") | ForEach-Object { [int]$_ }
    if (($p[0] -eq 22 -and $p[1] -ge 22) -or ($p[0] -eq 24 -and $p[1] -ge 15) -or ($p[0] -ge 26)) { $nodeOk = $true }
}
if (-not $nodeOk) {
    Write-Host "Node compatible con Angular 22 no encontrado. Instalando Node.js LTS con winget (puede pedir permiso de administrador)..."
    winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    Refrescar-Path
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Write-Host "ERROR: Node no quedó instalado." -ForegroundColor Red; Stop-Transcript; exit 1 }
node --version; npm --version

Paso "3/6 Entorno virtual de Python en $Venv"
if (-not (Test-Path "$Venv\Scripts\python.exe")) { & $py -m venv $Venv }
$vpy = "$Venv\Scripts\python.exe"
& $vpy -m pip install --upgrade pip
& $vpy -m pip install -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR instalando paquetes de Python" -ForegroundColor Red; Stop-Transcript; exit 1 }

Paso "4/6 Tests (incluye test_no_leakage)"
Push-Location $Root
$env:PYTHONIOENCODING = "utf-8"
& $vpy -m pytest -q
Write-Host "pytest exit code: $LASTEXITCODE"

Paso "5/6 Predicción de la serie"
& $vpy scripts\predict_series.py
Write-Host "predict exit code: $LASTEXITCODE"
Pop-Location

Paso "6/6 Web Angular (npm ci + build)"
Push-Location (Join-Path $Root "web")
npm ci --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { npm install --no-audit --no-fund }
npm run build   # prebuild regenera assets/img/index.json
Write-Host "ng build exit code: $LASTEXITCODE"
Pop-Location

Write-Host "`nLISTO. Usa ver_tablero.bat para abrir la web y correr_modelo.bat para re-entrenar." -ForegroundColor Green
Stop-Transcript | Out-Null
