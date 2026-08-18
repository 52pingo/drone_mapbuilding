param(
    [string]$Weights = '',
    [double]$Confidence = 0.30,
    [int]$ConfirmFrames = 2,
    [double]$CaptureInterval = 4.0,
    [int]$MaxImagesPerClass = 20,
    [double]$MaxDepthM = 60.0,
    [double]$PerceptionInterval = 0.20,
    [string]$Goals = '181.55,-583.34;-395.53,-409.16;-159.49,25.13;0,0',
    [double]$FlightZ = -15.0,
    [double]$MaxMissionTime = 1200.0,
    [string]$ResultRoot = '',
    [string]$Python = 'C:\Users\29593\anaconda3\envs\deeplearning\python.exe',
    [string]$WslDistro = 'Ubuntu-22.04',
    [string]$WslUser = 'hw'
)

$ErrorActionPreference = 'Stop'
$Workspace = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Weights)) {
    $Weights = Join-Path $Workspace 'best.pt'
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "YOLO Python environment not found: $Python"
}
if (-not (Test-Path -LiteralPath $Weights)) {
    throw "YOLO weights not found: $Weights"
}

if ([string]::IsNullOrWhiteSpace($ResultRoot)) {
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $ResultRoot = Join-Path $Workspace "results\citypark_semantic_$stamp"
}
$ResultRoot = [System.IO.Path]::GetFullPath($ResultRoot)
$SemanticDir = Join-Path $ResultRoot 'detected_classes'
$LiveDir = Join-Path $ResultRoot 'live_feed'
$MapDir = Join-Path $ResultRoot 'live_map'
$StopFile = Join-Path $ResultRoot 'semantic_stop.signal'
$ArchiveScript = Join-Path $PSScriptRoot 'session_archive.py'
New-Item -ItemType Directory -Force -Path $SemanticDir | Out-Null
New-Item -ItemType Directory -Force -Path $LiveDir | Out-Null
New-Item -ItemType Directory -Force -Path $MapDir | Out-Null
if (Test-Path -LiteralPath $StopFile) {
    Remove-Item -LiteralPath $StopFile -Force
}

$archiveInitArgs = @(
    $ArchiveScript, 'init',
    '--root', $ResultRoot,
    '--name', 'CityPark 大环线',
    '--goals', $Goals,
    '--flight-z', $FlightZ.ToString([Globalization.CultureInfo]::InvariantCulture),
    '--max-mission-time', $MaxMissionTime.ToString([Globalization.CultureInfo]::InvariantCulture),
    '--weights', $Weights,
    '--confidence', $Confidence.ToString([Globalization.CultureInfo]::InvariantCulture)
)
& $Python @archiveInitArgs
if ($LASTEXITCODE -ne 0) {
    throw "Session initialization failed with exit code $LASTEXITCODE"
}

$PerceptionScript = Join-Path $PSScriptRoot 'semantic_perception.py'
$perceptionArgs = @(
    '-u',
    $PerceptionScript,
    '--weights', $Weights,
    '--output-dir', $SemanticDir,
    '--confidence', $Confidence.ToString([Globalization.CultureInfo]::InvariantCulture),
    '--confirm-frames', $ConfirmFrames.ToString(),
    '--capture-interval', $CaptureInterval.ToString([Globalization.CultureInfo]::InvariantCulture),
    '--max-images-per-class', $MaxImagesPerClass.ToString(),
    '--max-depth-m', $MaxDepthM.ToString([Globalization.CultureInfo]::InvariantCulture),
    '--interval', $PerceptionInterval.ToString([Globalization.CultureInfo]::InvariantCulture),
    '--live-dir', $LiveDir,
    '--stop-file', $StopFile
)

