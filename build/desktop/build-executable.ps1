# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# Build MyTraL desktop executable using PyInstaller (Windows)

param (
    [switch]$ShowConsole = $false
)

$ErrorActionPreference = "Stop"

Write-Host "================================================" -ForegroundColor Green
Write-Host "MyTraL Desktop Executable Build (Windows)" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green

# get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$BuildDir = Join-Path $ProjectRoot "build\desktop"
$DistDir = Join-Path $ProjectRoot "distro\desktop"

Write-Host "Project root: $ProjectRoot"
Write-Host "Build dir: $BuildDir"
Write-Host "Dist dir: $DistDir"

# change to project root
Set-Location $ProjectRoot

# get MyTraL version
$MytralVersion = uv run python -c "import sys; sys.path.insert(0, 'mytral'); import version; print(version.__version__)" 2>$null
if ($null -eq $MytralVersion) { $MytralVersion = "dev" }
Write-Host "Building MyTraL version: $MytralVersion" -ForegroundColor Green

# install desktop dependencies via uv dependency group
Write-Host "Installing desktop dependencies..." -ForegroundColor Green
uv sync --group desktop

# create spec file
$SpecFile = Join-Path $BuildDir "mytral.spec"
Write-Host "Creating PyInstaller spec file..." -ForegroundColor Yellow
& "$ScriptDir\create-spec.ps1" -MytralVersion $MytralVersion -ShowConsole:$ShowConsole

# verify spec file exists
if (-not (Test-Path $SpecFile)) {
    Write-Error "ERROR: Spec file was not created at $SpecFile"
}

Write-Host "Using spec file: $SpecFile"

# run PyInstaller
Write-Host "Running PyInstaller..." -ForegroundColor Green
uv run pyinstaller "$SpecFile" `
    --clean `
    --noconfirm `
    --distpath "$DistDir"

# check if build succeeded
$ExecutableName = "mytral-$MytralVersion.exe"
$ExecutablePath = Join-Path $DistDir $ExecutableName

if (Test-Path $ExecutablePath) {
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "Build successful!" -ForegroundColor Green
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "Executable: $ExecutablePath" -ForegroundColor Green
} else {
    Write-Host "================================================" -ForegroundColor Red
    Write-Host "Build failed!" -ForegroundColor Red
    Write-Host "================================================" -ForegroundColor Red
    exit 1
}
