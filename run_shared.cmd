@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Сначала запустите setup_shared.cmd
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m gim.shared_main check-db
if errorlevel 1 (
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m gim.shared_main run
pause
