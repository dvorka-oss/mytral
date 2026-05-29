# MyTraL: my training log
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

# Create PyInstaller spec file for MyTraL desktop application (Windows)

param (
    [string]$MytralVersion = "dev",
    [switch]$ShowConsole = $false
)

$ErrorActionPreference = "Stop"

# get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$BuildDir = $ScriptDir

Write-Host "Creating PyInstaller spec file..." -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"
Write-Host "Build dir: $BuildDir"
Write-Host "Version: $MytralVersion"

$SpecContent = @"
# -*- mode: python ; coding: utf-8 -*-
# MyTraL Desktop Application - PyInstaller Spec File
# Version: $MytralVersion

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_all, copy_metadata

block_cipher = None

# get project root
project_root = os.path.abspath(SPECPATH + '/../..')

# collect all data files from mytral package
mytral_datas = []
mytral_datas += [(os.path.join(project_root, 'mytral/templates'), 'mytral/templates')]
mytral_datas += [(os.path.join(project_root, 'mytral/static'), 'mytral/static')]

# include package metadata for packages that call importlib.metadata.version() at import time
mytral_datas += copy_metadata('pydantic-ai-slim')
mytral_datas += copy_metadata('genai_prices')

# collect bokeh data files if available
try:
    bokeh_datas = collect_data_files('bokeh')
    mytral_datas += bokeh_datas
except Exception:
    pass

# psutil: C extension required by flaskwebgui — must use collect_all
psutil_datas, psutil_binaries, psutil_hidden = collect_all('psutil')
mytral_datas += psutil_datas
extra_binaries = psutil_binaries

# pydantic_ai and griffe
pydantic_ai_datas, pydantic_ai_binaries, pydantic_ai_hidden = collect_all('pydantic_ai')
mytral_datas += pydantic_ai_datas
extra_binaries += pydantic_ai_binaries

griffe_datas, griffe_binaries, griffe_hidden = collect_all('griffe')
if not griffe_hidden:
    raise RuntimeError("griffe package (griffelib) not collected - run: uv sync --group desktop")
mytral_datas += griffe_datas
extra_binaries += griffe_binaries

pydantic_datas, pydantic_binaries, pydantic_hidden = collect_all('pydantic')
mytral_datas += pydantic_datas
extra_binaries += pydantic_binaries

pydantic_core_datas, pydantic_core_binaries, pydantic_core_hidden = collect_all('pydantic_core')
mytral_datas += pydantic_core_datas
extra_binaries += pydantic_core_binaries

pydantic_graph_datas, pydantic_graph_binaries, pydantic_graph_hidden = collect_all('pydantic_graph')
mytral_datas += pydantic_graph_datas
extra_binaries += pydantic_graph_binaries

# collect all mytral submodules
hidden_imports = collect_submodules('mytral')
hidden_imports += psutil_hidden
hidden_imports += pydantic_ai_hidden
hidden_imports += griffe_hidden
hidden_imports += pydantic_hidden
hidden_imports += pydantic_core_hidden
hidden_imports += pydantic_graph_hidden
hidden_imports += collect_submodules('psutil')
hidden_imports += collect_submodules('pydantic_ai')
hidden_imports += collect_submodules('griffe')
hidden_imports += collect_submodules('pydantic')
hidden_imports += collect_submodules('pydantic_core')
hidden_imports += collect_submodules('pydantic_graph')
hidden_imports += ['waitress', 'flaskwebgui', 'psutil', 'flask', 'flask_wtf', 'wtforms', 'bokeh']
hidden_imports += ['pydantic_ai', 'griffe', 'pydantic', 'pydantic_core', 'pydantic_graph', 'annotated_types']
hidden_imports += ['email_validator', 'msgpack', 'requests']

# add backports and other commonly missing modules
hidden_imports += ['backports', 'backports.zoneinfo', 'backports.zoneinfo._tzpath']

# add pkg_resources and setuptools dependencies
try:
    hidden_imports += collect_submodules('pkg_resources')
except Exception:
    pass

try:
    hidden_imports += collect_submodules('setuptools')
except Exception:
    pass

# add Flask and WTForms dependencies
hidden_imports += ['flask.json', 'flask.json.tag']
hidden_imports += ['wtforms.fields', 'wtforms.validators', 'wtforms.widgets']
hidden_imports += ['werkzeug', 'werkzeug.routing', 'werkzeug.security']
hidden_imports += ['jinja2', 'jinja2.ext']
hidden_imports += ['importlib_metadata', 'importlib_resources']

a = Analysis(
    [os.path.join(project_root, 'mytral/run_desktop.py')],
    pathex=[project_root],
    binaries=extra_binaries,
    datas=mytral_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={
        'pkg_resources': {
            'data_subdirs': [],
        },
    },
    runtime_hooks=[],
    excludes=['tkinter', '_tkinter'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='mytral-$MytralVersion',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=$ShowConsole,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_root, 'mytral/static/favicon.ico'),
)
"@

$SpecFile = Join-Path $BuildDir "mytral.spec"
$SpecContent | Out-File -FilePath $SpecFile -Encoding utf8

Write-Host "Spec file created: $SpecFile" -ForegroundColor Green
