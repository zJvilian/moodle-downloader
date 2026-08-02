@echo off
setlocal
cd /d "%~dp0"
title Moodle Downloader

set "PYTHON_EXE="
set "PYTHON_ARGS="

if exist "%~dp0.venv\Scripts\python.exe" call :probe "%~dp0.venv\Scripts\python.exe" ""
if not defined PYTHON_EXE if exist "%LOCALAPPDATA%\Python\bin\python3.exe" call :probe "%LOCALAPPDATA%\Python\bin\python3.exe" ""
if not defined PYTHON_EXE call :probe "py" "-3"
if not defined PYTHON_EXE call :probe "python" ""
if not defined PYTHON_EXE for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do call :probe "%%~fD\python.exe" ""

if not defined PYTHON_EXE (
    echo.
    echo FEHLER: Keine funktionierende Python-Installation gefunden.
    echo.
    echo Installiere Python 3.10 oder neuer von https://www.python.org/downloads/
    echo und aktiviere bei der Installation "Add python.exe to PATH".
    echo Danach diese Datei erneut doppelklicken.
    echo.
    pause
    exit /b 1
)

set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import tkinter, requests, selenium, webdriver_manager" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Python wurde gefunden, aber Abhaengigkeiten fehlen in genau dieser Installation.
    echo Bitte diesen Befehl in PowerShell oder CMD ausfuehren:
    echo.
    echo   "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r "%~dp0requirements.txt"
    echo.
    pause
    exit /b 1
)

"%PYTHON_EXE%" %PYTHON_ARGS% "%~dp0start_ui.py"
if errorlevel 1 (
    echo.
    echo Die Benutzeroberflaeche wurde mit einem Fehler beendet.
    pause
    exit /b 1
)
exit /b 0

:probe
if defined PYTHON_EXE exit /b 0
"%~1" %~2 -c "import sys; raise SystemExit(0 if sys.version_info ^>= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=%~1"
    set "PYTHON_ARGS=%~2"
)
exit /b 0
