@echo off
rem Build MyTraL Windows installer using Inno Setup 6.
rem
rem Prerequisites:
rem   1. Build desktop executable first:  make distro-desktop-build-win
rem   2. Install Inno Setup 6:            https://jrsoftware.org/isinfo.php
rem   3. Edit build\windows\env.bat       to set MYTRAL_ISCC path.

setlocal

cd /d "%~dp0..\.."

call "build\windows\env.bat"

rem read version from Python via uv
for /f "tokens=*" %%i in ('uv run python -c "import sys; sys.path.insert(0, 'mytral'); import version; print(version.__version__)"') do set MYTRAL_VERSION=%%i
if "%MYTRAL_VERSION%"=="" (
    echo ERROR: Could not read version from mytral/version.py
    exit /b 1
)
echo Building MyTraL %MYTRAL_VERSION% installer...

rem verify the desktop executable was built first
set EXE_PATH=distro\desktop\mytral-%MYTRAL_VERSION%.exe
if not exist "%EXE_PATH%" (
    echo ERROR: Desktop executable not found: %EXE_PATH%
    echo Run 'make distro-desktop-build-win' first.
    exit /b 1
)

rem verify Inno Setup compiler is available
if not exist "%MYTRAL_ISCC%" (
    echo ERROR: Inno Setup compiler not found: %MYTRAL_ISCC%
    echo Install Inno Setup 6 from https://jrsoftware.org/isinfo.php
    echo Then update MYTRAL_ISCC in build\windows\env.bat
    exit /b 1
)

rem ensure output directory exists
mkdir distro\windows 2>nul

rem compile the installer script, passing version as a define
echo Running Inno Setup compiler...
"%MYTRAL_ISCC%" /DMytralAppVersion=%MYTRAL_VERSION% "build\windows\installer\mytral-setup.iss"

if %errorlevel% neq 0 (
    echo ERROR: Inno Setup compilation failed.
    exit /b 1
)

echo.
echo ================================================
echo Installer built: distro\windows\mytral-%MYTRAL_VERSION%-setup.exe
echo ================================================

endlocal
