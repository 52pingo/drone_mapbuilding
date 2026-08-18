[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [int]$Epochs = 80,
    [int]$Batch = 2,
    [int]$ImageSize = 640,
    [int]$Workers = 4,
    [double]$Fraction = 1.0,
    [switch]$NoValidation
)

$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$python = 'C:\Users\29593\anaconda3\envs\deeplearning\python.exe'
$trainingRoot = Join-Path $workspace 'results\training'
$runRoot = Join-Path $trainingRoot $Name
$controlRoot = Join-Path $trainingRoot ("{0}_control" -f $Name)

if (Test-Path -LiteralPath $runRoot) {
    throw "Training output already exists: $runRoot"
}
if (Test-Path -LiteralPath $controlRoot) {
    throw "Training control directory already exists: $controlRoot"
}
New-Item -ItemType Directory -Path $controlRoot -Force | Out-Null

$stdout = Join-Path $controlRoot 'train_stdout.log'
$stderr = Join-Path $controlRoot 'train_stderr.log'
$arguments = @(
    '-u',
    (Join-Path $PSScriptRoot 'train_uav_semantic.py'),
    '--name', $Name,
    '--epochs', $Epochs,
    '--batch', $Batch,
    '--imgsz', $ImageSize,
    '--workers', $Workers,
    '--fraction', $Fraction.ToString([Globalization.CultureInfo]::InvariantCulture)
)
if ($NoValidation) {
    $arguments += '--no-val'
}

$process = Start-Process -FilePath $python `
    -ArgumentList $arguments `
    -WorkingDirectory $workspace `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WindowStyle Hidden `
    -PassThru

$process.Id | Set-Content -LiteralPath (Join-Path $controlRoot 'pid.txt') -Encoding ASCII
[ordered]@{
    pid = $process.Id
    name = $Name
    stdout = $stdout
    stderr = $stderr
    output = $runRoot
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $controlRoot 'launch.json') -Encoding UTF8

Write-Output "TRAINING_PID=$($process.Id)"
Write-Output "STDOUT=$stdout"
Write-Output "STDERR=$stderr"
Write-Output "OUTPUT=$runRoot"
