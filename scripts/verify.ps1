[CmdletBinding()]
param(
    [switch]$IncludeTraining
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$UltralyticsConfigDir = Join-Path $ProjectRoot ".ci\ultralytics"
$MatplotlibConfigDir = Join-Path $ProjectRoot ".ci\matplotlib"

if (-not (Test-Path -LiteralPath $Python)) {
    throw ".venv is missing. Run .\scripts\bootstrap.ps1 first."
}

Push-Location $ProjectRoot
try {
    New-Item -ItemType Directory -Force -Path $UltralyticsConfigDir | Out-Null
    New-Item -ItemType Directory -Force -Path $MatplotlibConfigDir | Out-Null
    $env:YOLO_CONFIG_DIR = $UltralyticsConfigDir
    $env:MPLCONFIGDIR = $MatplotlibConfigDir
    $env:MPLBACKEND = "Agg"
    if (-not $env:WINDIR) {
        $env:WINDIR = "C:\Windows"
    }

    & $Python -m pip check
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency graph check failed."
    }

    & $Python -m compileall -q src test train.py tune.py eval.py export.py serve.py validate_data.py gradio_app.py
    if ($LASTEXITCODE -ne 0) {
        throw "Python compilation check failed."
    }

    & $Python -m ruff check .
    if ($LASTEXITCODE -ne 0) {
        throw "Ruff check failed."
    }

    $MarkerExpression = if ($IncludeTraining) { "not gpu" } else { "not gpu and not training" }
    & $Python -m pytest -m $MarkerExpression
    if ($LASTEXITCODE -ne 0) {
        throw "Test suite failed."
    }
}
finally {
    Pop-Location
}
