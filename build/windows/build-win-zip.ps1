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

# Package the MyTraL Windows desktop executable into a ZIP archive.
#
# Prerequisite: build the desktop executable first via 'make distro-desktop-build-win'.

$ErrorActionPreference = "Stop"

Write-Host "================================================" -ForegroundColor Green
Write-Host "MyTraL Windows ZIP Archive Build" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green

# get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")

Set-Location $ProjectRoot

# get MyTraL version
$MytralVersion = uv run python -c "import sys; sys.path.insert(0, 'mytral'); import version; print(version.__version__)" 2>$null
if ($null -eq $MytralVersion) { $MytralVersion = "dev" }
Write-Host "Packaging MyTraL version: $MytralVersion" -ForegroundColor Green

# verify the desktop executable was built first
$ExePath = Join-Path $ProjectRoot "distro\desktop\mytral-$MytralVersion.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "ERROR: Desktop executable not found: $ExePath`nRun 'make distro-desktop-build-win' first."
}

# ensure output directory exists
$OutputDir = Join-Path $ProjectRoot "distro\windows"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# create the ZIP archive (overwrite any stale archive)
$ZipPath = Join-Path $OutputDir "mytral-$MytralVersion.exe.zip"
Write-Host "Creating ZIP archive..." -ForegroundColor Yellow
Compress-Archive -Path $ExePath -DestinationPath $ZipPath -Force

Write-Host "================================================" -ForegroundColor Green
Write-Host "ZIP archive built: $ZipPath" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
