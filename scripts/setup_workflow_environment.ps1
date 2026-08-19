#Requires -Version 5.1
<# Idempotent checker/installer for the Windows + WSL drone workflow. #>
param(
    [ValidateSet('check', 'install')][string]$Mode = 'check',
    [string]$PerceptionPython = 'python',
    [string]$AirSimClientPath = '',
    [string]$AirSimSettings = '',
    [string]$QgcExecutable = '',
    [string]$Ue4Project = '',
    [string]$WslDistro = 'Ubuntu-22.04',
    [string]$WslUser = 'hw',
    [string]$RosWorkspace = '/home/hw/hw-ros2/ros2',
    [string]$Px4Dir = '/home/hw/px4v1.15.2',
    [string]$MicroXrceAgent = '/home/hw/Micro-XRCE-DDS-Agent/build/MicroXRCEAgent'
)

$ErrorActionPreference = 'Stop'
$Workspace = Split-Path -Parent $PSScriptRoot
$ToolsRoot = Join-Path $Workspace '.tools'

function Write-SetupStatus {
    param([string]$Component, [string]$Status, [string]$Detail, [string]$SuggestedPath = '')
    $payload = [ordered]@{
        component = $Component; status = $Status; detail = $Detail
    }
    if (-not [string]::IsNullOrWhiteSpace($SuggestedPath)) {
        $payload.suggested_path = $SuggestedPath
    }
    Write-Output "GUI_SETUP $($payload | ConvertTo-Json -Compress)"
}

function Convert-ToWslPath {
    param([string]$WindowsPath)
    $full = [IO.Path]::GetFullPath($WindowsPath)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "WSL conversion requires a drive path: $full"
    }
    return "/mnt/$($Matches[1].ToLower())/$($Matches[2].Replace('\', '/'))"
}

function Find-Qgc {
    $candidates = @(
        $QgcExecutable,
        (Join-Path $Workspace '..\QGroundControl\bin\QGroundControl.exe'),
        'C:\Program Files\QGroundControl\QGroundControl.exe',
        'D:\QGC\QGroundControl\bin\QGroundControl.exe'
    )
    return $candidates | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_) -and (Test-Path -LiteralPath $_ -PathType Leaf)
    } | Select-Object -First 1
}

