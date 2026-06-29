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

# Compute SHA256 of a published MyTraL Windows installer by downloading it from
# the GitHub release URL. Use this when the local installer file is no longer
# available (e.g. computed after publishing the GitHub release).
#
# Usage:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass `
#       -File build\winget\sha256-from-url.ps1 -Version 1.56.0

param (
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"

$Url = "https://github.com/dvorka-oss/mytral/releases/download/v$Version/mytral-$Version-setup.exe"
$TmpFile = [System.IO.Path]::GetTempFileName() + ".exe"

Write-Host "Downloading $Url ..."
Invoke-WebRequest -Uri $Url -OutFile $TmpFile -UseBasicParsing

$Hash = (Get-FileHash $TmpFile -Algorithm SHA256).Hash
Remove-Item $TmpFile -Force

Write-Host ""
Write-Host "SHA256: $Hash"
Write-Host ""
Write-Host "Use with:"
Write-Host "  make distro-winget-manifest VERSION=$Version SHA256=$Hash"
