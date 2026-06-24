# Configuration

## Environment Variables

All runtime behaviour is controlled by `MYTRAL_*` environment variables.
Boolean variables accept the string values `"true"` or `"false"`.

### Server

| Variable | Default | Description |
|---|---|---|
| `MYTRAL_HOST` | `127.0.0.1` | Bind address for the Flask server. Set to `0.0.0.0` to expose externally — only do this behind a reverse proxy. |
| `MYTRAL_PORT` | `5000` | Bind port for the application server. |
| `MYTRAL_CORS_ORIGINS` | `http://localhost:5000` | Comma-separated list of allowed CORS origins, e.g. `https://mytral.fitness,https://www.mytral.fitness`. |
| `MYTRAL_DEBUG` | `false` | Enable Flask debug mode (development only). Enables verbose error pages and relaxes some security checks. Never set in production. |
| `MYTRAL_INCARNATION` | `WEBAPP` | Deployment type. Set to `DESKTOP` for single-user local installs; `WEBAPP` for hosted/multi-user deployments. |
| `MYTRAL_TASK_TIMEOUT` | `3600` | Maximum time in seconds an async task (import, Strava sync, …) may run before it is killed. |

### Data & Persistence

| Variable | Default | Description |
|---|---|---|
| `MYTRAL_DATA_DIR` | `~/.local/share/mytral` (Linux XDG) | Path to the persistence directory. MyTraL stores user data under `<MYTRAL_DATA_DIR>/data/`. |
| `MYTRAL_PERSISTENCE_CACHE` | `true` | Enable in-memory caching of user data. Set to `false` in autoscaling environments where multiple server instances share the same filesystem. |
| `MYTRAL_USER_REGISTRATION` | `false` | Allow new athlete accounts to be created via the registration form. Set to `true` for fresh installs that need onboarding. |
| `MYTRAL_AUTO_ACCOUNT_CREATE` | `false` | Automatically create an account when an unknown user logs in. Useful for local development; do not enable in production. |

### Security

| Variable | Default | Description |
|---|---|---|
| `MYTRAL_ENCRYPTION_KEY` | — | Fernet key used to encrypt sensitive configuration values (API keys, tokens). **Required** in production `WEBAPP` deployments — MyTraL refuses to start without it. In `DESKTOP` and `DEBUG` modes a built-in development key is used as a fallback (not secure). Generate with: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `MYTRAL_SIGNING_KEY` | random (changes on restart) | Flask session signing key. When not set a new random key is generated on every startup, which invalidates all existing sessions. Set to a stable secret for production or any deployment where persistent login sessions are required. |

### Blob Storage

| Variable | Default | Description |
|---|---|---|
| `MYTRAL_BLOBSTORE_TYPE` | `filesystem` | Storage backend for photos and recordings. One of: `filesystem`, `minio`, `s3`. |

**Filesystem** (default) — blobs stored under `<MYTRAL_DATA_DIR>/blobs/`. No additional variables required.

### AI Providers

| Variable | Default | Description |
|---|---|---|
| `MYTRAL_ANTHROPIC_API_KEY` | — | Anthropic API key for Claude-powered AI coaches. |
| `MYTRAL_OPENAI_API_KEY` | — | OpenAI API key for GPT-powered AI coaches. |
| `MYTRAL_OLLAMA_KEY` | — | Ollama API key for locally hosted model inference. |

### Feature Flags

Feature flags enable optional or work-in-progress functionality.
All flags default to `false` unless noted.

| Variable | Default | Description |
|---|---|---|
| `MYTRAL_FF_TRIMP` | `false` | Enable TRIMP (Training Impulse / Banister model) calculations and chart on the Progress page. |
| `MYTRAL_FF_STRAVA_API_IMPORT` | `true` | Enable Strava API import. Disable to hide Strava import UI for users without a Strava account. |
| `MYTRAL_FF_ACOACHES` | `false` | Enable AI coaches subsystem (requires at least one AI provider key). |
| `MYTRAL_FF_PFN_PREDICTIONS` | `false` | Enable TabPFN ML-powered performance predictions page (experimental). |
| `MYTRAL_FF_TASKS_DEV` | `false` | Enable development task helpers (e.g. Hello World task). Development only. |
| `MYTRAL_FF_GSHEETS_DVORKA_IMPORT` | `false` | Enable Google Sheets import plugin (site-specific, not for general use). |
