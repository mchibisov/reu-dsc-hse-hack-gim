@echo off
setlocal
chcp 65001 >nul
set "BOT_DIR=%~dp0"
if not exist "%BOT_DIR%\.venv\Scripts\python.exe" (
    echo Preparing Python environment. Python 3.12+ is required.
    where py >nul 2>nul
    if errorlevel 1 (
        python -m venv "%BOT_DIR%\.venv"
    ) else (
        py -3.12 -m venv "%BOT_DIR%\.venv"
    )
    if errorlevel 1 goto failed
    "%BOT_DIR%\.venv\Scripts\python.exe" -m pip install -r "%BOT_DIR%\requirements.lock"
    if errorlevel 1 goto failed
)
"%BOT_DIR%\.venv\Scripts\python.exe" "%BOT_DIR%\main.py" %*
if errorlevel 1 goto failed
echo.
echo Questionnaire closed. Answers remain in demo.db.
pause
exit /b 0
:failed
echo.
echo Could not start. Read the error above and README.md.
pause
exit /b 1
