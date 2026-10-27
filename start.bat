@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Moodle Downloader - Web-App

chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

set "VENV_DIR=%~dp0.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "TOOLS_DIR=%~dp0.tools"
set "UV_DIR=%TOOLS_DIR%\uv"
set "UV_PYTHON_INSTALL_DIR=%TOOLS_DIR%\python"

call :environment_ready
if not errorlevel 1 goto :launch

echo.
echo ======================================================
echo    Moodle Downloader - Ersteinrichtung ^& Vorbereitung
echo ======================================================
echo.

if exist "%VENV_PYTHON%" goto :install_packages

call :find_python
if defined PYTHON_EXE (
    echo Erstelle isolierte Python-Umgebung in .venv ...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m venv "%VENV_DIR%"
    if not errorlevel 1 goto :install_packages
)

echo Kein lokales Python 3.10+ gefunden. Lade portable Laufzeitumgebung ^(uv^) herunter ...
call :ensure_uv
if errorlevel 1 (
    echo FEHLER: Konnte weder Python noch den portablen Installer ^(uv^) einrichten.
    echo Bitte pruefe deine Internetverbindung.
    goto :failed
)

"%UV_EXE%" venv --python 3.12 "%VENV_DIR%"
if errorlevel 1 (
    echo FEHLER: Die portable Python-Umgebung konnte nicht erstellt werden.
    goto :failed
)

:install_packages
echo Installiere beziehungsweise aktualisiere Abhaengigkeiten ...
if defined UV_EXE (
    "%UV_EXE%" pip install --python "%VENV_PYTHON%" -e "%~dp0"
) else (
    "%VENV_PYTHON%" -m pip install --disable-pip-version-check -e "%~dp0"
)
if errorlevel 1 (
    echo.
    echo FEHLER: Python-Pakete konnten nicht installiert werden.
    echo Pruefe die Internetverbindung und die Meldungen oberhalb.
    goto :failed
)

call :environment_ready
if errorlevel 1 (
    echo.
    echo FEHLER: Die Installation ist unvollstaendig.
    goto :failed
)

echo.
echo Umgebung erfolgreich eingerichtet!

:launch
"%VENV_PYTHON%" "%~dp0start.py" %*
if errorlevel 1 (
    echo.
    echo Der Webserver wurde mit einem Fehler beendet.
    pause
    exit /b 1
)
exit /b 0

:failed
echo.
pause
exit /b 1

:environment_ready
if not exist "%VENV_PYTHON%" exit /b 1
"%VENV_PYTHON%" -c "import sys, requests, selenium, webdriver_manager, yt_dlp, moodle_download; assert sys.version_info ^>= (3, 10)" >nul 2>&1
exit /b %ERRORLEVEL%

:find_python
set "PYTHON_EXE="
set "PYTHON_ARGS="
if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\Python\bin\python3.exe" call :probe "%LOCALAPPDATA%\Python\bin\python3.exe" ""
if not defined PYTHON_EXE call :probe "py" "-3"
if not defined PYTHON_EXE call :probe "python" ""
if defined LOCALAPPDATA if not defined PYTHON_EXE for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do call :probe "%%~fD\python.exe" ""
exit /b 0

:probe
if defined PYTHON_EXE exit /b 0
"%~1" %~2 -c "import sys; raise SystemExit(0 if sys.version_info ^>= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=%~1"
    set "PYTHON_ARGS=%~2"
)
exit /b 0

:ensure_uv
set "UV_EXE="
for %%U in (uv.exe) do if not "%%~$PATH:U"=="" (
    set "UV_EXE=%%~$PATH:U"
    exit /b 0
)
if exist "%UV_DIR%\uv.exe" (
    set "UV_EXE=%UV_DIR%\uv.exe"
    exit /b 0
)
if exist "%UV_DIR%\bin\uv.exe" (
    set "UV_EXE=%UV_DIR%\bin\uv.exe"
    exit /b 0
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop'; New-Item -ItemType Directory -Force -Path '%UV_DIR%' | Out-Null; $env:UV_UNMANAGED_INSTALL='%UV_DIR%'; irm https://astral.sh/uv/install.ps1 | iex"
if exist "%UV_DIR%\uv.exe" (
    set "UV_EXE=%UV_DIR%\uv.exe"
    exit /b 0
)
if exist "%UV_DIR%\bin\uv.exe" (
    set "UV_EXE=%UV_DIR%\bin\uv.exe"
    exit /b 0
)
exit /b 1
