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


#  _   ___   __
# | | | \ \ / /
# | |_| |\ V /
#  \__,_| \_/
#
# This is a Makefile for uv/pyproject.toml centric development of the MyTral app.

###########################
# Project DEVELOPMENT setup
#
# EITHER you can setup everything (if you have Python 3.12 installed):
#
# make setup
# . ./.venv/bin/activate
#
# ... OR run targets step by step:
#
## install Python
# uv python install 3.12
## create virtual environment
# uv venv --python 3.12 .venv
## run project setup
# make setup
## activate virtual environment (if needed)
# . ./.venv/bin/activate

###########################
# Run the web app
#
## run MyTraL server
# uv run make run

###########################
# Tooling overview
#
# make:
#  - build automation
# uv:
#  - fast Python project and package manager (Rust)
#  - pyproject.toml configuration driven
#  - pip, virtualenv, twine, ... replacement
#  - https://docs.astral.sh/uv/
# ruff (via uv):
#  - fast linter and formatter (Rust)
#  - flake8, black, isort, ... replacement
#  - pyproject.toml configuration driven
#  - https://docs.astral.sh/ruff/
# hatch (via uv):
#  - Python build system
#  - pyproject.toml configuration driven
# pytest (via uv):
#  - Python test framework
#

###########################
# MyTraL CLI
#
# uv run mytral help
#

.DEFAULT_GOAL := help

#
# VARIABLES
#

# MyTraL version - propagated from version.py
MYTRAL_VERSION := $(shell uv run python -c "import sys; sys.path.insert(0, 'mytral'); import version; print(version.__version__)" 2>/dev/null || echo "dev")
# Python interpreter
PYTHON ?= python
# Python version
PYTHON_VERSION := 3.12
# virtual environment detection
ACTIVE_VENV := $(shell echo $$VIRTUAL_ENV)
# user home
USER_HOME := $(shell echo $$HOME)
# platform name for test reports
PLATFORM := $(shell uname -s)
# DeepSeek API key (for vibe coding with DeepSeek)
DEEPSEEK_API_KEY ?= $(shell pass show deepseek/apikey20260605)

#
# HELP
#

.PHONY: help
help: ## make targets help
	@echo " __  __      _____          _"
	@echo "|  \\/  |_   |_   _| __ __ _| |"
	@echo "| |\\/| | | | || || '__/ _\` | |"
	@echo "| |  | | |_| || || | | (_| | |___"
	@echo "|_|  |_|\\__, ||_||_|  \\__,_|_____| $(MYTRAL_VERSION)"
	@echo "        |___/"
	@echo ""
	@echo "MyTraL: My Trailing Log - Swiss knife:"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	| sort \
	| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

#
# PYTHON VIRTUAL ENVIRONMENT
#

.PHONY: venv-ensure
venv-ensure:
ifndef ACTIVE_VENV
	$(error Virtual environment is NOT active. Please ACTIVATE it first and make sure VIRTUAL_ENV shell variable is set)
endif

.PHONY: venv-reset
venv-reset: # (undocumented) reset virtual environment
	rm -rvf ./.venv
	make setup

.venv:
	uv venv --python $(PYTHON_VERSION) .venv

setup: .venv ## setup virtul env and install Python dependencies
	uv sync --all-groups

.PHONY: py-install-deps
py-install-deps: venv-ensure ## install Python wheel deps (not dev nor test)
	uv sync

.PHONY: py-install-dev-deps
py-install-dev-deps: venv-ensure
	uv sync --group dev

.PHONY: py-install-test-deps
py-install-test-deps: venv-ensure
	uv sync --group test

#
# LINTING
#

.PHONY: py-imports-sort
py-imports-sort: py-install-dev-deps
	find mytral -name '*.py' | xargs uv run isort

.PHONY: py-analysis
py-analysis: py-install-dev-deps ## lint source code
	uv run ruff check --output-format concise mytral

.PHONY: py-format
py-format: py-imports-sort ## format sources
	uv run ruff format mytral

.PHONY: py-test-imports-sort
py-test-imports-sort: py-install-dev-deps
	find tests -name '*.py' | xargs uv run isort

.PHONY: py-test-format
py-test-format: py-test-imports-sort ## format test sources
	uv run ruff format tests

.PHONY: py-test-analysis
py-test-analysis: py-install-dev-deps ## lint test code
	uv run ruff check --output-format concise tests

.PHONY: py-lint-mypy
py-lint-mypy: .venv py-install-dev-deps ## mypy type checking
	uv tool run mypy --install-types --non-interactive
	uv tool run mypy mytral

