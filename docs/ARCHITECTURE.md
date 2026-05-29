# MyTraL Architecture

This page describes the actual runtime architecture of MyTraL based on the current Python modules and wiring.

## UML Component Diagram (Nested ASCII)

```text
+-------------------+                     +----------------------------------------+
|       User        |                     |                Browser                 |
| <<actor>> Athlete |-------------------->| <<component>> Tabler UI + JS + Bokeh   |
+-------------------+                     | + Leaflet + forms in HTML templates    |
                                          +-------------------+--------------------+
                                                              |
                                                              | HTTP request/response
                                                              v
  +-------------------------------------------------------------------------------------+
  |                           MyTraL Server (Python process)                            |
  |                                <<component>>                                        |
  |                                                                                     |
  |   +-------------------------------------------------------------------------+       |
  |   | Flask Web Layer                                                         |       |
  |   | <<component>> routes.py + blueprints/* + middleware/sync_guard.py       |       |
  |   +-----------------------------+---------------------------+---------------+       |
  |                                 |                           |                       |
  |                    +------------v-----------+     +---------v----------------+      |
  |                    | Jinja Template Layer   |     | Async Task Subsystem     |      |
  |                    | <<component>>          |     | <<component>>            |      |
  |                    | templates/*.html       |     | TaskManager              |      |
  |                    +------------------------+     | ThreadTaskExecutor       |      |
  |                                                   | TaskStorage + tasks/do/* |      |
  |                                                   +---------------+----------+      |
  |                                                                   |                 |
  |   +-------------------------------+                               |                 |
  |   | Domain & Analytics Layer      |                               |                 |
  |   | <<component>>                 |                               |                 |
  |   | stats.py athlete_metrics.py   |                               |                 |
  |   | charts.py insights.py plugins |                               |                 |
  |   +---------------+---------------+                               |                 |
  |                   |                                               |                 |
  |   +---------------v-----------------------------------------------v--------------+  |
  |   | Dataset Facade: MyTraLDataset / UserDataset interface                        |  |
  |   | <<component>> backends/dataset.py                                            |  |
  |   +--------------------------+------------------------------+--------------------+  |
  |                              |                              |                       |
  |      +-----------------------v----------------+   +---------v------------------+    |
  |      | JSON Persistence + Cache               |   | Blob Service Layer         |    |
  |      | <<component>>                          |   | <<component>>              |    |
  |      | JsonUsersDataset + JSONUserActivities  |   | Activity/Avatar/Entity svc |    |
  |      | InMemory/Passthrough cache             |   | validation + image process |    |
  |      +-----------------------+----------------+   +-------------+--------------+    |
  +------------------------------|----------------------------------|-------------------+
                                 |                                  |
                                 v                                  v
              +------------------+-------------------+   +----------+-------------------+
              | Filesystem Structured Store          |   | Blob Store Backend           |
              | <<component>> data/<user>/           |   | <<component>> filesystem     |
              | activities-*.json, user-*.json,      |   | (default), optional MinIO/S3 |
              | tasks/task-*.json + task-*.log       |   +------------------------------+
              +------------------+-------------------+
                                 |
                                 v
              +------------------+--------------------+
              | External Integrations                 |
              | <<component>> Strava / Google / Polar |
              | via plugins and integrations modules  |
              +---------------------------------------+
```

## User

The user is the primary actor who drives all use cases: training logging, profile maintenance, synchronization, and analytics consumption. In architecture terms, the user is external to the software system but initiates every flow by interacting with the browser client.

## Browser

The browser renders server-generated HTML from Jinja templates, loads static assets (Tabler CSS/JS, Bokeh JavaScript bundles, Leaflet), executes UI behavior, and sends authenticated HTTP requests back to the Flask server. It also hosts runtime UX elements like task status polling and chart interactivity.

## Server

The server is a single Python runtime where application singletons are created (`app_config`, dataset facade, blob store, task manager) and then shared across route handlers and services. It is the orchestration boundary that composes web handling, domain logic, storage, and asynchronous processing into one coherent request lifecycle.

## Flask Web Layer

Flask provides the request router and HTTP execution model through `routes.py` plus URI-space modules in `mytral/blueprints/`, with middleware hooks such as the sync guard that enforces read-only mode during running tasks. This layer binds sessions, forms, task APIs, and template rendering to specific endpoints.

## Jinja Template Layer

Jinja templates in `mytral/templates/` define the web UI structure and receive route-prepared view models, form instances, and chart embeds. It is responsible for consistent page composition (layout, navigation, flash messaging, task indicators) while keeping route modules focused on orchestration and data preparation.

## Domain & Analytics Layer

The domain layer is implemented by modules such as `stats.py`, `athlete_metrics.py`, `insights.py`, and `charts.py`, and turns raw persisted activity/profile data into derived metrics, health/training summaries, and Bokeh visualizations. It is consumed by both synchronous web requests and background task flows.

## Async Task Subsystem

The task subsystem consists of `TaskManager`, `ThreadTaskExecutor`, `TaskStorage`, per-user locking, and concrete task implementations in `tasks/do/*`. It executes long-running operations (imports, sync, conversion) in worker threads, persists task state/logs, supports cancellation and watchdog timeout handling, and integrates with UI status endpoints.

## Dataset Facade

`MyTraLDataset` in `backends/dataset.py` is the persistence-agnostic application facade that exposes user-centric operations while selecting the configured implementation. It decouples web/domain code from concrete storage details and provides a stable API for activities, profile entities, stats, and task-file persistence methods.

## JSON Persistence + Cache

`JsonUsersDataset` and `JSONUserActivitiesDataset` implement the default filesystem persistence model where structured data is stored as JSON files under per-user directories. This layer owns cache strategy (in-memory or passthrough), on-demand loading, serialization, dataset sharding by activity-year files, and user/task file path management.

## Blob Service Layer

The blob service layer (`activity_service.py`, `avatar_service.py`, `entity_photo_service.py`) contains business rules for binary attachments: validation, metadata handling, GPX/parquet linkage, photo normalization, and thumbnail generation. It bridges domain entities and the lower-level blob backend interface.

## Blob Store Backend

The blob backend is selected by configuration via `create_blobstore()` and uses a `BlobStoreAbc` contract with implementations for filesystem and optional object storage providers (MinIO/S3). This component persists binary payloads and metadata records independently of JSON entity storage.

## Filesystem Structured Store

The filesystem store is the durable substrate for the JSON persistence implementation and task metadata/log files, typically under `data/<user_id>/`. It holds structured files like `activities-*.json`, `user-*.json`, and `tasks/task-*.{json,log}` that are treated as the source of truth for non-blob entities.

## External Integrations & Plugins

MyTraL integrates with external ecosystems through `integrations/*` and `plugins.py`, including Strava and other import/sync sources used by both direct import routes and background tasks. This component adapts third-party payloads to internal entities so downstream analytics and UI features remain consistent.
