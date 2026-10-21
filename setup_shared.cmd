@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
py -3.12 -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install -r requirements.shared.txt
if errorlevel 1 exit /b 1
if not exist .env copy .env.shared.example .env >nul
echo Заполните .env по инструкции README-SHARED.md, затем запустите run_shared.cmd
pause
