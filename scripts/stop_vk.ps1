$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $projectPath 'runtime/vk-process.json'
if (-not (Test-Path -LiteralPath $statePath)) {
    Write-Output 'Managed VK process was not started.'
    exit 0
}
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$entryPath = Join-Path $projectPath 'main.py'
$running = Get-CimInstance Win32_Process -Filter "ProcessId=$($state.pid)"
if (-not $running) {
    Write-Output 'VK process is already stopped.'
    exit 0
}
if (-not $running.CommandLine.Contains($entryPath) -or -not $running.CommandLine.Contains('--vk')) {
    throw 'PID belongs to another command; refusing to stop it.'
}
Stop-Process -Id $state.pid -Force
Write-Output 'VK bot stopped.'
