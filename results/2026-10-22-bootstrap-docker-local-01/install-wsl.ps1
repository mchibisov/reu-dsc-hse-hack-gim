#requires -RunAsAdministrator
# Выполнять только после явного согласия владельца на системную установку.
# Официальный WSL, без установки Ubuntu и без запуска дистрибутива.
# Скрипт не перезагружает Windows и не удаляет Docker/WSL данные.
$ErrorActionPreference = 'Stop'
& "$env:SystemRoot/System32/wsl.exe" --install --no-distribution --web-download --no-launch
if ($LASTEXITCODE -ne 0) {
    throw "WSL installation returned exit code $LASTEXITCODE; inspect its output before continuing."
}
Write-Output 'WSL installation command completed. If Windows requests a reboot, save work and arrange it with the owner.'