# TY static type checker:
# - https://pydevtools.com/handbook/reference/ty/
.PHONY: py-lint-ty
py-lint-ty: .venv py-install-dev-deps ## ty type checking
	uv run ty check --python-version 3.12 mytral

# check Bokeh version: Python Bokeh package and JavaScript Bokeh versions MUST MATCH
.PHONY: py-check-bokeh
py-check-bokeh: .venv py-install-dev-deps
	@echo "Verifying Bokeh versions:"
	@BOKEH_VERSION=$$(grep -E 'bokeh==' pyproject.toml | head -1 | sed 's/.*bokeh==//; s/".*//' | sed 's/,.*//'); \
	echo "  pyproject.toml:   $$BOKEH_VERSION"; \
	MISSING=0; \
	for JS_FILE in mytral/static/bokeh-$$BOKEH_VERSION.min.js \
	               mytral/static/bokeh-tables-$$BOKEH_VERSION.min.js \
	               mytral/static/bokeh-widgets-$$BOKEH_VERSION.min.js; do \
		if [ ! -f "$$JS_FILE" ]; then \
			echo "  ERROR: $$JS_FILE not found"; \
			MISSING=1; \
		else \
			echo "  mytral/static:    $$(basename $$JS_FILE)"; \
		fi; \
	done; \
	if [ $$MISSING -eq 1 ]; then \
		exit 1; \
	fi; \
	echo "  OK: All Bokeh versions match"

.PHONY: py-security
py-security: py-install-dev-deps ## run bandit security scan on Python sources (fails on HIGH severity)
	uv run bandit -r mytral -lll -x mytral/__pycache__
	uv run pip-audit

.PHONY: py-check-secrets
py-check-secrets: py-install-dev-deps ## scan for accidentally committed secrets
	uv run detect-secrets scan --baseline make/.secrets.baseline mytral

.PHONY: py-lint
py-lint: py-format py-analysis py-test-format py-test-analysis py-check-bokeh ## sort imports, format, lint, and check Bokeh versions for Python sources
	@echo "DONE"

.PHONY: py-loc
py-loc: ## count lines of Python source code (production + tests)
	@echo "Production code (mytral/):"
	@find mytral -name '*.py' | xargs wc -l | tail -1
	@echo "Tests (tests/):"
	@find tests -name '*.py' | xargs wc -l | tail -1
	@echo "Total:"
	@find mytral tests -name '*.py' | xargs wc -l | tail -1

.PHONY: jinja-check
jinja-check: py-install-dev-deps ## check Jinja templates with djlint
	@uv run djlint mytral --check # detailed
	#uv run djlint mytral --lint # brief

.PHONY: jinja-lint
jinja-lint: py-install-dev-deps ## lint Jinja templates with djlint
	#uv run djlint mytral --reformat
	true

.PHONY: lint
# TODO lint: jinja-lint py-lint ## alias for py-lint
lint: py-lint ## alias for py-lint
	@true

.PHONY: precommit
precommit: py-lint py-security ## pre-commit checks: lint and security scan
	@true

#
# DIAGNOSTICS
#

.PHONY: troubleshooting
troubleshooting: ## if cannot run MyTraL - diagnose system (ports, resources, ...)
	netstat -tulnp | grep 5000

#
# SYNCHRONIZE DATA
#

.PHONY: data-sync
data-sync:: ## synchronize ~ pull data in MyTraL data repository
	@echo "Synchronizing data ..."
	cd ../my-training-log-data-dev && git pull
	@echo "DONE"

#
# RUN
#

.PHONY: run
run: .venv ## run MyTraL server w/ ENV var specified data directory
	MYTRAL_ENABLE_CACHE=true \
	MYTRAL_INCARNATION=DESKTOP \
	uv run python -m mytral.run

.PHONY: runvdev
ifeq ($(OS),Windows_NT)
run-dev: .venv ## run MyTraL server on Windows w/ DEV data
	MYTRAL_DATA_DIR="$(subst \,/,$(USERPROFILE))/mytral-data/development" \
	MYTRAL_DEBUG=true \
	MYTRAL_ENABLE_CACHE=true \
	MYTRAL_FF_ACOACHES=true \
	MYTRAL_FF_GSHEETS_DVORKA_IMPORT=true \
	MYTRAL_FF_IRM3D=true \
	MYTRAL_FF_STRAVA_API_IMPORT=true \
	MYTRAL_FF_TASKS_DEV=true \
	MYTRAL_FF_TRIMP=true \
	MYTRAL_INCARNATION=DESKTOP \
	MYTRAL_SECRET_KEY=no-secret-for-development \
	MYTRAL_USER_REGISTRATION=true \
	uv run python -m mytral.run
