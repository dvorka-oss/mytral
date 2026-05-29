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

# Clean desktop build artifacts (Windows)

$ErrorActionPreference = "Stop"

Write-Host "Cleaning desktop build artifacts..." -ForegroundColor Cyan

# get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")

Set-Location $ProjectRoot

# remove PyInstaller build artifacts
if (Test-Path "build\__pycache__") { Remove-Item -Recurse -Force "build\__pycache__" }
if (Test-Path "build\mytral") { Remove-Item -Recurse -Force "build\mytral" }
if (Test-Path "build\desktop\__pycache__") { Remove-Item -Recurse -Force "build\desktop\__pycache__" }

# remove spec file
if (Test-Path "build\desktop\mytral.spec") { Remove-Item -Force "build\desktop\mytral.spec" }

# remove dist directory (desktop executables)
if (Test-Path "distro\desktop") {
    Get-ChildItem "distro\desktop\mytral-*" -ErrorAction SilentlyContinue | Remove-Item -Force
    if (Test-Path "distro\desktop\mytral.exe") { Remove-Item -Force "distro\desktop\mytral.exe" }
}

Write-Host "Clean complete!" -ForegroundColor Green
