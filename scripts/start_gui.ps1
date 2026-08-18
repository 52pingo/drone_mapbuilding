param(
    [string]$Python = '',
    [string]$Config = '',
    [switch]$SmokeTest
)

$ErrorActionPreference = 'Stop'
$Workspace = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Python)) {
    $VenvPython = Join-Path $Workspace '.venv-gui\Scripts\python.exe'
    $Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { 'python' }
}

$Arguments = @('-m', 'drone_gui')
if (-not [string]::IsNullOrWhiteSpace($Config)) {
    $Arguments += @('--config', $Config)
}
if ($SmokeTest) {
    $Arguments += '--smoke-test'
}

Push-Location $Workspace
try {
    & $Python @Arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