else
run-dev: .venv ## run MyTraL server on Linux w/ DEV data
	MYTRAL_DATA_DIR=$(USER_HOME)/p/mytral/git/mytral-data/development \
	MYTRAL_DEBUG=true \
	MYTRAL_ENABLE_CACHE=true \
	MYTRAL_FF_ACOACHES=true \
	MYTRAL_FF_GSHEETS_DVORKA_IMPORT=true \
	MYTRAL_FF_IRM3D=true \
	MYTRAL_FF_STRAVA_API_IMPORT=true \
	MYTRAL_FF_TASKS_DEV=true \
	MYTRAL_FF_TRIMP=true \
	MYTRAL_INCARNATION=DESKTOP \
	MYTRAL_SECRET_KEY=no-secret-for-development \
	MYTRAL_USER_REGISTRATION=true \
	uv run python -m mytral.run
endif

run-preproduction: .venv ## run MyTraL server on Linux w/ DEMO data w/ production settings
	MYTRAL_DATA_DIR=$(USER_HOME)/p/mytral/git/mytral-data/pre-production \
	MYTRAL_DEBUG=true \
	MYTRAL_ENABLE_CACHE=true \
	MYTRAL_FF_GSHEETS_DVORKA_IMPORT=true \
	MYTRAL_FF_IRM3D=true \
	MYTRAL_FF_STRAVA_API_IMPORT=true \
	MYTRAL_FF_TASKS_DEV=true \
	MYTRAL_FF_TRIMP=true \
	MYTRAL_INCARNATION=DESKTOP \
	MYTRAL_SECRET_KEY=no-secret-for-development \
	uv run python -m mytral.run

.PHONY: run-production
run-production: .venv ## run MyTraL server w/ PRODUCTION data
	MYTRAL_DEBUG=true \
	MYTRAL_DATA_DIR=$(USER_HOME)/.local/share/mytral \
	uv run python -m mytral.run

.PHONY: run-demo
run-demo: .venv ## run MyTraL server on Linux w/ DEMO data
	MYTRAL_DATA_DIR=$(USER_HOME)/p/mytral/git/mytral-data/demo \
	MYTRAL_DEBUG=true \
	MYTRAL_ENABLE_CACHE=true \
	MYTRAL_FF_ACOACHES=true \
	MYTRAL_FF_IRM3D=true \
	MYTRAL_FF_STRAVA_API_IMPORT=true \
	MYTRAL_FF_TRIMP=true \
	MYTRAL_INCARNATION=DESKTOP \
	MYTRAL_SECRET_KEY=no-secret-for-demo \
	uv run python -m mytral.run

.PHONY: run-digi
run-digi: .venv ## run MyTraL server w/ DIGITALIZATION data
	MYTRAL_DEBUG=true \
	MYTRAL_DATA_DIR=$(USER_HOME)/p/mytral/git/mytral-data/digitalization-1996-2023 \
	MYTRAL_SECRET_KEY=no-secret-for-development \
	uv run python -m mytral.run

.PHONY: run-blank
run-blank: .venv ## run MyTraL server w/ NO data in /tmp directory
	MYTRAL_DEBUG=true \
	MYTRAL_DATA_DIR=/tmp \
	MYTRAL_AUTO_ACCOUNT_CREATE=true \
	MYTRAL_SECRET_KEY=no-secret-for-development \
	uv run python -m mytral.run

#
# VIBE CODING
#

# GitHub Copilot
# - run vibe coding w/ GitHub Copilot CLI
# ~/.copilot/* ... ~/.copilot/copilot-mcp.json
.PHONY: vibe-copilot
vibe-copilot:
	@mkdir -pv ./.github
	copilot --allow-all-tools --banner

# Ollama (cloud) hosted GitHub Copilot CLI
# ollama models:
# - deepseek-v4-pro:cloud / deepseek-v4-flash:cloud
# - kimi-k2.5:cloud / kimi-k2.6:cloud
# - qwen3.5:cloud
.PHONY: vibe-copilot-ollama-deepseek
vibe-copilot-ollama-deepseek:
	@mkdir -pv ./.github
	COPILOT_PROVIDER_MAX_PROMPT_TOKENS=840000 \
	COPILOT_PROVIDER_MAX_OUTPUT_TOKENS=128000 \
	ollama launch copilot-cli --model deepseek-v4-pro:cloud -- --allow-all-tools

