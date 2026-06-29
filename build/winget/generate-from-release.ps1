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

# Download the published MyTraL installer from a GitHub release, compute its
# SHA256, and generate the three winget manifest YAML files ready for submission
# to microsoft/winget-pkgs.
#
# Usage:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass `
#       -File build\winget\generate-from-release.ps1 -Version 1.56.0

param (
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"

$GithubOrg    = "dvorka-oss"
$GithubRepo   = "mytral"
$PackageId    = "Mytral.Mytral"
$InstallerName = "mytral-$Version-setup.exe"
$InstallerUrl  = "https://github.com/$GithubOrg/$GithubRepo/releases/download/v$Version/$InstallerName"

# ── Step 1: download and hash ──────────────────────────────────────────────────

Write-Host "Downloading $InstallerUrl ..." -ForegroundColor Cyan
$TmpFile = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), $InstallerName)
Invoke-WebRequest -Uri $InstallerUrl -OutFile $TmpFile -UseBasicParsing
$Sha256 = (Get-FileHash $TmpFile -Algorithm SHA256).Hash
Remove-Item $TmpFile -Force
Write-Host "SHA256: $Sha256" -ForegroundColor Green

# ── Step 2: prepare output directory ──────────────────────────────────────────

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$OutDir      = Join-Path $ProjectRoot "distro\winget\manifests\m\Mytral\Mytral\$Version"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# UTF-8 without BOM — winget rejects files with a BOM
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

# ── Step 3: version manifest ───────────────────────────────────────────────────

$VersionYaml = @"
PackageIdentifier: $PackageId
PackageVersion: $Version
DefaultLocale: en-US
ManifestType: version
ManifestVersion: 1.6.0
"@
[System.IO.File]::WriteAllText(
    (Join-Path $OutDir "$PackageId.yaml"), $VersionYaml, $Utf8NoBom)

# ── Step 4: installer manifest ─────────────────────────────────────────────────

$InstallerYaml = @"
PackageIdentifier: $PackageId
PackageVersion: $Version
InstallerType: inno
Scope: machine
InstallModes:
  - interactive
  - silent
Installers:
  - Architecture: x64
    InstallerUrl: $InstallerUrl
    InstallerSha256: $Sha256
    ProductCode: '{C3D7F241-8B5E-4A29-9F6D-E1B02A4C7853}_is1'
ManifestType: installer
ManifestVersion: 1.6.0
"@
[System.IO.File]::WriteAllText(
    (Join-Path $OutDir "$PackageId.installer.yaml"), $InstallerYaml, $Utf8NoBom)

# ── Step 5: locale manifest ────────────────────────────────────────────────────

$LocaleYaml = @"
PackageIdentifier: $PackageId
PackageVersion: $Version
PackageLocale: en-US
Publisher: Martin Dvorak
PublisherUrl: https://mytral.fitness
PublisherSupportUrl: https://github.com/$GithubOrg/$GithubRepo/issues
Author: Martin Dvorak
PackageName: MyTraL
PackageUrl: https://mytral.fitness
License: AGPL-3.0
LicenseUrl: https://github.com/$GithubOrg/$GithubRepo/blob/main/LICENSE
ShortDescription: My Training Log - fitness tracking desktop app
Description: |-
  MyTraL (My Training Log) is a sovereign athlete training log desktop application.
  Train smarter, not harder.
Tags:
  - running
  - cycling
  - fitness
  - training
  - sports
  - health
ReleaseNotesUrl: https://github.com/$GithubOrg/$GithubRepo/releases/tag/v$Version
ManifestType: defaultLocale
ManifestVersion: 1.6.0
"@
[System.IO.File]::WriteAllText(
    (Join-Path $OutDir "$PackageId.locale.en-US.yaml"), $LocaleYaml, $Utf8NoBom)

# ── Done ───────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "Manifests written to: $OutDir" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  make distro-winget-validate VERSION=$Version"
Write-Host "  ... then copy manifests to your winget-pkgs fork and open a PR"
