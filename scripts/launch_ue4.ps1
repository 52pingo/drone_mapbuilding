#Requires -Version 5.1
<#
    Launch an AirSim UE4 project in a detached game window and wait until the main
    window handle is available. Leaves UE4 running when the script exits.
#>
param(
    [int]$TimeoutSeconds = 180,
    [string]$Ue4EditorPath = 'D:\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe',
    [string]$ProjectPath = 'D:\CityParkEnvironmentCollec\CityPark.uproject',
    [string]$Map = '/Game/CityPark/Maps/Showcase?game=/Script/AirSim.AirSimGameMode',
    [string]$Python = 'python',
    [string]$AirSimClientPath = 'D:\PycharmProjects\PythonProject19\AirSim\PythonClient'
)

$ErrorActionPreference = 'Stop'

Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class Ue4LaunchNative {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
}
'@

if (-not (Test-Path -LiteralPath $Ue4EditorPath -PathType Leaf)) {
    throw "UE4 editor not found: $Ue4EditorPath"
}
if (-not (Test-Path -LiteralPath $ProjectPath -PathType Leaf)) {
    throw "UE4 project not found: $ProjectPath"
}

# Clean up any existing UE4 editor instance.
Stop-Process -Name 'UE4Editor' -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Start the game windowed. Do not wait: the process lives on.
$launchArguments = @($ProjectPath)
if (-not [string]::IsNullOrWhiteSpace($Map)) {
    $launchArguments += $Map
}
$launchArguments += @('-game', '-windowed', '-log')
$proc = Start-Process -FilePath $Ue4EditorPath -ArgumentList $launchArguments -PassThru
Write-Output "UE4 project=$ProjectPath"
Write-Output "UE4 map=$Map"
Write-Output "UE4 pid=$($proc.Id)"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$handle = [IntPtr]::Zero
while ((Get-Date) -lt $deadline) {
    $p = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
    if ($null -eq $p) {
        Start-Sleep -Milliseconds 500
        continue
    }
    if ($p.MainWindowHandle -ne [IntPtr]::Zero) {
        $handle = $p.MainWindowHandle
        break
    }
    Start-Sleep -Milliseconds 500
}

if ($handle -eq [IntPtr]::Zero) {
    throw "UE4 main window did not appear within ${TimeoutSeconds}s"
}

# Restore in case it is minimized and place it in the upper-left corner.
[void][Ue4LaunchNative]::ShowWindow($handle, 9)   # SW_RESTORE
Start-Sleep -Milliseconds 200
[void][Ue4LaunchNative]::MoveWindow($handle, 0, 0, 1280, 720, $true)
Start-Sleep -Milliseconds 200
Write-Output "UE4 ready hwnd=$handle"

# The main unbound CityPark post-process volume clamps AirSim floating-point
# depth to [0, 1]. Remove only that runtime actor (the .umap remains untouched)
# and verify metric depth before allowing PX4/ROS to start.
if ([System.IO.Path]::GetFileName($ProjectPath) -ieq 'CityPark.uproject') {
    $prepareScript = Join-Path $PSScriptRoot 'prepare_citypark_runtime.py'
    if (-not (Test-Path -LiteralPath $prepareScript -PathType Leaf)) {
        throw "CityPark runtime preparation script not found: $prepareScript"
    }
    Write-Output 'Waiting for CityPark AirSim depth pipeline...'
    & $Python $prepareScript `
        --timeout-seconds $TimeoutSeconds `
        --airsim-client $AirSimClientPath
    if ($LASTEXITCODE -ne 0) {
        throw "CityPark runtime preparation failed with exit code $LASTEXITCODE"
    }
}
