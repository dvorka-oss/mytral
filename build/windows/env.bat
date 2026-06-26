@echo off
rem MyTraL Windows build environment — adapt paths to your local installation.

rem Inno Setup 6 compiler (https://jrsoftware.org/isinfo.php)
rem Default to user-profile install; override with system-wide path if present.
set MYTRAL_ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set MYTRAL_ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
