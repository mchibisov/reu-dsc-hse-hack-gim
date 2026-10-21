$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$runtimePath = Join-Path $projectPath 'runtime'
$statePath = Join-Path $runtimePath 'vk-process.json'
$entryPath = Join-Path $projectPath 'main.py'
$pythonPath = Join-Path $projectPath '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Project Python environment is missing.'
}
if (Test-Path -LiteralPath $statePath) {
    $priorState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $priorProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($priorState.pid)"
    if ($priorProcess -and $priorProcess.CommandLine.Contains($entryPath) -and $priorProcess.CommandLine.Contains('--vk')) {
        Write-Output "VK bot already running: PID $($priorState.pid)"
        exit 0
    }
}
New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
$outPath = Join-Path $runtimePath 'vk.stdout.log'
$errPath = Join-Path $runtimePath 'vk.stderr.log'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
foreach ($logPath in @($outPath, $errPath)) {
    if (Test-Path -LiteralPath $logPath) {
        Move-Item -LiteralPath $logPath -Destination "$logPath.$stamp"
    }
}
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$child = Start-Process -FilePath $pythonPath -ArgumentList @(('"{0}"' -f $entryPath), '--vk') `
    -WorkingDirectory $projectPath -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $outPath -RedirectStandardError $errPath
Start-Sleep -Milliseconds 800
if ($child.HasExited) {
    throw 'VK process exited during startup; inspect local runtime logs.'
}
@{pid=$child.Id; entry=$entryPath; started=(Get-Date).ToString('o')} | ConvertTo-Json |
    Set-Content -LiteralPath $statePath -Encoding utf8
Write-Output "VK bot started: PID $($child.Id)"
