param(
    [string]$Python = '',
    [switch]$SkipArchive
)

$ErrorActionPreference = 'Stop'
$Workspace = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $Workspace '.venv-gui\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "GUI Python not found: $Python"
}

$Spec = Join-Path $Workspace 'drone_mapbuilding.spec'
Push-Location $Workspace
try {
    & $Python -m PyInstaller --noconfirm --clean $Spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
    $Target = Join-Path $Workspace 'dist\DroneMapbuilding'
    if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
        throw "Packaged directory was not created: $Target"
    }
    foreach ($name in @('scripts', 'config', 'docs')) {
        $sourceDirectory = Join-Path $Workspace $name
        $targetDirectory = Join-Path $Target $name
        New-Item -ItemType Directory -Force -Path $targetDirectory | Out-Null
        foreach ($file in Get-ChildItem -LiteralPath $sourceDirectory -File) {
            Copy-Item -LiteralPath $file.FullName -Destination $targetDirectory -Force
        }
    }
    foreach ($name in @('README.md', 'requirements-gui.txt', 'requirements-build.txt')) {
        Copy-Item -LiteralPath (Join-Path $Workspace $name) -Destination $Target -Force
    }
    $requiredRuntimeFiles = @(
        'scripts\launch_ue4.ps1',
        'scripts\run_citypark_semantic_mission.ps1',
        'scripts\run_citypark_loop_inner.sh',
        'scripts\semantic_perception.py',
        'scripts\session_archive.py',
        'config\gui_config.example.json'
    )
    foreach ($relativePath in $requiredRuntimeFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $Target $relativePath) -PathType Leaf)) {
            throw "Packaged runtime file is missing: $relativePath"
        }
    }
    if (-not $SkipArchive) {
        $Archive = Join-Path $Workspace 'dist\DroneMapbuilding-win64.zip'
        Compress-Archive -Path (Join-Path $Target '*') -DestinationPath $Archive -Force
        Write-Output "PACKAGE_ARCHIVE $Archive"
    }
    Write-Output "PACKAGE_DIR $Target"
}
finally {
    Pop-Location
}
