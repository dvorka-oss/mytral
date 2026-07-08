# Polar Flow integration

MyTraL imports the athlete's own training data from Polar Flow
(https://flow.polar.com) through two independent paths:

1. **Polar AccessLink API** - incremental sync of new training via the official
   API (https://www.polar.com/accesslink-api/), using the exercise transaction
   model so activities are never delivered twice.
2. **Polar "Download your data" (GDPR) export ZIP** - one-shot backfill of the
   full history, which the API cannot provide (the API only serves training
   recorded *after* the client was authorized).

Both paths normalize their payloads to the same internal shape (entity source
`polar-flow`), so downstream analytics and UI treat them identically. This is
separate from the legacy Polar Precision Performance (`.hrm` / `.pdd`) file
import.

The whole feature is gated behind the `MYTRAL_FF_POLAR_FLOW_IMPORT` feature flag
(`ff.can("POLAR_FLOW_IMPORT")`, default off).

## Why the design differs from Strava

Polar AccessLink access tokens **do not expire** unless the user revokes them,
and there is **no refresh token**. Credential handling is therefore simpler than
Strava's: once authorized, MyTraL stores a single long-lived access token plus
the numeric Polar user id and never has to refresh. The flip side is that the
access token is a high-value, long-lived secret, so it is encrypted at rest (see
below).

## Authentication (OAuth2 authorization-code grant)

Per-user credentials, all persisted on the user profile:

| Field                     | Meaning                                                       |
|---------------------------|---------------------------------------------------------------|
| `polar_flow_client_id`    | AccessLink client id (from admin.polaraccesslink.com).        |
| `polar_flow_client_secret`| AccessLink client secret.                                     |
| `polar_flow_access_token` | Long-lived AccessLink access token (no expiry, no refresh).   |
| `polar_flow_user_id`      | Numeric Polar user id, used to build transaction URLs.        |
| `polar_flow_member_id`    | MyTraL-generated member id used when linking the user.        |

The controller in `blueprints/polar_flow_uri_space.py` drives the flow, and
`polar_flow.ask_mentor()` decides the next step from whatever credentials are
present (`AuthMentorAdvice`): CONFIGURE -> AUTHENTICATE -> REGISTER_USER ->
AUTHENTICATED.

1. **Configure** - the user pastes client id / secret (`/polar/api-secrets`).
2. **Authenticate** - `/polar/auth-start` redirects to Polar's OAuth2 authorize
   URL; Polar redirects back to `/polar/auth-callback` with a `code`.
3. **Exchange** - `auth_exchange_code_for_token()` POSTs the code (HTTP Basic
   auth with client id / secret) to the token endpoint and stores the returned
   access token and `x_user_id`.
4. **Register** - `register_user()` links the Polar user to the client
   (idempotent: HTTP 409 "already registered" is treated as success) and stores
   the `polar-user-id`.

## Incremental sync (transaction model)

`create -> list -> fetch -> commit` guarantees each exercise is delivered once:

1. `create_transaction()` - opens a transaction; HTTP 204 means "no new data".
2. `list_transaction_exercises()` - lists the exercise resource URLs.
3. `fetch_exercise_summary()` / `fetch_exercise_gpx()` / `fetch_exercise_tcx()` -
   pulls each exercise's JSON summary and optional recording.
4. `commit_transaction()` - commits, so the same exercises are not returned by
   the next transaction.

AccessLink rate limiting (HTTP 429) is handled in `_request()` with a bounded
`Retry-After` backoff.

## Historical backfill (GDPR export ZIP)

`integrations/polar_flow_export.py` parses the "Download your data" ZIP and
normalizes each training session into the same summary shape the AccessLink path
produces (`parse_export()`), so the import pipeline is shared. This is the only
way to import training recorded before the AccessLink client was authorized.

## Secret storage at rest

Client id, client secret, and the access token are **encrypted on disk** with
Fernet (`MYTRAL_ENCRYPTION_KEY`). Encryption is transparent to the rest of the
code: `JsonUsersDataset` encrypts on write and decrypts on read via
`security.encrypt_profile_secrets()` / `security.decrypt_profile_secrets()`, so
in-memory `UserProfile` objects always hold plain text. The set of encrypted
fields per provider is declared once in `security._PROFILE_SECRET_GROUPS` -
adding a provider or field is a single edit there. Values with a missing `*_enc`
key fall back to any plain-text value, giving a transparent migration path for
profiles written before encryption existed.

## Setup steps

1. Sign in at https://admin.polaraccesslink.com/ with your Polar Flow account.
2. **Create client**, accept the AccessLink Limited License Agreement, and fill
   in the application information.
3. Set the **OAuth2 authorization callback URL** to your MyTraL host, e.g.
   `http://127.0.0.1:5000/polar/auth-callback` for local use.
4. Copy the **Client ID** and **Client Secret** into MyTraL at
   `/polar/api-secrets`.
5. Start authentication from the Polar Flow developer page
   (`/polar/api-developer`) and approve access at Polar.
6. Sync new training from that page, and/or import a GDPR export ZIP to backfill
   history.

## Code map

| File                                          | Responsibility                                  |
|-----------------------------------------------|-------------------------------------------------|
| `integrations/polar_flow.py`                  | AccessLink client, OAuth, transaction model.    |
| `integrations/polar_flow_export.py`           | GDPR export ZIP parser.                          |
| `blueprints/polar_flow_uri_space.py`          | Routes: configure, auth, sync, import.          |
| `tasks/do/polar_flow_sync.py`                 | Incremental sync task.                           |
| `tasks/do/polar_flow_resync_all.py`           | Purge + full re-pull task.                       |
| `tasks/do/polar_flow_export_import.py`        | GDPR export import task.                          |
| `tasks/do/polar_flow_commons.py`              | Shared task helpers.                             |
