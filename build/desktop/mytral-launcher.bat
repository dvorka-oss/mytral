@echo off
:: MyTraL Desktop Launcher
::
:: This script can be used to create a desktop launcher for MyTraL
:: after the executable has been built.
::

set MYTRAL_EXECUTABLE=%USERPROFILE%\AppData\Local\Programs\MyTraL\mytral.exe

if not exist "%MYTRAL_EXECUTABLE%" (
    echo MyTraL executable not found at: %MYTRAL_EXECUTABLE%
    echo Please build and install MyTraL first:
    echo   make distro-desktop-build-win
    echo   copy distro\desktop\mytral-*.exe "%MYTRAL_EXECUTABLE%"
    pause
    exit /b 1
)

set MYTRAL_USER_REGISTRATION=true
set MYTRAL_INCARNATION=DESKTOP
start "" "%MYTRAL_EXECUTABLE%" %*
