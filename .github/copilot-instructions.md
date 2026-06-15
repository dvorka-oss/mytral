# Copilot instructions

This document provides instructions to the copilot AI assistants and agents.

## General instructions

- Write beautiful code.
- Handle for errors, and exceptions and corner cases.
- Do good and don't be evil.

## Functional architecture instructions

- This repository is a monorepo of a sport training log web application.

## Technology stack instructions

- Frontend: HTML, CSS, JavaScript, Jinja templates and Tabler component and CSS framework.
- Backend: Python, Flask, WTForms, Bokeh.
- Persistence: JSON files, photos (*.jpg, *.png), data frames (*.parquet), sport recordings (*.gpx, *.tcx, *.fit) on the local filesystem.


## Backend code instructions

- Application backend is written in Python.
- Always use up to Python 3.11 language constructions and avoid newer language features.
- Work with backend code stored in the `mytral/` directory.
- Use Python 3.11 type hints - avoid Optional and Union from typing.
- Always start line comments (not docstrings) you generate with lowercase letter.
- Always use `numpy` docstring convention.
- Always use Google code style imports - import module, not symbols (except typing).
- Always use global imports at the top of the file.
- Never use local imports inside functions or methods.
- Use WTForms for forms and their validation.
- Use Bokeh for chart generation.
- `mytral/plugins.py` is MyTra's data import / export plugin architecture.
- `mytral/tasks` is MyTraL's framework for the execution of long running operations.
- `mytral/tasks/bulldozer.py` is MyTraL's multiprocessing-based framework used to parallelize and speed up computation heavy tasks.
- `mytral/releng.py` handles feature flags allowing to enable / disable MyTraL features.
- `mytral/config.py` handles MyTraL configuration from the environment and parameters to providing the configuration to the runtime.
- `mytral/routes.py` and `mytral/blueprints` implement Flask routes ~ the application URI space.


## Security instructions

- NEVER log, print, or output sensitive data such as passwords, tokens, API keys, secrets, or any authentication credentials.
- NEVER log form data that may contain sensitive information (e.g., password fields, password_confirm fields).
- When debugging authentication or user input, log only non-sensitive metadata (e.g., "Password validation successful" instead of actual password values).

## Backend code quality instructions

- ALWAYS follow CLEAN CODE principles.
- ALWAYS DRY (Do NOT Repeat Yourself) the code.
- ALWAYS write KISS (Keep It Simple Stupid) code.
- NEVER use hacks or workarounds to make tests pass - always write clean, production-quality code.
- NEVER add noqa comments to silence linters unless there's a legitimate architectural reason (not for test convenience).
- NEVER modify production code with ugly hacks just to make tests work - fix tests properly or remove them.
- Note that there is used `ruff check` with `pyproject.toml` for the Python code quality.
- Note that there is used `ruff format` with 88 columns for the Python formatting.
- Note that there is used `isort` for the Python imports sorting and `.isort.cfg` in the root directory.


## Frontend instructions

- Application frontend is written in Jinja templates served by the Flask server.
- Jinja templates contain HTML and CSS code bases on the `Tabler` framework.
- Use `Tabler` components and CSS styles and always review existing pages to make new code consistent with the existing code.
- When you use `badge` CSS class, always use corresponding `text-*-fg` class for the text color definition.
- Work with frontend Jinja templates code stored in the mytral/templates directory.
- Use Jinja formatting with 4 spaces indentation in templates.

## Test instructions

- Write Python backend tests for all the code.
- Use `pytest` for testing.
- Mark the tests with `@pytest.mark.mytral`.
- Each test (function) is structured into 3 sections: # GIVEN, # WHEN, and # THEN. # GIVEN section prepares the data, # WHEN section performs the actual test, and # THEN section asserts, checks and prints the results.
- Use `DONE` instead of emoji character ✓ (do not use emoji/unicode characters, use the text inside)

## Build instructions

- The project is built with `make`.
- Use `uv` for the Python dependency management.
- Use `pyproject.toml` to manage dependencies, build and testing.

## Deployment instructions

- Keep in mind that the project runs on the desktop by default.