$sessionPayload = [ordered]@{
    result_root = $ResultRoot
    semantic_dir = $SemanticDir
    live_dir = $LiveDir
    map_dir = $MapDir
} | ConvertTo-Json -Compress
Write-Output "GUI_SESSION $sessionPayload"
Write-Host "Starting semantic perception -> $SemanticDir"
$SemanticLog = Join-Path $SemanticDir 'perception.log'
$SemanticErrorLog = Join-Path $SemanticDir 'perception_error.log'
$perception = Start-Process -FilePath $Python -ArgumentList $perceptionArgs `
    -WorkingDirectory $Workspace -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $SemanticLog `
    -RedirectStandardError $SemanticErrorLog

$MissionSucceeded = $false
$PerceptionFailure = $null
try {
    if ($ResultRoot -notmatch '^[A-Za-z]:\\') {
        throw "Result path is not an absolute Windows drive path: $ResultRoot"
    }
    $drive = $ResultRoot.Substring(0, 1).ToLowerInvariant()
    $tail = $ResultRoot.Substring(2).Replace('\', '/')
    $wslDestination = "/mnt/$drive$tail"
    $workspaceDrive = $Workspace.Substring(0, 1).ToLowerInvariant()
    $workspaceTail = $Workspace.Substring(2).Replace('\', '/')
    $wslWorkspace = "/mnt/$workspaceDrive$workspaceTail"
    $wslMissionScript = "/mnt/$workspaceDrive$workspaceTail/scripts/run_citypark_loop_inner.sh"
    $previousWslEnv = $env:WSLENV
    $env:CITYPARK_GOALS = $Goals
    $env:CITYPARK_FLIGHT_Z = $FlightZ.ToString(
        '0.0###', [Globalization.CultureInfo]::InvariantCulture
    )
    $env:CITYPARK_MAX_TIME = $MaxMissionTime.ToString(
        '0.0###', [Globalization.CultureInfo]::InvariantCulture
    )
    $env:DRONE_MAPBUILDING_ROOT_WSL = $wslWorkspace
    $forwardVariables = (
        'CITYPARK_GOALS/u:CITYPARK_FLIGHT_Z/u:CITYPARK_MAX_TIME/u:' +
        'DRONE_MAPBUILDING_ROOT_WSL/u'
    )
    $env:WSLENV = if ([string]::IsNullOrWhiteSpace($previousWslEnv)) {
        $forwardVariables
    } else {
        "$previousWslEnv`:$forwardVariables"
    }
    wsl -d $WslDistro -u $WslUser -- bash `
        $wslMissionScript `
        $wslDestination.Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "CityPark mission failed with exit code $LASTEXITCODE"
    }
    $MissionSucceeded = $true
}
finally {
    $env:WSLENV = $previousWslEnv
    Remove-Item Env:CITYPARK_GOALS -ErrorAction SilentlyContinue
    Remove-Item Env:CITYPARK_FLIGHT_Z -ErrorAction SilentlyContinue
    Remove-Item Env:CITYPARK_MAX_TIME -ErrorAction SilentlyContinue
    Remove-Item Env:DRONE_MAPBUILDING_ROOT_WSL -ErrorAction SilentlyContinue
    New-Item -ItemType File -Force -Path $StopFile | Out-Null
    if (-not $perception.WaitForExit(15000)) {
        Stop-Process -Id $perception.Id -Force
    }
    # The timeout overload alone does not reliably populate ExitCode in
    # Windows PowerShell 5.1 when stdout/stderr are redirected. A second,
    # parameterless wait drains the async readers and refreshes the process.
    $perception.WaitForExit()
    $perception.Refresh()
    $perceptionExitCode = $perception.ExitCode
    if ($null -eq $perceptionExitCode -or $perceptionExitCode -ne 0) {
        $PerceptionFailure = "Semantic perception failed with exit code $perceptionExitCode; see $SemanticErrorLog"
    }

    $archiveStatus = if ($MissionSucceeded -and $null -eq $PerceptionFailure) {
        'completed'
    } else {
        'failed'
    }
    & $Python $ArchiveScript finalize --root $ResultRoot --status $archiveStatus
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Session finalization failed with exit code $LASTEXITCODE"
    }
}

if ($null -ne $PerceptionFailure) {
    throw $PerceptionFailure
}

Write-Host "Mission and semantic evidence complete -> $ResultRoot"
