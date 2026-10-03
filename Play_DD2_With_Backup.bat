@echo off
setlocal
title Dragon's Dogma 2 - Auto Backup
cd /d "%~dp0"

chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM ==================================================
REM SETTINGS
REM ==================================================

REM Python backup script
set "BACKUP_SCRIPT=%~dp0DD2_Backup.py"

REM Python DD2gether auto-update script
set "UPDATE_SCRIPT=%~dp0DD2gether_Update.py"

REM Shared configuration file
set "CONFIG_FILE=%~dp0config.ini"

REM Dragon's Dogma 2 process
set "GAME_PROCESS=DD2.exe"

REM DD2gether executable is loaded from config.ini
set "DD2GETHER_EXE="
set "AUTO_UPDATE=1"

if not exist "%CONFIG_FILE%" (
    echo.
    echo config.ini not found. Creating portable default settings...
    call :CREATE_CONFIG
    if errorlevel 1 goto END_WAIT
)

call :LOAD_CONFIG
if errorlevel 1 goto END_WAIT

REM ==================================================
REM CHECK FILES
REM ==================================================

if not exist "%BACKUP_SCRIPT%" (
    echo.
    echo ERROR: DD2_Backup.py not found.
    echo.
    echo %BACKUP_SCRIPT%
    goto END_WAIT
)

if not exist "%DD2GETHER_EXE%" (
    echo.
    echo DD2gether executable not found:
    echo %DD2GETHER_EXE%
    echo.
    echo Downloading the latest DD2gether from GitHub...
    echo.
    call :INSTALL_DD2GETHER
    if errorlevel 1 goto END_WAIT
    call :LOAD_CONFIG
    if errorlevel 1 goto END_WAIT
)

if not exist "%DD2GETHER_EXE%" (
    echo.
    echo ERROR: DD2gether executable still not found after download.
    echo %DD2GETHER_EXE%
    goto END_WAIT
)

REM ==================================================
REM CHECK FOR DD2GETHER UPDATE
REM ==================================================

set "UPDATE_STATUS=skipped"

if /I "%AUTO_UPDATE%"=="0" goto UPDATE_DONE
if /I "%AUTO_UPDATE%"=="false" goto UPDATE_DONE
if /I "%AUTO_UPDATE%"=="no" goto UPDATE_DONE
if /I "%AUTO_UPDATE%"=="off" goto UPDATE_DONE

echo.
echo ==========================================
echo CHECKING FOR DD2GETHER UPDATE
echo ==========================================
echo.

if not exist "%UPDATE_SCRIPT%" (
    echo WARNING: DD2gether_Update.py not found. Skipping update check.
    goto UPDATE_DONE
)

tasklist /FI "IMAGENAME eq %DD2GETHER_PROCESS%" 2>NUL | find /I "%DD2GETHER_PROCESS%" >NUL
if not errorlevel 1 (
    echo DD2gether is already running. Skipping update check.
    goto UPDATE_DONE
)

py -X utf8 -u "%UPDATE_SCRIPT%"

if errorlevel 1 (
    echo.
    echo WARNING: Update check failed. Continuing with the current version.
    set "UPDATE_STATUS=FAILED - using current version"
    timeout /t 3 /nobreak >nul
    goto UPDATE_DONE
)

set "UPDATE_STATUS=OK"

REM The update script may have changed dd2gether_path. Reload it.
call :LOAD_CONFIG
if errorlevel 1 goto END_WAIT

if not exist "%DD2GETHER_EXE%" (
    echo.
    echo ERROR: DD2gether executable not found after update.
    echo.
    echo %DD2GETHER_EXE%
    goto END_WAIT
)

:UPDATE_DONE

REM ==================================================
REM BACKUP BEFORE GAME
REM ==================================================

echo.
echo ==========================================
echo BACKUP BEFORE GAME
echo ==========================================
echo.

py -X utf8 -u "%BACKUP_SCRIPT%"

if errorlevel 1 (
    echo.
    echo ERROR: Pre-game backup failed.
    goto END_WAIT
)

echo.
echo Pre-game backup completed.
echo.

REM ==================================================
REM START DD2GETHER
REM ==================================================

echo ==========================================
echo STARTING DD2GETHER
echo ==========================================
echo.

start "" "%DD2GETHER_EXE%"

echo DD2gether started.
echo.
echo Waiting for Dragon's Dogma 2...
echo.
echo Press "Launch Dragon's Dogma 2"
echo in the DD2gether window.
echo.

REM ==================================================
REM WAIT FOR GAME START
REM ==================================================

:WAIT_GAME_START

tasklist /FI "IMAGENAME eq %GAME_PROCESS%" 2>NUL | find /I "%GAME_PROCESS%" >NUL

if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto WAIT_GAME_START
)

echo.
echo ==========================================
echo GAME DETECTED
echo ==========================================
echo.
echo Dragon's Dogma 2 is running.
echo Waiting for game to close...
echo.

REM ==================================================
REM WAIT FOR GAME CLOSE
REM ==================================================

:WAIT_GAME_CLOSE

tasklist /FI "IMAGENAME eq %GAME_PROCESS%" 2>NUL | find /I "%GAME_PROCESS%" >NUL