# DeepSeek
# https://api-docs.deepseek.com/quick_start/agent_integrations/copilot_cli
.PHONY: vibe-copilot-deepseek
vibe-copilot-deepseek:
	@cp -vf ./.github/copilot-instructions.md ./DEEPSEEK.md
	COPILOT_PROVIDER_TYPE=anthropic \
	COPILOT_PROVIDER_BASE_URL=https://api.deepseek.com/anthropic \
	COPILOT_PROVIDER_API_KEY=$(DEEPSEEK_API_KEY) \
	COPILOT_MODEL=deepseek-v4-pro \
	COPILOT_PROVIDER_MAX_PROMPT_TOKENS=840000 \
	COPILOT_PROVIDER_MAX_OUTPUT_TOKENS=128000 \
	copilot --allow-all-tools --banner

# Anthropic Claude Code: ideally @ Sonnet 1M
.PHONE: vibe-cc
vibe-cc:
	@cp -vf ./.github/copilot-instructions.md ./CLAUDE.md
	claude --dangerously-skip-permissions

# DeepSeek
# https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code
.PHONY: vibe-deepseek-cc
vibe-cc-deepseek:
	@cp -vf ./.github/copilot-instructions.md ./CLAUDE.md
	ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic \
	ANTHROPIC_AUTH_TOKEN=$(DEEPSEEK_API_KEY) \
	ANTHROPIC_MODEL=deepseek-v4-pro[1m] \
	ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro[1m] \
	ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-pro[1m] \
	ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash \
	CLAUDE_CODE_SUBAGENT_MODEL=deepseek-v4-flash \
	CLAUDE_CODE_EFFORT_LEVEL=max \
	claude --dangerously-skip-permissions

# Z.ai
# https://ollama.com/library/glm-5
.PHONY: vibe-cc-ollama-glm
vibe-cc-ollama-glm:
	@cp -vf ./.github/copilot-instructions.md ./CLAUDE.md
	ollama launch claude --model glm-5:cloud -- --dangerously-skip-permissions

# Anthrop\c Claude Code
# - run vibe coding Anthropic Claude CODE harness w/ Ollama hosted models
# ollama models:
# - deepseek-v4-pro:cloud / deepseek-v4-flash:cloud
# - kimi-k2.7:cloud
# - qwen3.5:cloud
.PHONY: vibe-cc-ollama-deepseek
vibe-cc-ollama-deepseek:
	@cp -vf ./.github/copilot-instructions.md ./CLAUDE.md
	ollama launch claude --model deepseek-v4-pro:cloud -- --dangerously-skip-permissions

vibe-cc-ollama-kimi:
	@cp -vf ./.github/copilot-instructions.md ./CLAUDE.md
	ollama launch claude --model kimi-k2.7:cloud -- --dangerously-skip-permissions

.PHONY: vibe-cc-ollama-minimax
vibe-cc-ollama-minimax:
	@cp -vf ./.github/copilot-instructions.md ./CLAUDE.md
	ollama launch claude --model minimax-m3:cloud -- --dangerously-skip-permissions

.PHONY: vibe-cc-ollama-gemma4
vibe-cc-ollama-gemma4:
	@cp -vf ./.github/copilot-instructions.md ./CLAUDE.md
	ollama launch claude --model gemma4:31b-cloud -- --dangerously-skip-permissions

# Pi CLI
# - run vibe coding w/ Mario's Pi CLI
.PHONY: vibe-pi
vibe-pi:
	@cp -vf ./.github/copilot-instructions.md ./AGENT.md
	ollama launch pi --model qwen3.5:cloud

# Codex CLI
# - run vibe coding w/ OpenAI Codex CLI
.PHONY: vibe-codex
vibe-codex:
	@cp -vf ./.github/copilot-instructions.md ./AGENTS.md
	codex

# Google Antigravity CLI
# - run vibe coding w/ Google Antigravity CLI
.PHONY: vibe-agy
vibe-agy:
	@echo "Updating Antigravity instructions..."
	@cp -vf ./.github/copilot-instructions.md AGENTS.md
	agy --dangerously-skip-permissions

# Vibe coding - run a DEFAULT vibe coding CLI
.PHONY: vibe
vibe: vibe-copilot-ollama-deepseek
	@echo "DONE"

#
# PROTOTYPING
#

jupyter-run: .venv ## run Jupyter Lab
	uv sync --group notebook
	uv run jupyter lab

#
# IMPORT
#

import-gdoc: py-install-test-deps ## import from Google Docs
	$(PYTHON) -m pytest -ra tests/test_tool_import_gdocs.py::test_import_gdocs

