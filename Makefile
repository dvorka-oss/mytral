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
# EITHER you can setup everything (if you have Python 3.11 installed):
#
# make setup
# . ./.venv/bin/activate
#
# ... OR run targets step by step:
#
## install Python
# uv python install 3.11
## create virtual environment
# uv venv --python 3.11 .venv
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
PYTHON_VERSION := 3.11
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
	uv run ty check --python-version 3.11 mytral

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
	vibe
	uv run python -m mytral.run

.PHONY: runvdev
ifeq ($(OS),Windows_NT)
run-dev: .venv ## run MyTraL server on Windows w/ DEV data
	MYTRAL_DATA_DIR="$(subst \,/,$(USERPROFILE))/mytral-dev-data" \
	MYTRAL_DEBUG=true \
	MYTRAL_ENABLE_CACHE=true \
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
	MYTRAL_DATA_DIR=$(USER_HOME)/p/mytral/git/my-training-log-data-dev/development \
	MYTRAL_DEBUG=true \
	MYTRAL_ENABLE_CACHE=true \
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

run-preproduction: .venv ## run MyTraL server on Linux w/ PRE-PRODUCTION data
	MYTRAL_DEBUG=true \
	MYTRAL_INCARNATION=DESKTOP \
	MYTRAL_DATA_DIR=$(USER_HOME)/p/mytral/git/my-training-log-data-dev/pre-production \
	MYTRAL_SECRET_KEY=no-secret-for-development \
	MYTRAL_ENABLE_CACHE=true \
	MYTRAL_FF_GSHEETS_DVORKA_IMPORT=true \
	MYTRAL_FF_STRAVA_API_IMPORT=true \
	MYTRAL_FF_TASKS_DEV=true \
	MYTRAL_FF_IRM3D=true \
	uv run python -m mytral.run

.PHONY: run-production
run-production: .venv ## run MyTraL server w/ PRODUCTION data
	MYTRAL_DEBUG=true \
	MYTRAL_DATA_DIR=$(USER_HOME)/.local/share/mytral \
	uv run python -m mytral.run

.PHONY: run-demo
run-demo: .venv ## run MyTraL server on Linux w/ DEMO data
	MYTRAL_DATA_DIR=$(USER_HOME)/p/mytral/git/my-training-log-data-dev/demo \
	MYTRAL_DEBUG=true \
	MYTRAL_ENABLE_CACHE=true \
	MYTRAL_FF_IRM3D=true \
	MYTRAL_FF_TRIMP=true \
	MYTRAL_INCARNATION=DESKTOP \
	MYTRAL_SECRET_KEY=no-secret-for-demo \
	uv run python -m mytral.run

.PHONY: run-digi
run-digi: .venv ## run MyTraL server w/ DIGITALIZATION data
	MYTRAL_DEBUG=true \
	MYTRAL_DATA_DIR=$(USER_HOME)/p/mytral/git/my-training-log-data-dev/digitalization-1996-2023 \
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
	@cp -vf ./vibe/GH-COPILOT-INSTRUCTIONS.md ./.github/copilot-instructions.md
	copilot --allow-all-tools --banner

# Ollama (cloud) hosted GitHub Copilot CLI
# ollama models:
# - deepseek-v4-pro:cloud / deepseek-v4-flash:cloud
# - kimi-k2.5:cloud / kimi-k2.6:cloud
# - qwen3.5:cloud
.PHONY: vibe-copilot-ollama-deepseek
vibe-copilot-ollama-deepseek:
	@mkdir -pv ./.github
	@cp -vf ./vibe/GH-COPILOT-INSTRUCTIONS.md ./.github/copilot-instructions.md
	COPILOT_PROVIDER_MAX_PROMPT_TOKENS=840000 \
	COPILOT_PROVIDER_MAX_OUTPUT_TOKENS=128000 \
	ollama launch copilot-cli --model deepseek-v4-pro:cloud -- --allow-all-tools

# DeepSeek
# https://api-docs.deepseek.com/quick_start/agent_integrations/copilot_cli
.PHONY: vibe-copilot-deepseek
vibe-copilot-deepseek:
	@cp -vf ./vibe/COPILOT-INSTRUCTIONS.md ./DEEPSEEK.md
	COPILOT_PROVIDER_TYPE=anthropic \
	COPILOT_PROVIDER_BASE_URL=https://api.deepseek.com/anthropic \
	COPILOT_PROVIDER_API_KEY=$(DEEPSEEK_API_KEY) \
	COPILOT_MODEL=deepseek-v4-pro \
	COPILOT_PROVIDER_MAX_PROMPT_TOKENS=840000 \
	COPILOT_PROVIDER_MAX_OUTPUT_TOKENS=128000 \
	copilot --allow-all-tools --banner

# DeepSeek
# https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code
.PHONY: vibe-deepseek-cc
vibe-cc-deepseek:
	ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic \
	ANTHROPIC_AUTH_TOKEN=$(DEEPSEEK_API_KEY) \
	ANTHROPIC_MODEL=deepseek-v4-pro[1m] \
	ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro[1m] \
	ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-pro[1m] \
	ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash \
	CLAUDE_CODE_SUBAGENT_MODEL=deepseek-v4-flash \
	CLAUDE_CODE_EFFORT_LEVEL=max \
	claude --dangerously-skip-permissions

# Anthrop\c Claude Code
# - run vibe coding Anthropic Claude CODE harness w/ Ollama hosted models
# ollama models:
# - deepseek-v4-pro:cloud / deepseek-v4-flash:cloud
# - kimi-k2.7:cloud
# - qwen3.5:cloud
.PHONY: vibe-cc-ollama-deepseek
vibe-cc-ollama-deepseek:
	@cp -vf ./vibe/COPILOT-INSTRUCTIONS.md ./CLAUDE.md
	ollama launch claude --model deepseek-v4-pro:cloud -- --dangerously-skip-permissions

