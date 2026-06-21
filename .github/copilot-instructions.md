# Copilot instructions

This document provides instructions to coding agents.

## Project identity

- **MyTraL** — a personal sport training log web application (monorepo).
- **License**: AGPL-3.0.  **Python**: 3.11 only.  **Version**: `mytral/version.py`.
- **Run**: `uv run make run` (server), `uv run mytral-web` (CLI), `uv run mytral-desktop` (desktop).
- **Lint**: `uv run make py-lint` (ruff check + ruff format + isort).  **MANDATORY after every change.**
- **Test**: `uv run make test` (pytest).  **MANDATORY after every change.**
- **Build**: `make` + `uv` + `pyproject.toml` (hatchling build backend).

## Code quality principles — KISS, DRY, CLEAN CODE

These are the **most important** instructions in this document.  Follow them in every
line of code you write.  Violating them is worse than a failing test.

### KISS — Keep It Simple, Stupid

- The simplest solution that meets the requirements is the **correct** one.
- Do NOT over-engineer: no unnecessary abstractions, no premature generalization,
  no design patterns "just in case."
- A 5-line function that is obvious is better than a 3-line function that is clever.
- If you need a paragraph to explain what the code does, it is not KISS — refactor.
- **Concrete test**: would a new teammate understand your code in one reading?

### DRY — Don't Repeat Yourself

- Every piece of knowledge must have a **single, authoritative** representation.
- If you are about to copy-paste code, **stop** — extract a shared helper/function/macro.
- Shared constants go to `commons.py`.  Shared utilities go to `utils.py`.
- Shared Jinja snippets go to `macros/` or `includes/`.
- Shared form validation logic belongs in `forms.py`, not duplicated across routes.
- **Concrete test**: if a rule changes, would you edit exactly one place?

### CLEAN CODE

- **Functions do one thing** — small, focused, named for what they do.
- **Names are intention-revealing** — `calculate_weekly_training_load()` not `proc_wtl()`.
- **No magic numbers** — use named constants from `commons.py`.
- **No dead code** — never leave commented-out blocks; delete them.
- **No commented-out code** — the git history remembers; the file should not.
- **Consistent style** — match the existing code's patterns, naming, and structure.
- **Imports at top** — never at bottom, never inside functions, never relative.
- **No god-functions** — if a function exceeds ~40 lines, split it.
- **No god-files** — if a module exceeds ~500 lines, split it into a new package.

### When you violate these principles

You are creating **technical debt** that someone (probably you) will pay for later.
Every violation makes the codebase harder to understand, change, and test.
**Write code for the human reading it, not for the machine executing it.**

## Module map — what lives where