import-google-docs: py-install-test-deps ## import activities from Strava export + Google Docs (comment out @pytest.mark.skip first)
	$(PYTHON) -m pytest -s tests/test_tool_import_google_docs.py::test_import_google_docs

#
# TEST
#

py-coverage: py-install-test-deps ## run Python tests with coverage report
	MYTRAL_ENCRYPTION_KEY=foo-random-key-for-tests \
	uv run pytest \
		--cov=mytral \
		--cov-report=html:tests/build/coverage-py \
		--cov-report=xml:tests/build/coverage.xml \
		--junit-prefix=$(PLATFORM) \
		--junitxml=tests/build/test-reports/TEST-mytral.xml \
		tests
	@echo "Coverage report generated at: file://$(PWD)/tests/build/coverage-py/index.html"

py-test: py-install-test-deps ## run Python tests
	MYTRAL_ENCRYPTION_KEY=foo-random-key-for-tests \
	$(PYTHON) -m pytest -ra --maxfail=10 tests/

.PHONY: test
test: py-test ## alias for py-test
	@true

#
# BENCHMARK
#

random-attack: py-install-test-deps ## run random attack benchmark w/ synthetic
	MYTRAL_TEST_RANDOM_ATTACK=true \
	MYTRAL_ENCRYPTION_KEY=foo-random-key-for-tests \
	$(PYTHON) -m pytest -s tests/test_random_attack.py
	cat /tmp/mytral-random-attack-data-dir.txt && MYTRAL_DATA_DIR=`cat /tmp/mytral-random-attack-data-dir.txt` make run

.PHONY: random-attack-watts
random-attack-watts: py-install-test-deps ## run random attack benchmark with synthetic watts for 3D IRM
	MYTRAL_TEST_RANDOM_ATTACK=true \
	MYTRAL_RANDOM_ATTACK_WATTS=true \
	MYTRAL_ENCRYPTION_KEY=foo-random-key-for-tests \
	$(PYTHON) -m pytest -s tests/test_random_attack.py::test_generate_mytral_dataset
	cat /tmp/mytral-random-attack-data-dir.txt && MYTRAL_DATA_DIR=`cat /tmp/mytral-random-attack-data-dir.txt` make run

#
# PACKAGING: wheel
#

.PHONY: requirements-txt
requirements-txt: ## generate requirements.txt from pyproject.toml (for deployments)
	uv pip compile pyproject.toml -o requirements.txt

.PHONY: wheel
wheel: ## build Python wheel
	uv build --out-dir distro/


#
# DISTRIBUTION: web application
#

DIR_DISTRO_WEBAPP = distro/webapp
DIR_DISTRO_DESKTOP = distro/desktop
DIR_DISTRO_DEB = distro/deb

.PHONY: distro-webapp-clean
distro-webapp-clean: ## clean web application distribution directory
	rm -rvf $(DIR_DISTRO_WEBAPP)

distro-webapp-build: distro-webapp-clean requirements-txt ## build web application distribution for PythonAnywhere hosting
	python3 make/distro_webapp_build.py

distro-webapp-test: distro-webapp-build ## test web application distribution
	@echo "Testing web application distribution..."
	rm -rvf /tmp/mytral-webapp-test
	mkdir -vp /tmp/mytral-webapp-test
	tar -xzf ./distro/webapp/mytral-$(MYTRAL_VERSION).tgz -C /tmp/mytral-webapp-test
	cd /tmp/mytral-webapp-test/mytral && uv venv --python $(PYTHON_VERSION) .venv
	cd /tmp/mytral-webapp-test/mytral && uv pip install -r requirements.txt && uv run python -m mytral.run
	@echo "DONE"

#
# DISTRIBUTION: upstream tarball
#

.PHONY: distro-tarball
distro-tarball: ## build upstream tarball (.tar.gz) for Linux distribution maintainers
	@./build/tarball/tarball-build.sh

.PHONY: distro-pad-refresh
distro-pad-refresh: ## refresh PAD.xml release fields (version, date, changelog, installer size)
	uv run python make/distro_pad_refresh.py

#
# DISTRIBUTION: Ubuntu PPA @ Launchpad
#

distro-launchpad-release:  ## build Ubuntu PPA package for Launchpad
	@cd build/ubuntu && \
	cp -vf ./launchpad-release.sh $(USER_HOME)/p/mytral/launchpad && \
	cd $(USER_HOME)/p/mytral/launchpad && \
	./launchpad-release.sh
	@echo "DONE: Ubuntu PPA package released to Launchpad in file://$(USER_HOME)/p/mytral/launchpad"

