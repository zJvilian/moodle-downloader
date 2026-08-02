@echo off
setlocal enabledelayedexpansion

echo.
echo ========================================
echo    Moodle Kurs-Downloader v2.2
echo ========================================
echo.

REM Schritt 1: Download-Pfad
echo [1] Download-Verzeichnis
echo ----------------------------------------
set "OUTPUT_DIR="
set /p "OUTPUT_DIR=Pfad (Enter=downloads): "
if "!OUTPUT_DIR!"=="" set "OUTPUT_DIR=downloads"
echo.
echo OK: !OUTPUT_DIR!
echo.

REM Schritt 2: Credentials
echo [2] Login-Daten
echo ----------------------------------------
set "USERNAME_ARG="
set "PASSWORD_ARG="
set "SKIP_CREDS=N"

if exist "credentials.json" (
    echo credentials.json gefunden.
    set "USE_CREDS="
    set /p "USE_CREDS=Verwenden? (J=Ja / N=Nein) [J]: "
    if "!USE_CREDS!"=="" set "USE_CREDS=J"
    if /i "!USE_CREDS!"=="J" (
        echo Verwende credentials.json
        set "SKIP_CREDS=Y"
    )
)

if "!SKIP_CREDS!"=="N" (
    set "MY_USER="
    set /p "MY_USER=Benutzername: "
    if "!MY_USER!"=="" (
        echo FEHLER: Benutzername leer!
        pause
        exit /b 1
    )
    set "MY_PASS="
    set /p "MY_PASS=Passwort: "
    set "USERNAME_ARG=--username !MY_USER!"
    set "PASSWORD_ARG=--password !MY_PASS!"
    echo OK
)
echo.

REM Schritt 3: URLs
echo [3] Moodle-Kurs-URL(s)
echo ----------------------------------------
echo Gib eine oder mehrere URLs ein (eine pro Zeile).
echo Leere Zeile = Eingabe beenden.
echo.
set "URL_ARGS="
set "URL_COUNT=0"

:input_url
set "COURSE_URL="
set /p "COURSE_URL=URL !URL_COUNT! (Enter=fertig): "
if "!COURSE_URL!"=="" goto :done_urls
set "URL_ARGS=!URL_ARGS! --url "!COURSE_URL!""
set /a URL_COUNT+=1
goto :input_url

:done_urls
if "!URL_COUNT!"=="0" (
    echo FEHLER: Keine URL eingegeben!
    pause
    exit /b 1
)
echo.
echo !URL_COUNT! Kurs(e) eingegeben.
echo.

REM Schritt 4: Filter
echo [4] Was herunterladen?
echo ----------------------------------------
echo   A  = Alles (Standard)
echo   F  = Nur Dateien/PDFs
echo   D  = Nur Beschreibungen
echo   Q  = Nur Quizzes
echo   B  = Nur Buecher
echo   FO = Nur Foren
echo   L  = Nur Links
echo.
set "CHOICE="
set /p "CHOICE=Auswahl [A]: "
if "!CHOICE!"=="" set "CHOICE=A"

set "INCLUDE_ARG="
if /i "!CHOICE!"=="F" set "INCLUDE_ARG=--include file"
if /i "!CHOICE!"=="D" set "INCLUDE_ARG=--include description"
if /i "!CHOICE!"=="Q" set "INCLUDE_ARG=--include quiz"
if /i "!CHOICE!"=="B" set "INCLUDE_ARG=--include book"
if /i "!CHOICE!"=="FO" set "INCLUDE_ARG=--include forum"
if /i "!CHOICE!"=="L" set "INCLUDE_ARG=--include link"
echo.

REM Schritt 5: Tiefe
echo [5] Scraping-Tiefe
echo ----------------------------------------
echo   D = Deep, in Activities (Standard)
echo   S = Shallow, nur Kursseite
echo.
set "DEPTH="
set /p "DEPTH=Auswahl [D]: "
if "!DEPTH!"=="" set "DEPTH=D"

set "DEPTH_ARG=--depth deep"
if /i "!DEPTH!"=="S" set "DEPTH_ARG=--depth shallow"
echo.

REM Schritt 6: AI-ready Export
echo [6] AI-ready Export
echo ----------------------------------------
echo Erstellt Strukturkarte, Manifest und AI-Kontext-Pakete.
set "AI_CHOICE="
set /p "AI_CHOICE=Aktivieren? (J/N) [N]: "
set "AI_ARG="
if /i "!AI_CHOICE!"=="J" set "AI_ARG=--optimize-ai"
echo.

REM Schritt 7: Externe Links
echo [7] Externe Links
echo ----------------------------------------
set "YOUTUBE_CHOICE="
set /p "YOUTUBE_CHOICE=YouTube-Videos herunterladen? (J/N) [N]: "
set "YOUTUBE_ARG="
if /i "!YOUTUBE_CHOICE!"=="J" set "YOUTUBE_ARG=--download-youtube"

set "WEB_CHOICE="
set /p "WEB_CHOICE=Webseiten als Markdown archivieren? (J/N) [J]: "
set "WEB_ARG="
if /i "!WEB_CHOICE!"=="N" set "WEB_ARG=--no-scrape-external"
echo.

REM Bestaetigung
echo ========================================
echo   Kurse:  !URL_COUNT!
echo   Output: !OUTPUT_DIR!
echo ========================================
echo.
set "GO="
set /p "GO=Starten? (J/N) [J]: "
if "!GO!"=="" set "GO=J"
if /i not "!GO!"=="J" (
    echo Abgebrochen.
    pause
    exit /b 0
)

REM Start
echo.
echo Starte Download...
echo.

set PYTHONPATH=%~dp0src
python -m moodle_download !URL_ARGS! --output "!OUTPUT_DIR!" !DEPTH_ARG! !INCLUDE_ARG! !AI_ARG! !YOUTUBE_ARG! !WEB_ARG! !USERNAME_ARG! !PASSWORD_ARG!

echo.
echo Fertig!
pause