```
mytral/
├── __init__.py          # composition root: creates all application singletons
├── config.py            # MytralConfig, enums (PersistenceType, BlobStoreType, HostPlatform)
├── releng.py            # FeatureFlags (ff) — MYTRAL_FF_* env vars, ff.can("FEATURE")
├── loggers.py           # structlog configuration, MytralStructLogger (keyword args only!)
├── security.py          # bcrypt password hashing, Fernet encryption (MYTRAL_ENCRYPTION_KEY)
├── routes.py            # main Flask route handlers (home, activity CRUD, day, me, …)
├── forms.py             # all WTForms form classes (FlaskForm subclasses)
├── views.py             # view-model builders that prepare data for template rendering
├── settings.py          # domain entities: Gear, Goal, Exercise, Outfit, Lap, Symptom, …
├── commons.py           # shared constants, enums, small helpers
├── utils.py             # general utilities (getenv_bool, date helpers, …)
├── parsers.py           # input parsing/sanitization
├── plugins.py           # import/export plugin architecture (Plugin, PluginType enum)
├── charts.py            # Bokeh chart builders
├── stats.py             # training statistics computation
├── athlete_metrics.py   # athlete-level metrics (TRIMP, CTL/ATL/TSB, …)
├── insights.py          # insight generators (YoY, gear performance, sickness heatmap, …)
├── cals.py              # calorie calculations
├── ninjas.py            # miscellaneous domain logic
├── profilers.py         # performance profiling utilities
├── muscle_groups.py     # muscle group definitions
├── onboarding.py        # new-user onboarding checklist logic
├── bootstraps.py        # initial data bootstrapping for new accounts
├── migrations.py        # data migration between versions
├── ext.py               # Flask extensions / third-party integrations
├── cli.py               # CLI entry point (uv run mytral)
├── run.py               # web server entry point (uv run mytral-web)
├── run_desktop.py       # desktop app entry point (uv run mytral-desktop)
├── tools.py             # ad-hoc tools / swiss-knife scripts
│
├── backends/
│   ├── dataset.py       # MyTraLDataset facade — persistence-agnostic data access
│   ├── entities.py      # core domain entities (Activity, User, …)
│   ├── cache.py         # cache interface
│   ├── caches/          # InMemoryCache, PassthroughCache implementations
│   └── datasets/        # JsonUsersDataset — JSON-file persistence implementation
│
├── blueprints/          # Flask Blueprint route modules (URI-space modules)
│   ├── *_crud.py        # CRUD blueprints (gear, goal, exercise, activity_type, …)
│   └── *_uri_space.py   # feature-area blueprints (auth, import, export, health, maps, …)
│
├── blobstore/           # photo & attachment storage (filesystem default, optional MinIO/S3)
│   ├── abc.py           # AbstractBlobStore interface
│   ├── filesystem.py    # FilesystemBlobStore (default)
│   ├── activity_service.py / avatar_service.py / entity_photo_service.py
│   └── validation.py / image_processing.py
│
├── tasks/               # async task execution subsystem
│   ├── manager.py       # TaskManager — singleton, manages task lifecycle
│   ├── executor.py      # task executor interface
│   ├── executors/       # ThreadTaskExecutor implementation
│   ├── storage.py       # TaskStorage — JSON-file task persistence
│   ├── locks.py         # per-user task locking
│   ├── _entities.py     # Task entity definitions
│   └── do/              # concrete task implementations (strava_*, gpx_import, …)
│
├── integrations/        # external service integrations
│   ├── strava.py        # Strava API client
│   ├── concept2.py      # Concept2 logbook
│   ├── polar_hrm.py     # Polar HRM data
│   ├── google_sheets.py # Google Sheets import
│   └── *_recording.py   # recording format handlers (fit, gpx, tcx)
│
├── recordings/          # sport recording file parsers (FIT, GPX, TCX → Parquet)
│   ├── models.py        # recording data models
│   ├── fit_extractor.py / gpx_extractor.py / tcx_extractor.py
│   └── parquet_converter.py
│
├── ai/                  # AI coaching subsystem (pydantic-ai-slim, Claude/OpenAI)
│   ├── agent.py         # AI agent runner
│   ├── acoaches.py      # AI coach definitions
│   ├── providers.py     # LLM provider configuration
│   ├── context.py       # context assembly for AI prompts
│   └── settings.py      # AI coach settings entities
│
├── ml/                  # machine learning (xgboost, scikit-learn, tabpfn)
│   ├── ml_models.py     # ML model wrappers
│   ├── sick_model.py    # sickness prediction model
│   └── icl/             # in-context learning (TabPFN predictions)
│
├── middleware/          # Flask middleware (sync_guard — read-only mode during tasks)
├── notifications/       # user notification storage and entities
│
├── templates/           # Jinja templates (139 files)
│   ├── layout.html      # base layout (navigation, flash messages, task indicator)
│   ├── macros/          # reusable Jinja macros (activity-fields, buttons, maps, …)
│   └── includes/        # field-filter.html, field-filter-script.html
│
└── static/              # static assets (Tabler CSS/JS, Leaflet, KaTeX, images, …)
```

## Application singletons — how to access them

These are created in `mytral/__init__.py` and imported by all other modules.
**Never re-instantiate them — always import the singleton:**

```python
from mytral import app_config        # MytralConfig — port, paths, debug, encryption/signing keys
from mytral import app_ds            # MyTraLDataset — persistence-agnostic dataset facade
from mytral import app_user_ds       # user-scoped dataset (app_ds.user())
from mytral import app_blobstore     # blob store for photos & attachments
from mytral import app_task_manager  # TaskManager — async task lifecycle
from mytral import app_logger        # MytralStructLogger — structured logging
from mytral import ff                # FeatureFlags — ff.can("FEATURE_NAME")
```

## Architecture patterns

### Route organization
- **`routes.py`** — main page routes (home, activity CRUD, day, me, calendar, …).
- **`blueprints/*.py`** — feature-area routes registered as Flask Blueprints.
  - `*_crud.py` = CRUD operations for a domain entity (gear, goal, exercise, …).
  - `*_uri_space.py` = feature-area pages (auth, import, export, health, maps, …).
- Routes prepare data via `views.py`, handle forms from `forms.py`, render Jinja templates.

### Dataset facade
- `MyTraLDataset` (`backends/dataset.py`) is the persistence-agnostic API.
- Concrete implementation: `JsonUsersDataset` (`backends/datasets/dataset_json.py`) — JSON files.
- Access user data via `app_user_ds` (already user-scoped).
- Recording data stored as Parquet files alongside JSON.

### Task subsystem
- Long-running operations (imports, Strava sync, reprocessing) run as async tasks.
- `app_task_manager` handles lifecycle: create, start, cancel, query status.
- Task implementations in `tasks/do/` — each is a callable registered with the manager.
- Tasks persist state/logs as JSON files; UI polls status endpoints.

### Feature flags
- `ff.can("FEATURE_NAME")` checks if a feature is enabled.
- Features: TRIMP, PFN_PREDICTIONS, GSHEETS_DVORKA_IMPORT, STRAVA_API_IMPORT, TASKS_DEV, ACOACHES.
- Controlled by `MYTRAL_FF_*` environment variables.