.PHONY: distro-ubuntu-deb
distro-ubuntu-deb: ## build Ubuntu .deb package locally (output to distro/deb/)
	@mkdir -p $(DIR_DISTRO_DEB)
	@cd build/ubuntu && \
	cp -vf ./launchpad-release.sh $(USER_HOME)/p/mytral/launchpad && \
	cd $(USER_HOME)/p/mytral/launchpad && \
	DRY_RUN=true ./launchpad-release.sh
	@find $(USER_HOME)/p/mytral/launchpad -name "mytral_*.deb" | \
	    xargs ls -t | head -1 | xargs -I{} cp -v {} $(DIR_DISTRO_DEB)/
	@echo "DONE: .deb package in file://$(CURDIR)/$(DIR_DISTRO_DEB)"

#
# DISTRIBUTION: desktop application
#

.PHONY: distro-desktop-build
distro-desktop-build: distro-desktop-deps ## build Linux desktop executable (air-gapped application)
	@./build/desktop/build-executable.sh

.PHONY: distro-desktop-build-win
distro-desktop-build-win: ## build Windows desktop executable
	powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build\desktop\build-executable.ps1

.PHONY: distro-desktop-build-win-logs
distro-desktop-build-win-logs: ## build Windows desktop executable with console window (shows logs)
	powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build\desktop\build-executable.ps1 -ShowConsole

.PHONY: distro-desktop-clean
distro-desktop-clean: ## clean Linux desktop distribution build artifacts
	@./build/desktop/clean.sh

.PHONY: distro-desktop-clean-win
distro-desktop-clean-win: ## clean Windows desktop distribution build artifacts
	powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build\desktop\clean.ps1

distro/desktop/mytral: distro-desktop-build
	@true

distro-desktop-install: distro/desktop/mytral ## install desktop application to ~/.local/bin
	@rm -vf ~/.local/bin/mytral ~/.local/share/applications/mytral.desktop
	@echo "Installing BINARY..."
	@cp -vf distro/desktop/mytral-$(MYTRAL_VERSION) ~/.local/bin/mytral
	@echo "Installing ICON..." # IMPROVE: ~/.local/share/icons/hicolor/256x256/apps/mytral.png
	@cp -vf mytral/static/images/mytral-logo-transparent-bg.png ~/.config/mytral/mytral.png
	@echo "Installing DESKTOP META..."
	@sed \
	-e 's|$(CURDIR)/distro/desktop/mytral|$(USER_HOME)/.local/bin/mytral|' \
	-e 's|Icon=mytral|Icon=$(USER_HOME)/.config/mytral/mytral.png|' \
	distro/desktop/mytral.desktop \
      > ~/.local/share/applications/mytral.desktop

#
# DISTRIBUTION: Windows installer (Inno Setup 6)
#
# Prerequisites:
#   1. Build desktop executable: make distro-desktop-build-win
#   2. Install Inno Setup 6:     https://jrsoftware.org/isinfo.php
#   3. Configure compiler path:  build\windows\env.bat
#

.PHONY: distro-win-installer
distro-win-installer: distro-win-clean distro-desktop-build-win  ## build Windows installer (.exe setup) from the desktop executable; requires Inno Setup 6
	.\build\windows\build-win-installer.bat

.PHONY: distro-win-zip
distro-win-zip: ## package Windows desktop executable into a ZIP archive — run after distro-desktop-build-win
	powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build\windows\build-win-zip.ps1

.PHONY: distro-win-clean
distro-win-clean: ## clean Windows installer build artifacts
	powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -Recurse -Force distro\windows -ErrorAction SilentlyContinue; Write-Host 'DONE: Windows installer artifacts removed'"

#
# SNAP: Snap package distribution (local builds only)
#
# Prerequisites:
#   # Snapcraft
#   sudo snap install snapcraft --classic
#   # LXD containers
#   sudo snap install lxd
#   sudo lxd init --auto
#   sudo usermod -aG lxd $USER
#

.PHONY: distro-snap-clean
distro-snap-clean: ## clean Snap build artifacts
	@./build/snap/clean.sh

.PHONY: distro-snap-remove
distro-snap-remove: ## remove locally installed Snap (requires sudo)
	@echo "Removing Snap package..."
	sudo snap remove mytral || true
	@echo "DONE Snap removed"

.PHONY: distro-snap-build
distro-snap-build: ## build Snap package (LXD required; see build/snap/build-snap.sh)
	@./build/snap/build-snap.sh

