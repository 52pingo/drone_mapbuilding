#Requires -Version 5.1
<# Launch a selected AirSim UE4 project or packaged simulator and verify readiness. #>
param(
    [ValidateSet('editor', 'standalone')]
    [string]$LaunchMode = 'editor',
    [int]$TimeoutSeconds = 180,
    [string]$Ue4EditorPath = 'D:\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe',
    [string]$ProjectPath = 'D:\CityParkEnvironmentCollec\CityPark.uproject',
    [string]$StandaloneExecutable = '',
    [string]$Map = '',
    [string]$Python = 'python',
    [string]$AirSimClientPath = '',
    [ValidateSet('auto', 'generic', 'none')]
    [string]$ValidationMode = 'auto',
    [ValidateSet('reuse', 'fail')]
    [string]$ExistingInstancePolicy = 'reuse',
    [string]$VehicleName = 'PX4',
    [string]$CameraName = 'CameraDepth'
)

$ErrorActionPreference = 'Stop'

function Write-Ue4Status {
    param([bool]$WindowReady, $AirSimReady, [string]$Message)
    $payload = [ordered]@{
        window_ready = $WindowReady
        airsim_ready = $AirSimReady
        message = $Message
    } | ConvertTo-Json -Compress
    Write-Output "GUI_UE4 $payload"
}

Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class Ue4LaunchNative {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
}
'@

function Test-AirSimPort {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.BeginConnect('127.0.0.1', 41451, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne(700)) {
            return $false
        }
        $client.EndConnect($connect)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Find-MatchingSimulator {
    param([string]$Program)
    $processName = [System.IO.Path]::GetFileName($Program)
    try {
        $candidates = @(Get-CimInstance Win32_Process -Filter "Name='$processName'" -ErrorAction Stop)
    }
    catch {
        Write-Output "Existing-instance discovery warning: $($_.Exception.Message)"
        return $null
    }
    $matches = @()
    foreach ($candidate in $candidates) {
        $commandLine = [string]$candidate.CommandLine
        $pathMatches = $false
        if ($LaunchMode -eq 'editor') {
            $pathMatches = $commandLine.IndexOf(
                $ProjectPath, [System.StringComparison]::OrdinalIgnoreCase
            ) -ge 0
        }
        else {
            $pathMatches = (
                [string]$candidate.ExecutablePath
            ).Equals($StandaloneExecutable, [System.StringComparison]::OrdinalIgnoreCase)
        }
        $mapMatches = (
            [string]::IsNullOrWhiteSpace($Map) -or
            $commandLine.IndexOf($Map, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        )
        if ($pathMatches -and $mapMatches) {
            $process = Get-Process -Id $candidate.ProcessId -ErrorAction SilentlyContinue
            if ($null -ne $process) { $matches += $process }
        }
    }
    return $matches | Sort-Object @{Expression = {$_.MainWindowHandle -ne [IntPtr]::Zero}; Descending = $true}, StartTime | Select-Object -First 1
}

function Invoke-AirSimValidation {
    param([bool]$WindowReady, [string]$Context)
    if ($ValidationMode -eq 'none') {
        Write-Ue4Status $WindowReady $null "$Context AirSim validation was skipped."
        exit 0
    }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        Write-Ue4Status $WindowReady $false "Simulator is open, but validation Python was not found: $Python"
        exit 2
    }

    $isCityPark = (
        $ValidationMode -eq 'auto' -and
        [System.IO.Path]::GetFileName($ProjectPath) -ieq 'CityPark.uproject'
    )
    $validatorName = if ($isCityPark) {
        'prepare_citypark_runtime.py'
    }
    else {
        'verify_airsim_runtime.py'
    }
    $validationScript = Join-Path $PSScriptRoot $validatorName
    $validationArgs = @(
        $validationScript,
        '--timeout-seconds', $TimeoutSeconds,
        '--airsim-client', $AirSimClientPath,
        '--vehicle', $VehicleName,
        '--camera', $CameraName
    )
    if (-not (Test-Path -LiteralPath $validationScript -PathType Leaf)) {
        Write-Ue4Status $WindowReady $false "Simulator is open, but AirSim validator is missing: $validationScript"
        exit 2
    }

    Write-Output "Waiting for AirSim RGB/depth pipeline..."
    & $Python @validationArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Ue4Status $WindowReady $false "Simulator is open, but AirSim validation failed (exit $LASTEXITCODE)."
        exit 2
    }
    Write-Ue4Status $WindowReady $true "$Context AirSim RGB/depth are ready."
    exit 0
}