### Plugin architecture
- `plugins.py` — `Plugin` base class, `PluginType` enum (ACTIVITIES_IMPORT, ACTIVITY_IMPORT, ENTITIES_IMPORT).
- Plugins allow users to import activities/entities from external formats and services.

## Technology stack — specific versions

| Layer          | Technology                                          |
|----------------|-----------------------------------------------------|
| Backend        | Python 3.11, Flask 3.1, WTForms 3.2                 |
| Charts         | Bokeh 3.8.2                                         |
| Data frames    | Polars 1.30 (NOT Pandas for production code)        |
| Logging        | structlog 25.5 (keyword args only, no positional)   |
| Auth           | bcrypt 5.0, cryptography 46.0 (Fernet)              |
| HTML sanitize  | bleach 6.3, markdown 3.10                           |
| AI/LLM         | pydantic-ai-slim 1.94, anthropic 0.101, openai 2.29 |
| ML             | xgboost-cpu 3.2, scikit-learn 1.5+, tabpfn 2.2+     |
| Frontend       | Tabler CSS/JS, Leaflet, KaTeX, Jinja templates      |
| HTTP           | requests 2.32, flask-cors 6.0                       |
| Geo            | polyline 2.0, rdp 0.8                               |
| Recordings     | fit-tool 0.9+, defusedxml 0.7                        |
| Serialization  | msgpack 1.0                                         |
| Validation     | email_validator 2.2                                  |
| Dev tools      | ruff 0.15, isort 7.0, mypy 1.18, pytest 8.4         |
| Build          | uv, hatchling, make                                  |

## Python code conventions

- **Python 3.11 only** — use `X | Y` unions, lowercase types (`list[str]`), never `Optional`/`Union`.
- **Imports**: ALWAYS import modules (not symbols), ALWAYS at top of file, NEVER local, NEVER relative.
  ```python
  # CORRECT
  import flask
  from mytral import app_config
  from mytral.backends import entities

  # WRONG
  from flask import Flask, request  # symbol import
  from . import utils               # relative import
  ```
- **Line comments** start with lowercase letter.  **Docstrings** use numpy convention.
- **Line length**: 88 columns (ruff format).  **Quotes**: double (`"`).
- **Logging**: use `app_logger.info("msg", key=value)` — keyword args only, never positional.
  ```python
  app_logger.info("user logged in", user=username, ip=remote_addr)
  ```
- **Security**: NEVER log passwords, tokens, API keys, secrets, or form data with sensitive fields.
- **No hacks**: never add `# noqa`, never write workarounds to make tests pass.

## Frontend conventions

- **Templates**: `mytral/templates/` — 4-space Jinja indentation (djlint configured).
- **Base layout**: `layout.html` — all pages extend it.
- **Reusable components**: `macros/` directory (activity-fields, buttons, maps, gear_components, …).
- **Tabler CSS framework**: use Tabler components and CSS classes.
- **Badges**: always pair `badge` with `text-*-fg` for text color.
- **Forms**: rendered with WTForms field macros, validated server-side.
- **Charts**: Bokeh charts embedded via `bokeh_components()` → Jinja `{{ script|safe }}` / `{{ div|safe }}`.
- **Maps**: Leaflet for GPX route visualization.

## Test conventions

- **Location**: `tests/` directory at repository root.
- **Framework**: pytest 8.4.  **Marker**: `@pytest.mark.mytral` on every test function.
- **Structure** — every test has 3 sections:
  ```python
  @pytest.mark.mytral
  def test_something():
      # GIVEN — prepare data/state
      ...
      # WHEN — perform the action under test
      ...
      # THEN — assert expected outcomes
      ...
  ```
- **Output**: use `DONE` text, never emoji/unicode characters like ✓.

## Persistence & data model

- **Users/activities/entities**: JSON files under `data/<user_id>/` on the local filesystem.
- **Recordings**: GPX, TCX, FIT files parsed into Parquet data frames for efficient querying.
- **Photos/attachments**: blob store (filesystem by default, optional MinIO or S3).
- **Tasks**: JSON state files + log files under `data/<user_id>/tasks/`.
- **Config**: environment variables prefixed `MYTRAL_` (see `config.py`).

## Deployment context

- **Default runtime**: desktop (local Flask server + browser window via flaskwebgui).
- **Production hosting**: pythonanywhere.com.  **Domain**: mytral.fitness.
- **Desktop packaging**: PyInstaller (via `dependency-groups.desktop`).

## Workflow checklist — after every code change

1. `uv run make py-lint` — MUST pass (ruff check + ruff format + isort).
2. `uv run make test` — MUST pass (pytest).
3. If lint fails: fix all issues, do NOT add `# noqa` comments.
4. If tests fail: fix production code properly, do NOT hack tests to pass.