.PHONY: distro-snap-install-local
distro-snap-install-local: distro-snap-remove distro-snap-build ## build and install Snap locally (for testing, requires sudo)
	@echo "Installing Snap package locally..."
	@SNAP_FILE=$$(ls distro/snap/mytral_*.snap 2>/dev/null | head -1); \
	if [ -z "$$SNAP_FILE" ]; then \
		echo "Error: Snap package not found. Run 'make distro-snap-build' first."; \
		exit 1; \
	fi; \
	echo "Note: This command requires sudo privileges for snap install"; \
	sudo snap install --dangerous --classic "$$SNAP_FILE"; \
	echo "DONE Snap installed. Run with: mytral"

.PHONY: distro-snap-path
distro-snap-path: ## show path to built snap package
	@ls distro/snap/mytral_*.snap 2>/dev/null || echo "No snap package built yet"

.PHONY: distro-snap-upload
distro-snap-upload: ## upload Snap package to Snap Store
	@echo "Uploading Snap package to Snap Store..."
	snapcraft upload --release=stable mytral_$(MYTRAL_VERSION)_amd64.snap

#
# FLATPAK: Flatpak package distribution (local builds only)
#
# Prerequisites:
#   sudo apt install flatpak flatpak-builder   # or dnf/pacman/zypper equivalent
#   flatpak remote-add --if-not-exists --user flathub \
#       https://flathub.org/repo/flathub.flatpakrepo
#   flatpak install --user flathub \
#       org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08
#

.PHONY: distro-flatpak-clean
distro-flatpak-clean: ## clean Flatpak build artifacts
	@./build/flatpak/clean.sh

.PHONY: distro-flatpak-build
distro-flatpak-build: ## build Flatpak bundle (flatpak-builder + freedesktop 24.08 runtime/sdk required)
	@./build/flatpak/build-flatpak.sh

.PHONY: distro-flatpak-path
distro-flatpak-path: ## show path to built Flatpak bundle
	@ls distro/flatpak/mytral-*.flatpak 2>/dev/null || echo "No Flatpak bundle built yet"

.PHONY: distro-flatpak-remove
distro-flatpak-remove: ## remove locally installed Flatpak
	@echo "Removing Flatpak..."
	flatpak uninstall --user -y fitness.mytral.Mytral || true
	@echo "DONE Flatpak removed"

.PHONY: distro-flatpak-install-local
distro-flatpak-install-local: distro-flatpak-build ## build and install Flatpak locally (user scope, for testing)
	@echo "Installing Flatpak bundle locally..."
	@BUNDLE=$$(ls distro/flatpak/mytral-*.flatpak 2>/dev/null | head -1); \
	if [ -z "$$BUNDLE" ]; then \
		echo "Error: Flatpak bundle not found. Run 'make distro-flatpak-build' first."; \
		exit 1; \
	fi; \
	flatpak install --user --reinstall -y "$$BUNDLE"; \
	echo "DONE Flatpak installed. Run with: flatpak run fitness.mytral.Mytral"

#
# DOCUMENTATION
#

.PHONY: doc
doc-sync-data:
	@echo "Preparing data..."
	cp -vf CREDITS.md docs/CREDITS.md
	cp -vf CHANGELOG.md docs/CHANGELOG.md
	cp -vf INSTALLATION.md docs/INSTALLATION.md
	uv run python make/preprocess_license_to_markdown.py
	uv run python make/preprocess_licenses_to_markdown.py

.PHONY: doc
doc: doc-sync-data ## generate HTML documentation from Markdown sources
	@echo "Generating documentation from Markdown..."
	uv run python make/generate_docs_from_markdown.py
	@echo "DONE Documentation generated successfully to file://$(PWD)/mytral/static/documentation/index.html"

