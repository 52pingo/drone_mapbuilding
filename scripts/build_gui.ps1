param(
    [string]$Python = '',
    [switch]$SkipArchive,
    [switch]$NoClean,
    [string]$DistRoot = ''
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
if ([string]::IsNullOrWhiteSpace($DistRoot)) {
    $DistRoot = Join-Path $Workspace 'dist'
}
elseif (-not [System.IO.Path]::IsPathRooted($DistRoot)) {
    $DistRoot = Join-Path $Workspace $DistRoot
}
New-Item -ItemType Directory -Force -Path $DistRoot | Out-Null
Push-Location $Workspace
try {
    $pyInstallerArgs = @('-m', 'PyInstaller', '--noconfirm')
    if (-not $NoClean) { $pyInstallerArgs += '--clean' }
    $pyInstallerArgs += @('--distpath', $DistRoot)
    $pyInstallerArgs += $Spec
    & $Python @pyInstallerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
    $Target = Join-Path $DistRoot 'DroneMapbuilding'
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
    # session_archive.py is executed by the separately configured perception
    # Python, not by the frozen EXE.  Ship its small pure-Python package
    # surface so that imports work from a portable distribution.
    $externalPackageTarget = Join-Path $Target 'drone_gui'
    New-Item -ItemType Directory -Force -Path $externalPackageTarget | Out-Null
    foreach ($name in @('__init__.py', 'session_archive.py', 'report_export.py')) {
        Copy-Item -LiteralPath (Join-Path $Workspace "drone_gui\$name") `
            -Destination $externalPackageTarget -Force
    }
    $rosSource = Join-Path $Workspace 'ros2_ws'
    Copy-Item -LiteralPath $rosSource -Destination (Join-Path $Target 'ros2_ws') -Recurse -Force

    $vendorCandidates = @(
        (Join-Path $Workspace '.tools\airsim_rpc'),
        (Join-Path (Split-Path -Parent $Workspace) '.tools\airsim_rpc')
    )
    $vendorSource = $vendorCandidates | Where-Object {
        Test-Path -LiteralPath $_ -PathType Container
    } | Select-Object -First 1
    if (-not $vendorSource) {
        throw 'AirSim RPC compatibility dependencies are missing (.tools\airsim_rpc)'
    }
    $vendorTarget = Join-Path $Target '.tools\airsim_rpc'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $vendorTarget) | Out-Null
    Copy-Item -LiteralPath $vendorSource -Destination $vendorTarget -Recurse -Force

    foreach ($name in @('README.md', 'requirements-gui.txt', 'requirements-build.txt', 'requirements-perception.txt')) {
        Copy-Item -LiteralPath (Join-Path $Workspace $name) -Destination $Target -Force
    }
    $requiredRuntimeFiles = @(
        'scripts\launch_ue4.ps1',
        'scripts\verify_airsim_runtime.py',
        'scripts\setup_workflow_environment.ps1',
        'scripts\setup_wsl_environment.sh',
        'scripts\run_citypark_semantic_mission.ps1',
        'scripts\run_citypark_loop_inner.sh',
        'scripts\semantic_perception.py',
        'scripts\session_archive.py',
        'drone_gui\session_archive.py',
        'drone_gui\report_export.py',
        'config\gui_config.example.json',
        '.tools\airsim_rpc\msgpackrpc\__init__.py',
        'ros2_ws\src\hw_insight\package.xml'
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