function Test-Workflow {
    if (Test-Path -LiteralPath $PerceptionPython -PathType Leaf) {
        Write-SetupStatus 'python' 'pass' $PerceptionPython
    } else {
        Write-SetupStatus 'python' 'fail' "Perception Python not found: $PerceptionPython"
    }
    if ((Test-Path -LiteralPath $PerceptionPython -PathType Leaf) -and
            (Test-Path -LiteralPath $AirSimClientPath -PathType Container)) {
        $checker = Join-Path $PSScriptRoot 'check_airsim_python.py'
        & $PerceptionPython $checker --airsim-client $AirSimClientPath 2>&1 | ForEach-Object { Write-Output $_ }
        if ($LASTEXITCODE -eq 0) {
            Write-SetupStatus 'airsim_python' 'pass' 'AirSim PythonClient and RPC dependencies are importable'
        } else {
            Write-SetupStatus 'airsim_python' 'fail' 'AirSim Python dependencies are incomplete; run repair'
        }
    } else {
        Write-SetupStatus 'airsim_python' 'fail' "AirSim PythonClient not found: $AirSimClientPath"
    }
    if (-not [string]::IsNullOrWhiteSpace($Ue4Project) -and (Test-Path -LiteralPath $Ue4Project)) {
        $plugin = Join-Path (Split-Path -Parent $Ue4Project) 'Plugins\AirSim'
        if (Test-Path $plugin) {
            Write-SetupStatus 'airsim_ue4' 'pass' "AirSim project plugin found: $plugin"
        } else {
            Write-SetupStatus 'airsim_ue4' 'warning' 'Plugins\AirSim was not found; verify project integration'
        }
    }
    $qgc = Find-Qgc
    if ($qgc) { Write-SetupStatus 'qgc' 'pass' $qgc $qgc }
    else { Write-SetupStatus 'qgc' 'fail' 'QGroundControl was not found' }

    $distros = ((& wsl.exe --list --quiet 2>$null) -join "`n") -replace "`0", ''
    if ($distros -notmatch [regex]::Escape($WslDistro)) {
        Write-SetupStatus 'wsl' 'fail' "WSL distribution is not installed: $WslDistro"
        return
    }
    Write-SetupStatus 'wsl' 'pass' $WslDistro
    $setupScript = Convert-ToWslPath (Join-Path $PSScriptRoot 'setup_wsl_environment.sh')
    $projectRoot = Convert-ToWslPath $Workspace
    & wsl.exe -d $WslDistro -u root -- bash $setupScript check $WslUser `
        $RosWorkspace $Px4Dir $MicroXrceAgent $projectRoot
    if ($LASTEXITCODE -ne 0) {
        Write-SetupStatus 'wsl_workflow' 'fail' "WSL check returned $LASTEXITCODE"
    }
}

if ($Mode -eq 'check') {
    Test-Workflow
    exit 0
}

New-Item -ItemType Directory -Force -Path $ToolsRoot | Out-Null
if (-not (Test-Path -LiteralPath $AirSimClientPath -PathType Container)) {
    $airSimRoot = Join-Path $ToolsRoot 'AirSim'
    if (-not (Test-Path -LiteralPath $airSimRoot -PathType Container)) {
        Write-SetupStatus 'airsim_download' 'running' 'Downloading AirSim v1.8.1 source'
        & git clone --branch v1.8.1 --depth 1 https://github.com/microsoft/AirSim.git $airSimRoot
        if ($LASTEXITCODE -ne 0) { throw "AirSim clone failed with exit code $LASTEXITCODE" }
    }
    $AirSimClientPath = Join-Path $airSimRoot 'PythonClient'
    Write-SetupStatus 'airsim_download' 'pass' $AirSimClientPath $AirSimClientPath
}

if (-not [string]::IsNullOrWhiteSpace($AirSimSettings) -and (Test-Path -LiteralPath $AirSimSettings)) {
    $settingsTarget = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'AirSim\settings.json'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $settingsTarget) | Out-Null
    if (Test-Path -LiteralPath $settingsTarget) {
        $backup = "$settingsTarget.backup.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        Copy-Item -LiteralPath $settingsTarget -Destination $backup
    }
    Copy-Item -LiteralPath $AirSimSettings -Destination $settingsTarget -Force
    Write-SetupStatus 'airsim_settings' 'pass' "Applied: $settingsTarget"
}

$qgc = Find-Qgc
if (-not $qgc) {
    $downloadDir = Join-Path $ToolsRoot 'downloads'
    New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
    $installer = Join-Path $downloadDir 'QGroundControl-installer.exe'
    Write-SetupStatus 'qgc_download' 'running' 'Downloading the stable QGroundControl installer'
    Invoke-WebRequest 'https://d176tv9ibo4jno.cloudfront.net/latest/QGroundControl-installer.exe' -OutFile $installer
    Write-SetupStatus 'qgc_download' 'warning' 'Complete QGC setup in the installer window'
    Start-Process -FilePath $installer -Wait
}

$distros = ((& wsl.exe --list --quiet 2>$null) -join "`n") -replace "`0", ''
if ($distros -notmatch [regex]::Escape($WslDistro)) {
    Write-SetupStatus 'wsl_install' 'running' "Installing $WslDistro"
    & wsl.exe --install -d $WslDistro
    Write-SetupStatus 'wsl_install' 'warning' 'WSL installation was submitted; restart Windows and run setup again'
    exit 0
}

$setupScript = Convert-ToWslPath (Join-Path $PSScriptRoot 'setup_wsl_environment.sh')
$projectRoot = Convert-ToWslPath $Workspace
& wsl.exe -d $WslDistro -u root -- bash $setupScript install $WslUser `
    $RosWorkspace $Px4Dir $MicroXrceAgent $projectRoot
if ($LASTEXITCODE -ne 0) { throw "WSL workflow setup failed with exit code $LASTEXITCODE" }
Test-Workflow