.PHONY: doc-clean
doc-clean: ## clean generated documentation
	rm -f mytral/static/documentation/*.html
	@echo "Documentation cleaned"

.PHONY: doc-live
doc-live: doc ## serve documentation locally for preview
	@echo "Serving documentation at http://localhost:8080"
	uv run python -m http.server 8080 --directory mytral/static/documentation

#
# WEB: mytral.fitness
#

# INSTALL live server: npm install -g live-server
.PHONY: www-live
www-live: ## start live server for www.mytral.fitness development
	@echo "Serving documentation at http://localhost:8080"
	uv run python -m http.server 8080 --directory webs/www.mytral.fitness

.PHONY: www-doc
www-doc: doc-sync-data ## generate public documentation for www.mytral.fitness
	@echo "Generating public documentation from Markdown..."
	uv run python make/generate_public_docs.py
	@echo "DONE Public documentation generated successfully to file://$(PWD)/webs/www.mytral.fitness/docs/index.html"

.PHONY: www-doc-clean
www-doc-clean: ## clean generated public documentation
	rm -rf webs/www.mytral.fitness/docs/*.html
	rm -rf webs/www.mytral.fitness/docs/*.png
	@echo "Public documentation cleaned"

.PHONY: www-doc-live
www-doc-live: www-doc ## serve public documentation locally for preview
	@echo "Serving public documentation at http://localhost:8080"
	uv run python -m http.server 8080 --directory webs/www.mytral.fitness/docs

.PHONY: www-banners
www-banners: ## generate Snapcraft/store feature banners (outputs to media/banners/)
	@echo "Generating banners..."
	uv run python media/banners/make_banners.py
	@echo "DONE Banners saved to media/banners/"

#
# DEPLOYMENT: mytral.fitness
#

.PHONY: deployment-spaceship-data-backup
deploy-spaceship-data-backup: ## backup SpaceShip.com data, use TARGET_DATA_DIRECTORY to also copy it
	cd ./deploy/spaceship.com && ./ftp-download-data.sh $(TARGET_DATA_DIRECTORY)

#
# DEPLOYMENT: Docker
#

.PHONY: distro-docker-debian-build
distro-docker-debian-build: ## build Docker Debian image with MyTraL inside
	@./build/docker/debian/build.sh

.PHONY: distro-docker-debian-run
distro-docker-debian-run: ## run MyTraL Docker Debian container (http://localhost:8888)
	@./build/docker/debian/run.sh

.PHONY: distro-docker-fedora-build
distro-docker-fedora-build: ## build Docker Fedora image with MyTraL inside
	@./build/docker/fedora/build.sh

.PHONY: distro-docker-fedora-run
distro-docker-fedora-run: ## run MyTraL Docker Fedora container (http://localhost:8888)
	@./build/docker/fedora/run.sh

#
# DEPLOYMENT: k8s (k3s, k9s)
#

.PHONY: k8s-deploy
k8s-deploy:  ## deploy MyTraL to Kubernetes
	kubectl apply -f build/k8s/mytral-deployment.yaml
	kubectl get namespaces
	kubectl get pods --namespace mytral
	kubectl get services --namespace mytral
	kubectl get ingress --namespace mytral

#
# DEPLOYMENT: Desktop
#

.PHONY: distro-desktop-deps
distro-desktop-deps: .venv ## install desktop application dependencies
	uv sync --group desktop

.PHONY: distro-desktop-run
distro-desktop-run: .venv ## run MyTraL in desktop mode (development)
	uv run python -m mytral.run_desktop

#
# RELEASE
#

release-distros-linux: clean distro-snap-clean distro-flatpak-clean distro-tarball distro-snap-build distro-flatpak-build ## build all LINUX distribution packages for release
	@echo "ALL Linux distribution packages built for release"

release-distros-win: clean distro-win-clean distro-desktop-build-win distro-win-installer ## build all WIN distribution packages for release
	@echo "ALL Win distribution packages built for release"

.PHONY: release-distros-macos
release-distros-macos:  ## build all MACOS distribution packages for release
	@echo "ALL MacOS distribution packages built for release"

#
# CLEANUP
#

.PHONY: clean
clean: distro-desktop-clean distro-webapp-clean distro-snap-clean ## clean build relics
	rm -vf GEMINI.md
	rm -vf requirements*.txt
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rvf distro data
	rm -vf build/desktop/mytral.spec

.PHONY: purge
purge: clean ## deep clean - remove all build and data relics - DANGEROUS
	@echo "All build and data relics purged"

#
# TOOLS
#

.PHONY: tool-parquet-viewer
tool-parquet-viewer: ## run Squey - Parquet viewer
	flatpak run org.squey.Squey

tool-pyproject-as-yaml: ## convert pyproject.toml to JSON
	python3 -c "import tomllib, json, sys; print(json.dumps(tomllib.loads(sys.stdin.read()), indent=2))" < pyproject.toml

#
# USER SPECIFIC PRODUCTION DATA MANAGEMENT
#

.PHONY: my-data-zip
my-data-zip-snapshot:
	@timestamp=$$(date +%Y%m%d-%H%M%S); \
	archive=$(USER_HOME)/mytral-snapshot-$${timestamp}.tgz; \
	echo "Zipping production data to $${archive} ..."; \
	tar czf "$${archive}" -C $(USER_HOME)/.local/share mytral; \
	echo "DONE Archive created: $${archive}"