if ($LaunchMode -eq 'editor') {
    if (-not (Test-Path -LiteralPath $Ue4EditorPath -PathType Leaf)) {
        throw "UE4 editor not found: $Ue4EditorPath"
    }
    if (-not (Test-Path -LiteralPath $ProjectPath -PathType Leaf)) {
        throw "UE4 project not found: $ProjectPath"
    }
    $program = $Ue4EditorPath
    # PowerShell 5 joins ArgumentList into one string; quote paths containing spaces.
    $launchArguments = @("`"$ProjectPath`"")
    if (-not [string]::IsNullOrWhiteSpace($Map)) {
        $launchArguments += $Map
    }
    $launchArguments += @('-game', '-windowed', '-log')
}
else {
    if (-not (Test-Path -LiteralPath $StandaloneExecutable -PathType Leaf)) {
        throw "Packaged simulator not found: $StandaloneExecutable"
    }
    $program = $StandaloneExecutable
    $launchArguments = @('-windowed', '-log')
    if (-not [string]::IsNullOrWhiteSpace($Map)) {
        $launchArguments = @($Map) + $launchArguments
    }
}

$existing = Find-MatchingSimulator $program
if ($null -ne $existing) {
    if ($ExistingInstancePolicy -eq 'fail') {
        Write-Ue4Status $false $false "Matching simulator is already running (pid=$($existing.Id))."
        Write-Error "Matching simulator is already running (pid=$($existing.Id)); close it or use the reuse policy."
        exit 3
    }
    $handle = $existing.MainWindowHandle
    if ($handle -ne [IntPtr]::Zero) {
        [void][Ue4LaunchNative]::ShowWindow($handle, 9)
        Start-Sleep -Milliseconds 200
        [void][Ue4LaunchNative]::MoveWindow($handle, 0, 0, 1280, 720, $true)
    }
    Write-Output "UE4 reuse pid=$($existing.Id) hwnd=$handle"
    Write-Ue4Status $true $null 'Matching simulator is already running; reusing it and checking AirSim.'
    Invoke-AirSimValidation $true 'Existing simulator reused;'
}

if (Test-AirSimPort) {
    Write-Ue4Status $false $false 'AirSim port 41451 is occupied by a different environment.'
    Write-Error 'AirSim RPC port 41451 is already occupied, but it does not match the selected project/map. Close the other simulator first.'
    exit 3
}

$proc = Start-Process -FilePath $program -ArgumentList $launchArguments -PassThru
Write-Output "UE4 mode=$LaunchMode"
Write-Output "UE4 program=$program"
Write-Output "UE4 project=$ProjectPath"
Write-Output "UE4 map=$Map"
Write-Output "UE4 pid=$($proc.Id)"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$handle = [IntPtr]::Zero
while ((Get-Date) -lt $deadline) {
    $process = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        throw "UE4 process exited before its main window became ready (pid=$($proc.Id))"
    }
    if ($process.MainWindowHandle -ne [IntPtr]::Zero) {
        $handle = $process.MainWindowHandle
        break
    }
    Start-Sleep -Milliseconds 500
}

if ($handle -eq [IntPtr]::Zero) {
    throw "UE4 main window did not appear within ${TimeoutSeconds}s"
}

[void][Ue4LaunchNative]::ShowWindow($handle, 9)
Start-Sleep -Milliseconds 200
[void][Ue4LaunchNative]::MoveWindow($handle, 0, 0, 1280, 720, $true)
Write-Output "UE4 ready hwnd=$handle"
Write-Ue4Status $true $null 'UE4 window is ready; checking AirSim.'
Invoke-AirSimValidation $true 'UE4 launched;'
