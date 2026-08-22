@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 exit /b %errorlevel%
)

".venv\Scripts\python.exe" -m pip install -e ".[build]"
if errorlevel 1 exit /b %errorlevel%

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean kinebeat.spec