vibe-cc-ollama-kimi:
	@cp -vf ./vibe/COPILOT-INSTRUCTIONS.md ./CLAUDE.md
	ollama launch claude --model kimi-k2.7:cloud -- --dangerously-skip-permissions

.PHONY: vibe-cc-ollama-minimax
vibe-cc-ollama-minimax:
	@cp -vf ./vibe/COPILOT-INSTRUCTIONS.md ./CLAUDE.md
	ollama launch claude --model minimax-m3:cloud -- --dangerously-skip-permissions

.PHONY: vibe-cc-ollama-gemma4
vibe-cc-ollama-gemma4:
	@cp -vf ./vibe/COPILOT-INSTRUCTIONS.md ./CLAUDE.md
	ollama launch claude --model gemma4:31b-cloud -- --dangerously-skip-permissions

# Pi CLI
# - run vibe coding w/ Mario's Pi CLI
.PHONY: vibe-pi
vibe-pi:
	@cp -vf ./vibe/COPILOT-INSTRUCTIONS.md ./AGENT.md
	ollama launch pi --model qwen3.5:cloud

# Codex CLI
# - run vibe coding w/ OpenAI Codex CLI
.PHONY: vibe-codex
vibe-codex:
	@cp -vf ./vibe/COPILOT-INSTRUCTIONS.md ./AGENTS.md
	codex

# Google Antigravity CLI
# - run vibe coding w/ Google Antigravity CLI
.PHONY: vibe-agy
vibe-agy:
	@echo "Updating Antigravity instructions..."
	@cp -vf ./vibe/COPILOT-INSTRUCTIONS.md AGENTS.md
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

.PHONY: distro-desktop-test
distro-desktop-test: distro-desktop-build ## test the built desktop executable
	@echo "Testing desktop executable..."
	@ls -lh distro/desktop/mytral-* 2>/dev/null || ls -lh distro/desktop/mytral* 2>/dev/null || (echo "ERROR: No executable found in distro/desktop/"; exit 1)

#
# DOCUMENTATION
#

.PHONY: doc
doc-sync-data:
	@echo "Preparing data..."
	cp -vf CREDITS.md docs/CREDITS.md
	cp -vf CHANGELOG.md docs/CHANGELOG.md
	uv run python make/preprocess_license_to_markdown.py
	uv run python make/preprocess_licenses_to_markdown.py

.PHONY: doc
doc: doc-sync-data ## generate HTML documentation from Markdown sources
	@echo "Generating documentation from Markdown..."
	uv run python make/generate_docs_from_markdown.py
	@echo "DONE Documentation generated successfully"

.PHONY: doc-clean
doc-clean: ## clean generated documentation
	rm -f mytral/static/documentation/*.html
	@echo "Documentation cleaned"

.PHONY: doc-serve
doc-serve: doc ## serve documentation locally for preview
	@echo "Serving documentation at http://localhost:8080"
	uv run python -m http.server 8080 --directory mytral/static/documentation

#
# WEB: mytral.fitness
#

# INSTALL live server: npm install -g live-server
.PHONY: www-live-server
www-live-server: ## start live server for www.mytral.fitness development
	@cd webs/www.mytral.fitness && live-server ./

.PHONY: www-doc
www-doc: doc-sync-data ## generate public documentation for www.mytral.fitness
	@echo "Generating public documentation from Markdown..."
	uv run python make/generate_public_docs.py
	@echo "DONE Public documentation generated successfully"

.PHONY: www-doc-clean
www-doc-clean: ## clean generated public documentation
	rm -rf webs/www.mytral.fitness/docs/*.html
	rm -rf webs/www.mytral.fitness/docs/*.png
	@echo "Public documentation cleaned"

.PHONY: www-doc-serve
www-doc-serve: www-doc ## serve public documentation locally for preview
	@echo "Serving public documentation at http://localhost:8080"
	uv run python -m http.server 8080 --directory webs/www.mytral.fitness/docs

#
# DEPLOYMENT: mytral.fitness
#

.PHONY: deployment-spaceship-data-backup
deploy-spaceship-data-backup: ## backup SpaceShip.com data, use TARGET_DATA_DIRECTORY to also copy it
	cd ./deploy/spaceship.com && ./ftp-download-data.sh $(TARGET_DATA_DIRECTORY)

#
# DEPLOYMENT: Docker
#

docker-build-image: wheel ## build Docker image
	rm -rvf build/docker/*.whl
	cp distro/mytral-$(MYTRAL_VERSION)-py3-none-any.whl build/docker/
	cd build/docker && docker build --tag mytral:$(MYTRAL_VERSION) .
	docker images | grep mytral

.PHONY: docker-run
docker-run: ## run MyTraL Docker container on port 5500
	docker run -p 5500:5000 --name running-mytral mytral:latest

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
# CLEANUP
#

.PHONY: clean
clean: distro-desktop-clean distro-webapp-clean ## clean build relics
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

# pull production data from Git repository & sync blobs from the shared drive
PHONY: my-data-pull
my-data-pull:
	cd make && ./d_production_data_pull.sh

# push production data to Git repository & sync blobs to the shared drive
.PHONY: my-data-push
my-data-push:
	cd make && ./d_production_data_push.sh

.PHONY: my-data-zip
my-data-zip-snapshot:
	@timestamp=$$(date +%Y%m%d-%H%M%S); \
	archive=$(USER_HOME)/mytral-snapshot-$${timestamp}.tgz; \
	echo "Zipping production data to $${archive} ..."; \
	tar czf "$${archive}" -C $(USER_HOME)/.local/share mytral; \
	echo "DONE Archive created: $${archive}"