if not errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto WAIT_GAME_CLOSE
)

echo.
echo Game closed.
echo Waiting 5 seconds before backup...

timeout /t 5 /nobreak >nul

REM ==================================================
REM BACKUP AFTER GAME
REM ==================================================

echo.
echo ==========================================
echo BACKUP AFTER GAME
echo ==========================================
echo.

py -X utf8 -u "%BACKUP_SCRIPT%"

if errorlevel 1 (
    echo.
    echo ERROR: Post-game backup failed.
    goto END_WAIT
)

REM ==================================================
REM WAIT FOR DD2GETHER LAUNCHER TO CLOSE
REM ==================================================

tasklist /FI "IMAGENAME eq %DD2GETHER_PROCESS%" 2>NUL | find /I "%DD2GETHER_PROCESS%" >NUL

if not errorlevel 1 (
    echo Waiting for DD2gether Launcher to close...
    echo.
)

:WAIT_LAUNCHER_CLOSE

tasklist /FI "IMAGENAME eq %DD2GETHER_PROCESS%" 2>NUL | find /I "%DD2GETHER_PROCESS%" >NUL

if not errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto WAIT_LAUNCHER_CLOSE
)

echo DD2gether Launcher closed.
echo Checking the latest save one more time...
timeout /t 2 /nobreak >nul
echo.

py -X utf8 -u "%BACKUP_SCRIPT%"

if errorlevel 1 (
    echo.
    echo ERROR: Final backup after Launcher closed failed.
    goto END_WAIT
)

echo.
echo ==========================================
echo ALL DONE
echo ==========================================
echo.
echo DD2gether update   : %UPDATE_STATUS%
echo Pre-game backup    : OK
echo Post-game backup   : OK
echo Final backup check : OK
echo.

:END_WAIT

echo ==========================================
echo Press ENTER or Q to close
echo ==========================================
echo.

powershell -NoProfile -Command "$Host.UI.RawUI.FlushInputBuffer(); while($true){$k=$Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown'); if($k.VirtualKeyCode -eq 13 -or $k.Character -eq 'q' -or $k.Character -eq 'Q'){break}}"

endlocal
exit

REM ==================================================
REM SUBROUTINE: LOAD_CONFIG
REM Reads dd2gether_path / auto_update from config.ini
REM ==================================================
:LOAD_CONFIG
set "DD2GETHER_EXE="
set "AUTO_UPDATE=1"

for /f "usebackq tokens=1,* delims==" %%A in ("%CONFIG_FILE%") do (
    if /I "%%A"=="dd2gether_path" set "DD2GETHER_EXE=%%B"
    if /I "%%A"=="auto_update" set "AUTO_UPDATE=%%B"
)

if not defined DD2GETHER_EXE (
    echo.
    echo ERROR: config.ini is missing dd2gether_path.
    exit /b 1
)

for %%F in ("%DD2GETHER_EXE%") do set "DD2GETHER_PROCESS=%%~nxF"
exit /b 0

REM ==================================================
REM SUBROUTINE: INSTALL_DD2GETHER
REM Downloads the latest DD2gether and writes config.ini
REM ==================================================
:INSTALL_DD2GETHER
if not exist "%UPDATE_SCRIPT%" (
    echo ERROR: DD2gether_Update.py not found. Cannot download DD2gether.
    exit /b 1
)

py -X utf8 -u "%UPDATE_SCRIPT%"

if errorlevel 1 (
    echo.
    echo ERROR: Failed to download DD2gether.
    exit /b 1
)
exit /b 0

REM ==================================================
REM SUBROUTINE: CREATE_CONFIG
REM Writes config.ini for an already-extracted DD2gether,
REM or downloads DD2gether when none is found.
REM ==================================================
:CREATE_CONFIG
set "FOUND_DD2GETHER="
for /r "%~dp0" %%F in (DD2gether.exe) do set "FOUND_DD2GETHER=%%~fF"

if not defined FOUND_DD2GETHER (
    echo DD2gether.exe was not found under:
    echo %~dp0
    echo.
    echo Downloading the latest DD2gether from GitHub...
    echo.
    call :INSTALL_DD2GETHER
    if errorlevel 1 exit /b 1
    exit /b 0
)

>"%CONFIG_FILE%" echo # DD2gether executable path
>>"%CONFIG_FILE%" echo dd2gether_path=%FOUND_DD2GETHER%
>>"%CONFIG_FILE%" echo.
>>"%CONFIG_FILE%" echo # Backup output folder
>>"%CONFIG_FILE%" echo backup_output_path=Backups
>>"%CONFIG_FILE%" echo.
>>"%CONFIG_FILE%" echo # Auto-update DD2gether from GitHub before launch (1=on, 0=off)
>>"%CONFIG_FILE%" echo auto_update=1
>>"%CONFIG_FILE%" echo.
>>"%CONFIG_FILE%" echo # GitHub repository that publishes DD2gether releases
>>"%CONFIG_FILE%" echo dd2gether_repo=But-Frog/dd2-together-release

echo Created:
echo %CONFIG_FILE%
exit /b 0
