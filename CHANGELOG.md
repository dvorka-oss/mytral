# Changelog

## [1.55.0](https://github.com/dvorka-oss/mytral/compare/v1.54.0...HEAD)

This MyTraL **minor** release brings:

### Changed
- Switched from Python 3.11 to Python 3.12. The main reason is that Snap 22 runtime
  had Python 3.10 and Snap 24 runtime has Python 3.12. New Python constructs - like
  `type`, `override`, and `T` - will be incorporated as I go.

### Added
- .

### Fixed
- Fixed "missing waitress" server in the MyTraL installation from PPA `apt` log.

### Performance
- .

## Documentation
- .



## [1.54.0](https://github.com/dvorka-oss/mytral/compare/v1.53.0...v1.54.0)

This MyTraL **minor** release brings:

### Fixed
- Fixed and refactored Snap distribution builder to have `snapcraft.io` on repository
  paths required by snapcraft.io, use host's vs. container's resources correctly,
  and avoid use of (host) hard-coded paths.



## [1.53.0](https://github.com/dvorka-oss/mytral/compare/v1.52.0...v1.53.0)

This MyTraL **minor** release brings:

### Added
- Added Windows installer built with Inno Setup 6 (`build/windows/installer/mytral-setup.iss`).
  Installs to `C:\Program Files\MyTraL\`, registers an uninstaller, and optionally creates
  a Desktop shortcut.
- Added `distro-windows-installer` Makefile target to build the Windows installer after the
  desktop executable is built with `distro-desktop-build-win`.
- Added `distro-windows-clean` Makefile target to remove Windows installer build artifacts.
- Added Ubuntu PPA distribution for Ubuntu via Launchpad (`ppa:ultradvorka/sport`).
- Added `distro-ubuntu-deb` Makefile target to build `.deb` package locally.
- Added Snap package distribution for universal Linux package management. Opens a native
  desktop window via FlaskUI via classic confinement. User data stored in default
  locations.

### Fixed
- Fixed elevation chart rendering in the application's analysis page by smoothing
  the GPX points.
- Fixed `.deb` packaging: Python dependencies are installed into an isolated virtualenv at
  `/opt/mytral/venv/` - system Python environment is never polluted.
- Fixed `.deb` wrapper scripts to export `MYTRAL_INCARNATION`, `MYTRAL_USER_REGISTRATION`,
  and `MYTRAL_ENABLE_CACHE` environment variables for correct desktop startup.

### Performance
- Fixed top calendar week navigation which was slooow as it was build on the frontend -
  moved it to the backend.
- Fixed top feed day navigation which was slooow as it was build on the frontend -
  moved it to the backend.
- Fixed duplicated activities list loading by the `routes.py::calendar_view()`

## Documentation
- Added MyTraL configuration guide.
- Added Ubuntu PPA installation guide.
- Added Ubuntu .deb installation guide.



## [1.52.0](https://github.com/dvorka-oss/mytral/compare/v1.51.0...v1.52.0)

This MyTraL **minor** release brings:

### Added
- Added Windows 10 distribution build to GH release.

### Fixed
- Fixed Desktop binary environment variables based setup so that athletes can create
  accounts OOTB.

## Documentation
- Added Ubuntu distribution build guide.
- Added Python @ Ubuntu distribution guide.
- Added Debian @ Docker distribution guide.
- Added Fedora @ Docker distribution guide.



## [1.51.0](https://github.com/dvorka-oss/mytral/compare/v1.50.0...v1.51.0)

This MyTraL **minor** release brings:

### Added
- Added activity type color border hint to goals, gear, and several other pages.
- Added Strava synchronization of individual activities from the activity GET page.
- Added card encouraging athlete to create an activity to pages which need at least one
  activity to render.
- Added weight to gear.
- Added tarball distribution.
- Added Debian @ Docker distribution.
- Added Fedora @ Docker distribution.
- Added weight field to gear model allowing track the weight of your gear like running
  shoes, or bikes.

### Fixed
- Fixed km / hour usage of retired gears with no history.
- Fixed exercise / symptom delete message to contain display name (not UUID) when
  removing these entities from an activity.
- Removed color from Strava links on the day activities view and search result view.
- Fixed exercise and symptom delete pages to show display names instead of UUIDs.

## Documentation
- Adding the installation documentation.



## [1.50.0](https://github.com/dvorka-oss/mytral/compare/v1.9.0...v1.50.0)

This MyTraL release is very **special** to me. After years of coding and hacking
together various versions of MyTraL I am moving to a brand-new Git repository on my 50th
birthday.

Sports have been my main hobby for 40 years - I have 30 years of training data scattered
across everything from paper logs to MyTraL. Today, I’m starting a fresh chapter - free
from hacks, sensitive data and the "sins of my youth."

Channeling Steve Prefontaine energy today - pure heart, max effort, FLOSS execution!

### Added
- Added polyline with map background to the activity feed.
- Added rainbow polyline w/ running dot to the activity feed.
- Added elevation chart to the activity feed.
- Added "maximize map" action to the activity view page.
- Added description field to symptoms so that user can specify how to cure such injury
  or illness.
- Added import of Strava bulk user export ZIP archive (activities, GPX/TCX recordings,
  photos).
- Added TCX import (individual files and directory of recordings/archives).
- Added `gender` field to the athlete profile in order to calculate metrics like TRIMP
  more accurately.
- Added TRIMP calculation and chart to the `Progress` menu.
- Added FIT directory import - import all FIT files from a local directory in one go,
  with automatic conflict detection and parquet generation.
- Bulldozer framework - a multiprocessing-based sandboxed job runner for
  parallelizing CPU-bound import workloads across multiple cores.
- GPX polyline encoding with 2 selectable methods: fast distance-based sampling
  (default) and legacy RDP-based simplification for preview rendering. New GPX polyline
  encoding is ~4000× faster with the new distance-based sampling method - the default
  for all recording import paths.
- Added meta sport taxonomy based lifetime totals insight page.
- Added new cards on the homepage indicating the risk of injury, gear needed service,
  suggested activity and weight balance.
- Added resting HR estimate to the athlete metrics page.

### Changed
- Strava API import is not hidden behing feature flag (just inverse condition on FE).
- Refactored Predictions insight page to two pages - Predictions and Analytics.
- Rewritten task manager, tasks and tasks invocation - removed duplicated task manager
  definitions, converged to MyTraL's task manager, typed tasks are used from now on.
- Strava bulk ZIP archive import rewritten with Bulldozer framework for parallel
  photo & recording upload, parquet conversion, and GPX map-data precomputation.
- Polar Precision Performance import rewritten with Bulldozer framework - HRM blob
  upload and parquet generation now run in .

### Removed
- Removed `Suffer Score` from the ActivityEntity and related forms and HTML code.

### Fixed
- Fixed blobstore logging message which no longer specifies wrong blob type.
- Polar HRM import conflict resolution no longer fails on missing year-cache entries.
- `fit_tool` monkeypatch tolerates non-UTF8 bytes in FIT string fields (Garmin
  developer fields), preventing silent parse failures.
- Fixed many problems in the Polar PPP import - from user forgetting to switch
  the activity type, to the source of data (HRM vs. PDD) and the right units.
- Fixed notifications decorator - it's newly tightly coupled w/ the icon.



## [1.9.0](https://github.com/dvorka-oss/my-training-log/compare/v1.8.0...v1.9.0)

This MyTraL **minor** release brings:

### Added
- Added import from FIT.
- Added import from GPX - file or directory.
- Added GPX recording management: upload, view metadata, edit name/description/keywords,
  download, and delete.
- Added storing of recorded data (FIT, GPX, Polar HRM) to Parquet and Polars-based
  loading/saving.
- Added power zones.
- Added HR zones.
- Added 2D maps rendering for GPX recordings.
- Added athlete performance metrics w/ FTP, aerobic/anaerobic thresholds, ... estimates.
- Added recorded data analytics - ridge/bar/line charts of various metrics.
- Added multi-photo upload support for activities - up to 50 photos per activity.
- Added outfits selection to activity create and update (all) forms.
- Added outfits display to activity detail page.
- Added sickness / injury in time chart.
- Added day-based navigation to the activity feed.
- Added week-based navigation to the caledar activity view.
- Added avatar/photo upload support for users, AI coaches, gear, goals, and exercises.
- Added preview of TabPFN ML-powered predictions feature with dedicated settings and
  predictions pages (behind feature flag).
- Added sponsor link to the application layout.
- Added Windows binary build.
- Added and expanded sport taxonomy and mappings (new meta_activity_type, many new AT_*
  constants, Strava/FIT mappings, Concept2 uses AT_ROW_ERG).
- Enriched bootstraps for activity types, exercises, and symptoms (muscle groups,
  descriptions/default weights, symptom body-part targeting) with new pytest coverage.

### Changed
- Core data model changes:
  - `ActivityEntity.sport` renamed to `ActivityEntity.activity_type_key` - breaks
    backward compatibility.
  - Added `ActivityEntity.avg_cadence` and `ActivityEntity.max_cadence` - consider
    rides, rowing, swimming, and other activities.
  - Added `ActivityEntity.meta_activity_type` - consider `ski` aggregating DP/F roller
    ski, DP/F nordic ski, ...
  - Added `ActivityEntity.tags`.
  - Added `ActivityEntity.is_plan`.
- Reworked photo UI flows (entity photo galleries, activity/exercise photo metadata
  editor pages, markdown image support) and updated documentation site pages.
- Data migration framework:
  - Migration step: rename sport to activity type in activities and gears.
  - Migration step: merge new activity types, exercises and symptoms.
  - Expert UI tool: migration of activities from one activity type to another.
  - Python tool: re-sync Strava activities to re-new lost source attributes.

### Fixed
- Activity update no longer purges source attributes (ID, descriptor and URL).
- Blobstore exception handling in activity view/update routes now only silently ignores
  expected `BlobStoreError`; unexpected errors are logged and re-raised for easier
  debugging.
- GPX import rewritten to be non-blocking (except upload) and to make intensive work in
  the asynchronous task.

### Performance
- Per-request total size limit is now enforced when uploading multiple photos in a
  single request, preventing excessive memory use.
- EXIF metadata stripping in image processing no longer materialises the full pixel
  array into a Python list; metadata is cleared in-place, reducing memory allocation
  significantly for large images.

### Documentation
- HTML documentation is newly generated from Markdown files in this repository.
- Public HTML documentation for mytral.fitness is newly generated from Markdown files in
  this repository.

### Tests
- Added random attack which generates synthetic data of all MyTraL entities including
  attachments and recordings.



## [1.8.0](https://github.com/dvorka-oss/my-training-log/compare/v1.7.0...v1.8.0)

This MyTraL **minor** release brings:

### Added
- ACoaches - AI coaching feature powered by LLM providers:
  - Configure LLM providers: local Ollama, Anthropic Claude,
    or OpenAI GPT — each with optional API key stored encrypted at rest.
  - Define AI coaches with custom names and system prompts (personality, focus area,
    coaching style); built-in out-of-the-box prompt templates to get started quickly.
  - Persistent multi-turn chat sessions with each coach — full history saved per user.
  - Context-aware responses: coaches automatically receive recent activities, PRs,
    gear, symptoms, and athlete profile as structured context with every message.
  - Streaming responses for real-time token-by-token output in the chat UI.
  - Fetch available models directly from a running Ollama instance.
  - New dependencies: `anthropic`, `openai`, `pydantic-ai`, `griffe`.
- Extensibility API: introducing ability of pluggable activities importers.
- Desktop and webapp MyTraL incarnation which controls sign-up and log-in process.
- Users are newly allowed to enable auto-login on desktop.
- Dashboard revamp for better UX - advanced charts refactored to `Insights`,
  this vs. last month moved to the dashboard.
- Injection of feature flags to Jinja templates.
- Import of activities from Concept2 CSV, Google Sheets CSV, MyTraL JSON.
- Import of entities from MyTraL JSON files.
- Rewritten Strava API (developer) integration (deprecated due to legal term changes).

### Fixed
- Completely rewritten MyTraL configuration, ability to configure MyTraL using environment
  variables and default values.
- Fixed directory resolution and use to by compliant with XDG base directory specification
  https://specifications.freedesktop.org/basedir-spec/latest/
- Removed `desktop.key` to ensure portability in case that MyTraL is used on different
  machines which share the data.
- Fixed discarded fields when updating activities - add/edit/delete
  exercises/lap/symptom while other fields were modified lead to the loss of data.
- Fixed desktop distribution build as it became the main distribution incarnation going
  forward.



## [1.7.0](https://github.com/dvorka-oss/my-training-log/compare/v1.6.0...v1.7.0)

This MyTraL **minor** release brings:

### Added
- Ability to specify muscle groups for exercises and activity types - shown in
  the activity detail and day pages.
- Ability to specify body part for symptoms - shown in `Me` page.
- Muscle group heatmap in the day presented as manequinn.
- Previous / next day navigation in the day and activity view.
- Structured logging using `structlog`.
- User dataset size statistics to the account page.

### Performance
- Deployments and build configuration upgraded from Python 3.10 to Python 3.11.
- Source code migrated to 3.11 constructions like `match` or `Self`.

### Fixed
- Progress/PRs grouping based on time e.g. 30' laps.



## [1.6.0](https://github.com/dvorka-oss/my-training-log/compare/v1.5.0...v1.6.0)

This MyTraL **minor** release brings:

### Added
- Filtering of fields in create / update activity HTML pages.
- Filtering of exercise types by tag.
- Markdown support for activity, exercise type, gear, outfit, goal, and lap/route descriptions.
- Ranked laps: added `ranked` boolean field to `LapEntity` so individual laps within
  an activity can be marked as personal bests, mirroring the existing `ranked` flag on
  activities.
- Progress / PRs page now includes ranked laps in addition to ranked activities, showing
  lap name, distance, duration, activity types, and date with a link back to the parent activity.

### Performance
- DRY of Jinja templates - new macros and includes.

### Security
* Moved Flask `SECRET_KEY` to `MYTRAL_SECRET_KEY` (with a random per-start fallback +
  warning) and restricted CORS origins via `MYTRAL_CORS_ORIGINS`.
* Made debug mode configurable via `MYTRAL_DEBUG` and default server bind host
  configurable via `MYTRAL_HOST` (default `127.0.0.1`).
* Upgraded password hashing to `bcrypt` and introduced backward-compatible verification
  for legacy `SHA-256` hashes; updated login to use `verify_password`.
* Hardened Strava integration: `HTTPS` OAuth authorize URL, removed token logging, and
  switched activity export to `Authorization: Bearer` instead of query-string tokens.
* Fixed several runtime issues in routes (invalid `enum`/`int` handling, uninitialized
  variables, and incorrect activity key type).
* Fixed negative index exploitation: added `index < 1` guard after `int(index)`
  conversion in exercise and symptom update/delete routes to prevent `pop(-1)` silently
  deleting the last list element.
* Fixed timing side-channel in legacy `SHA-256` password verification: replaced `==`
  with `hmac.compare_digest()`.
* Fixed CORS origins parsing: added `.strip()` to each origin to prevent
  leading/trailing whitespace causing origin mismatches.
* Added `URL` and `DSN` to env-var redaction blocklist on the admin/settings page to
  prevent credential-bearing connection strings from leaking.
* Added boot-time warning log when `MYTRAL_CORS_ORIGINS` is not set in the environment.
* Added `RuntimeError` fail-fast guard in `run.py` when `debug=True` is combined with a
  non-loopback `MYTRAL_HOST` to prevent accidental remote debugger exposure.
* Added unit tests for `hash_password` and `verify_password` covering `bcrypt`, legacy
  `SHA-256`, wrong passwords, and empty inputs.

### Fixed
- Fixed `enable_cache=False` (passthrough) mode: activities were still served from stale
  in-memory data on subsequent requests because `dataset_name()` and `set_dataset_name()`
  were not overridden in `PassthroughUserCache`, causing `_load()` to skip filesystem
  re-reads after the first request. Both methods are now overridden so every request
  always reloads activity data from the filesystem.

### Infrastructure
- All dependencies and dev dependency group items pinned with `~=` in `pyproject.toml`.
- Security: upgraded `bokeh` 3.6.3 → 3.8.2 (CVE-2026-21883), `flask` 3.1.0 → 3.1.3
  (CVE-2025-47278, CVE-2026-27205), `flask-cors` 5.0.0 → 6.0.2 (CVE-2024-6866,
  CVE-2024-6844, CVE-2024-6839), `jinja2` 3.1.5 → 3.1.6 (CVE-2025-27516), `pillow`
  11.1.0 → 12.1.1 (CVE-2026-25990), `requests` 2.32.3 → 2.32.5 (CVE-2024-47081),
  `tornado` 6.4.2 → 6.5.4 (CVE-2025-47287), `urllib3` 2.3.0 → 2.6.3 (CVE-2025-50182,
  CVE-2025-50181, CVE-2025-66418, CVE-2025-66471, CVE-2026-21441), `werkzeug` 3.1.3 →
  3.1.6 (CVE-2025-66221, CVE-2026-21860, CVE-2026-27199).



## [1.5.0](https://github.com/dvorka-oss/my-training-log/compare/v1.4.0...v1.5.0)

This MyTraL **minor** release brings:

### Added
- Eisenhower matrix HTML page for goals.
- Ability to tag exercises to filter them and to create routines/sets.
- Admin view with the deployment environment introspection.

### Removed
- `CLAUDE.md` removed as its content is getting obsolete
   (GitHub copilot and Augment AI is used for agent assisted coding).
- `pip` based `Makefile` as well as `requirements*.txt` files removed as switch to `uv`
  is definitive and there is no need to keep these files with gradually obsolete content.

### Fixed
- Fixed unexplainable set of minutes and seconds when creating / updating an activity.
- Units format and hints in charts y-axis legends as well as charts hover-over tooltips.
- GitHub Actions workflows to use `uv` instead of `pip`.
- Fixed deading and writing of unicode characters, like emojis, by forcing UTF-8 encoding
  in JSON IO persistence functions.

### Documentation
- HTML documentation scripts revamp.
- Added "Why MyTraL?" HTML documentation page.
- End to end review of sources to ensure AGPL license omnipresence.
- SpaceShip.com deployment documentation and artifacts.

### Infrastructure
- Switched from `black`, `isort` and `flake8` to `ruff` for configurability and speed.
- Code quality toolchain configuration moved from files to `pyproject.toml`.
- Makefile target to sync data between SpaceShip.com and localhost.
- Updated 2026 year in the copyright.



## [1.4.0](https://github.com/dvorka-oss/my-training-log/compare/v1.3.0...v1.4.0)

This MyTraL **minor** release brings:

### Added
- Pass through cache allowing to operate on system where caching would cause data inconsistency
  (data modified & uploaded to cache on 1 node and then overwritten on another node).



## 1.3.2

This MyTraL **minor** release brings:

### Added
- Weight graph shows the Monday's date instead of the week number.
- Goals listing page shows activity type display name instead of the ID.



## 1.3.0

This MyTraL **minor** release brings:

### Added
- Onboarding logic:
  - checklist feature with progress tracking
  - User onboarding state management
  - Checklist items for profile completion and gear setup
  - Completion percentage calculation
  - Dismiss and reset functionality for onboarding

### Fixed
- Fixed strava.com import failing due to printing non-ASCII characters to console.



## 1.2.0

This MyTraL **minor** release brings:

### Added
- Gear Components Feature: Track individual components of gear items
  - Add, edit, delete components for any gear (e.g., bike chain, running shoe insoles)
  - Automatic usage tracking from activities (distance and time)
  - Service interval monitoring (km, hours, and time-based)
  - Visual notifications when components require service
  - Service history recording with costs
  - Component replacement workflow with chain tracking
  - Component status management (active/retired)
  - Total Cost of Ownership (TCoO) includes all component and service costs
  - Support for multiple service intervals per component
  - Attention indicators in gear list showing components needing service
- Settings:
  - Added 4 metrics for goals, exercises, symptoms, laps and outfits.

### Changed
- Changed activities and settings (gear, exercises, symptoms, ...) JSON persistence from dicts to lists.
- Enhanced Gear class to support components and component history.
- Updated gear list to show service attention indicators.
- Updated gear detail page to show components table.
- Improved TCoO calculation to include all component costs.
- Activity creation/update now tracks component usage automatically.

### Infrastructure
- Added web application distribution build.
- Rewritten desktop application executable build.



## 1.1.0

This MyTraL **minor** release brings:

### Added
- Lap type data model entity, forms, routes and HTML pages.
- Day view.
- Activity feed view.
- Body diagram with interactive injuries and sicknesses filtering.

### Changed
- Removed `activity_key` field in the `activity/exercises[]` items.
- Renamed `activity/exercises[]/name` to `activity/exercises[]/name`.
- Activity can newly have more than one gear.
- Activity newly has 0 or more laps.

### Removed
- Route data model entity, forms and HTML pages.

### Infrastructure
- Version management with the single source of truth (SSOT) approach.

### Documentation
- Scripts for building of the HTML documentation.
- Initial drafts of digitization, terminology and normalization documentation.



## 1.0.0

This MyTraL **major** release brings:

### Added
- Initial release of MyTraL training log application.
- User authentication and session management.
- Training log entry creation and management.
- Activity tracking (running, cycling, swimming, strength training).
- Interactive Bokeh charts for training data visualization.
- Weekly and monthly training statistics.
- JSON-based data persistence.
- Responsive web interface using Tabler framework.
- WTForms-based form validation.
- Export training data to CSV format.
- Training calendar view.
- Activity filtering and search functionality.

### Security
- Secure password hashing for user accounts.
- Session management with Flask-Login.
- CSRF protection on all forms.

### Performance
- Optimized JSON file operations for faster data loading.
- Lazy loading of chart data for improved page load times.

### Documentation
- Complete README with installation and setup instructions.
- API documentation for backend modules.
- User guide for training log features.
- Development setup guide.

### Infrastructure
- Flask-based web server configuration.
- Deployment configuration for PythonAnywhere.
- Automated testing with pytest.
- Code quality tools (black, flake8, isort).
- Makefile for common development tasks.
- UV-based dependency management.



## 0.0.1

This MyTraL **patch** release brings:

### Added
- Initial YAML data format with applications.
- Manually written pure HTML pages no-JavaScript/no-CSS (bar) charts.



## 0.0.0 - 2014-09-12

The first MyTraL commit - YAML based datasets with Python based scripts.



## Changelog Conventions

All notable changes to MyTraL (My Training Log) are documented by this file
whose format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Find conventions details and template at the bottom of this document.

Version Numbering (Semantic Versioning)

- **MAJOR** (X.0.0): Incompatible API changes, breaking changes, or major functionality overhauls.
- **MINOR** (x.Y.0): New features added in a backward-compatible manner.
- **PATCH** (x.y.Z): Backward-compatible bug fixes, security patches, and **minor** improvements.

Changes are organized into the following categories:

- **Added**: New features, functionality, or capabilities.
- **Changed**: Changes in existing functionality or behavior.
- **Deprecated**: Features that will be removed in upcoming releases.
- **Removed**: Features or functionality that have been removed.
- **Fixed**: Bug fixes and error corrections.
- **Security**: Security vulnerability fixes and improvements.
- **Performance**: Performance improvements and optimizations.
- **Documentation**: Documentation updates and improvements.
- **Dependencies**: Dependency updates and changes.
- **Infrastructure**: Build, deployment, and infrastructure changes.

Entry Format

- Use present tense ("Add feature" not "Added feature").
- Start with a verb when possible.
- Be concise but descriptive.
- Reference issue/PR numbers when applicable: `[#123]`.
- Group related changes together.
- Most important changes first within each category.

Release Date Format

- Use ISO 8601 date format: `YYYY-MM-DD`.

Version History Links

- Unreleased: https://github.com/dvorka-oss/mytral/compare/v1.0.0...HEAD
- 1.0.0: https://github.com/dvorka-oss/mytral/releases/tag/v0.9.0...v1.0.0
