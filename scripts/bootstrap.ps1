[CmdletBinding()]
param(
    [ValidateSet("cpu", "cu128")]
    [string]$TorchVariant = "cu128",

    [string]$PythonLauncher = "py",

    [switch]$RuntimeOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

Push-Location $ProjectRoot
try {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Write-Host "Creating .venv with Python 3.12..."
        if ((Split-Path -Leaf $PythonLauncher) -match '^py(?:\.exe)?$') {
            & $PythonLauncher -3.12 -m venv $VenvDir
        }
        else {
            & $PythonLauncher -m venv $VenvDir
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create .venv with $PythonLauncher."
        }
    }

    $PythonVersion = (& $VenvPython -c "import sys; print('.'.join(map(str, sys.version_info[:3])))").Trim()
    if (-not $PythonVersion.StartsWith("3.12.")) {
        throw ".venv uses Python $PythonVersion; this baseline requires Python 3.12.x."
    }
    if ($PythonVersion -ne "3.12.13") {
        Write-Warning "Baseline was verified with Python 3.12.13; found $PythonVersion."
    }

    $TorchIndex = "https://download.pytorch.org/whl/$TorchVariant"
    Write-Host "Installing PyTorch 2.11.0 ($TorchVariant)..."
    & $VenvPython -m pip install torch==2.11.0 torchvision==0.26.0 --index-url $TorchIndex
    if ($LASTEXITCODE -ne 0) {
        throw "PyTorch installation failed."
    }

    $RequirementFile = if ($RuntimeOnly) { "requirements.txt" } else { "requirements-dev.txt" }
    Write-Host "Installing $RequirementFile..."
    & $VenvPython -m pip install --requirement $RequirementFile
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed."
    }

    Write-Host "Environment ready: $VenvDir"
    Write-Host "Run .\scripts\verify.ps1 to validate it."
}
finally {
    Pop-Location
}
