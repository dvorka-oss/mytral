# Feature: 3D GPX Terrain Visualization

 Status | Reviewers | Last updated | Comment
 --- |  --- |  --- | ---
 DONE | @dvorka | 2026-06-30 | Gated behind `MYTRAL_FF_GPX_3D_MAP`.

**Table of contents**

* [Analysis](#analysis)
    * [Why](#why)
    * [Functional Requirements](#functional-requirements)
    * [Functional Non-requirements](#functional-non-requirements)
    * [Technical Requirements](#technical-requirements)
    * [Technical Non-requirements](#technical-non-requirements)
* [Design](#design)
    * [Implementation](#implementation)
    * [Tests](#tests)
    * [Benchmarks](#benchmarks)
* [References](#references)
* [Appendices](#appendices)


# Analysis

The 3D GPX terrain viewer renders an activity's GPS track draped over real-world
elevation terrain, textured with map tiles, in an interactive WebGL scene in the
browser. It turns a flat 2D route map into a spatial, explorable model: the athlete sees
the actual mountains they climbed, the valleys they ran through, where the climbs were,
and how the route sits in the landscape. The feature is inspired by
[CubeTrek](https://cubetrek.com/) and the broad genre of "tour 3D" visualizations
(FATMAP, Relive, Strava 3D), re-implemented natively inside MyTraL with an
all-open-data, no-mandatory-API-key pipeline.

The server parses the GPX/FIT recording, fetches SRTM elevation data, builds a textured
3D terrain mesh as a glTF 2.0 document, and ships it plus a GeoJSON track to the browser,
where Babylon.js renders it. All heavy assets (the 3D engine, elevation, tiles) are
cached so the feature is fast on repeat views and works offline after a first load.

## Why

MyTraL already shows each activity's route on a 2D Leaflet map with an elevation profile.
That conveys *where* and *how high*, but not the *shape of the land*. For mountain
sports — hiking, trail running, ski touring, cycling cols — the terrain **is** the story:
a 600 m profile gain reads very differently as a number than as a wall you can see.

Value proposition:

* **Emotional re-living** — the single most requested quality of tour visualizations;
  athletes want to *see* their adventure, not read a chart.
* **Analytical context** — gradient-coloured route + synced elevation profile make it
  obvious where the steep sections, the summit, and the descents are.
* **Differentiation** — a self-hosted training log with native, key-free 3D terrain is
  rare; it is a flagship visual feature.
* **Reuse of existing data** — the GPX/FIT recordings are already stored; this extracts
  far more value from them at no extra data-entry cost.

## Functional Requirements

**As** an athlete with a GPS-recorded activity, **I want to** view my route in 3D on
real terrain **so that** I can re-live and understand the landscape I moved through.

* Acceptance criteria:
    * A "View 3D terrain" button appears on the activity's GPS-track map card when the
      activity has a GPX/FIT recording and the feature flag is on.
    * The 3D page shows the terrain mesh textured with a map, the route draped on the
      surface, and start/finish/peak markers.

**As** an athlete, **I want to** see where the climbs and descents are **so that** I can
analyse the effort distribution.

* Acceptance criteria:
    * The route is coloured by gradient (slope) using the same ramp as the 2D elevation
      profile.
    * An elevation/gradient chart sits beneath the 3D view and is cross-linked: hovering
      either the chart or the terrain highlights the corresponding point on the other.

**As** an athlete, **I want to** explore the model freely **so that** I can find the best
viewpoint.

* Acceptance criteria:
    * Orbit / zoom / pan controls, preset camera angles (Fit, Top, N/S/E/W), and a
      "Fly" fly-through that follows the track.
    * A choice of map styles (OSM always; MapTiler standard/satellite when a key is set).

## Functional Non-requirements

* No editing of the route or terrain in 3D (read-only visualization).
* No client-side GPX upload/processing in the 3D view — it consumes already-stored
  recordings only.
* No multi-activity overlay / comparison in one 3D scene (single activity per view).
* No 3D measurement tools (distance picking, cross-sections), no annotations.
* No mobile-native app; this is a browser WebGL feature.
* No global, pre-baked terrain — meshes are generated per activity on demand.

## Technical Requirements

**As** an operator, **I want** the feature to work without a paid map API key **so that**
self-hosters can run it out of the box.

* OSM raster tiles are the default and require no key; MapTiler is optional.

**As** an operator on modest hosting (pythonanywhere), **I want** the feature to be cheap
on repeat views **so that** it does not hammer upstreams or burn CPU.

* SRTM elevation tiles are cached on disk; map tiles are cached on disk; generated glTF
  is cached in memory (bounded). The GPX is parsed at most once per output per view.

**As** a user, **I want** MyTraL to keep working offline **so that** the desktop app is
usable without connectivity.

* The 3D engine (Babylon.js) is **vendored locally**, not loaded from a CDN. SRTM and
  map tiles are served through MyTraL and cached on disk, so a previously-viewed area
  renders offline; a tile that cannot be fetched degrades to a placeholder rather than
  failing the whole scene.

**As** a developer, **I want** the visual layer to be verifiable and robust **so that**
regressions are catchable.

* Pure-unit-testable backend (no network in tests); the trail/markers must render under
  the headless software GL used for verification.

## Technical Non-requirements

* No GPU compute / WebGPU; classic WebGL2 via Babylon.js is sufficient.
* No streaming/LOD terrain or tiled mesh paging — one activity's extent is small (capped
  at 48 map tiles), so the whole mesh is sent at once.
* No server-side rendering / headless screenshot generation in production.
* No custom shaders shipped by MyTraL (uses Babylon's standard materials).
* No imperial-unit handling (MyTraL is metric-only).

# Design

The feature is a classic **server-generates-assets / client-renders** split:

```
GPX/FIT  ─┐
          │  TerrainService (backend)
SRTM HGT ─┼─►  parse → simplify → bbox → tiles → DEM grid → mesh → glTF ──► browser
          │                                   └────────► GeoJSON track ──► browser
map tiles ┘                                                                  │
                                                              Babylon.js + terrain3d.js
                                                              gpx-profile-chart.js
```

The backend produces two artifacts per activity:

1. **glTF 2.0** — the textured terrain mesh (one node per map tile + optional enclosure
   walls), with map-tile images referenced by URL through a same-origin proxy.
2. **GeoJSON** — the track as `[lon, lat, ele, time, dist, hr]` per point, plus a
   `scene` block of coordinate parameters and `labels` for start/finish/peak.

The browser loads the glTF into Babylon.js, then uses the GeoJSON `scene` parameters to
place the gradient-coloured route, markers, and hover dot in the same coordinate space,
and renders an SVG elevation/gradient chart cross-linked to the 3D scene.

## Implementation

### Module map

```
mytral/gpx_terrain/                      # backend pipeline (pure, unit-tested)
├── coordinates.py      # bbox, haversine, metres-per-degree, slippy-tile math
├── gpx_worker.py       # GPX (gpxpy) + FIT (fitdecode) parse, RDP simplify,
│                       #   stats, mean-bias elevation normalization, GeoJSON
├── hgt_loader.py       # SRTM HGT loading via srtm.py, multi-tile grid stitch,
│                       #   on-disk cache, void filling
├── map_tile.py         # slippy map tile model, auto-zoom to a tile budget
├── mesh_builder.py     # DEM grid → vertices/indices/normals/UVs; enclosure walls
├── gltf_writer.py      # MeshBuffers → glTF 2.0 JSON (base64 buffers, materials)
├── tile_cache.py       # on-disk raster tile cache (mirrors HgtCache)
└── terrain_service.py  # orchestrator: build_geojson() / build_gltf()

mytral/blueprints/gpx_terrain_views.py   # Flask routes + tile proxy (+ singletons)
mytral/templates/activity-view3d.html    # the 3D page (controls, chart slot, scripts)
mytral/static/js/terrain3d.js            # Babylon scene: terrain, trail, markers,
│                                        #   hover, camera presets, fly-through
mytral/static/js/gpx-profile-chart.js    # standalone slope-coloured SVG profile
mytral/static/babylon/                    # vendored Babylon.js 9.14.0 (offline)
```

### Backend pipeline (`TerrainService`)

Parameters (CubeTrek-derived defaults, `terrain_service.py`): `scale_factor = 0.0001`
(metres → scene units), `z_exaggeration = 1.5`, `height_offset = 500 m`, bbox
`padding = 500 m`, `max_tiles = 48`, `grid_cells_per_tile = 40`.

1. **Parse** the GPX (`gpxpy`) or FIT (`fitdecode`, semicircles → degrees) into
   `TrackPoint[]` (lat, lon, elevation, timestamp, heart_rate).
2. **Simplify** with **Ramer–Douglas–Peucker** (`epsilon = 2 m`, planar metric using
   metres-per-degree) — removes redundant points while preserving shape, cutting mesh/
   draw work for dense recordings.
3. **Bounding box** from the track + 500 m padding so the terrain extends beyond the
   route.
4. **Elevation normalization (optional)** — GPS barometric elevation is biased; a
   **mean-bias correction** shifts all GPS elevations by a constant so their mean matches
   the SRTM reference mean, preserving the profile *shape* while aligning it to the same
   datum the terrain mesh uses.
5. **Tile selection** — `auto_zoom` picks the highest slippy-map zoom whose tile count
   over the bbox is ≤ 48, giving the sharpest map texture within a fixed budget.
6. **DEM grid (seam-safe)** — instead of sampling each tile independently (which causes
   vertical seam "walls" where neighbouring tiles disagree on a shared edge), one
   **master elevation grid** is loaded over the whole tile lattice from SRTM-3 (~90 m)
   via `srtm.py`, then **sliced** per tile so adjacent tiles share identical border
   samples by construction. A single global elevation minimum is subtracted (minus the
   height offset) so all tiles share one Y origin.
7. **Mesh build** (`mesh_builder.py`) — per tile, a regular grid mesh:
   vertices in a Y-up `[lat, height, lon]` layout; **smooth per-vertex normals** from the
   height field via central finite differences (`np.gradient`) for proper lighting; UVs
   with V=0 at the north edge (matching north-up map tiles). Optional **enclosure walls**
   give the model a solid "cake slice" base.
8. **glTF assembly** (`gltf_writer.py`) — emits a self-contained glTF 2.0 JSON: one mesh
   node per tile, binary buffers embedded as base64 data URIs, and a PBR material per
   tile whose `baseColorTexture` is the map tile. The material is deliberately
   **mostly-emissive** (`emissiveFactor ≈ 0.85`, low `baseColorFactor`) so the map reads
   at near-true brightness regardless of slope, with a small lit term for relief.
9. **GeoJSON** (`gpx_worker.points_to_geojson`) — track coordinates plus a `scene` block
   (`center_lat/lon`, metres-per-degree, scale_factor, z_exaggeration, height_offset,
   terrain min/max elevation) that lets the client map lat/lon/ele → the exact scene
   XYZ the mesh uses, and `labels` for start/finish/highest.

### Serving & caching (`gpx_terrain_views.py`)

Four routes (feature-flag gated, login required):

* `GET /app/activities/<key>/view3d` — the page.
* `GET /api/terrain/<key>.geojson` — the track.
* `GET /api/terrain/<key>.gltf?maptype=…` — the mesh (in-memory LRU-bounded cache, 16
  entries, keyed by activity+maptype+proxy).
* `GET /api/terrain/tiles/<maptype>/<z>/<x>/<y>.png` — **same-origin tile proxy**.

The tile proxy exists to avoid browser CORS issues when Babylon loads tile textures, and
to enable caching/offline: it checks an **on-disk tile cache** (`tile_cache.py`, under the
purgeable `~/.cache/mytral/map_tiles`), fetches upstream (with a proper User-Agent) only
on a miss, and writes through. On an upstream failure it returns a muted **placeholder
PNG (HTTP 200)** so one bad tile never aborts the whole glTF texture load.

### Frontend (`terrain3d.js`)

All visual constants live in a single `CONFIG` block at the top of the file for one-place
tuning (lighting, trail/marker sizes, zoom, fly-through).

* **Scene & lighting** — daylight slate sky, a fixed NW sun (`intensity 0.9`) plus low
  hemispheric + ambient fill, ACES tone-mapping with raised contrast (`1.4`). The map
  material's emissive/albedo balance is applied from `CONFIG` on load. Net effect: a
  readable, contrasty map (forest/meadow/rock distinguishable) with hill-shade relief —
  not the washed-out or "dark cave" extremes.
* **Coordinate transform** — Babylon's glTF loader wraps the import in a `__root__` node
  that **negates world X** (scaling.z = −1 + 180° Y rotation, right-handed → left-handed).
  The client `sceneXZ(lat, lon)` therefore **negates X** so the trail/markers align with
  the terrain map.
* **Trail draping** — the track is downsampled (≤ 2000 points), each point projected to
  scene XZ and given a surface Y by a **downward ray-cast** onto the terrain mesh (so it
  hugs the actual rendered surface), lifted a few metres. It is rendered as **emissive
  tubes, one merged mesh per slope-colour run** (gradient ramp shared with the chart),
  **depth-tested** in the default rendering group so ridges naturally occlude the route
  where it runs behind them. A tight camera near/far ratio (~3000:1) plus a small lift and
  `zOffset` prevent z-fighting with the ground.
* **Markers** — start (green **S**), finish (red **F**), peak (amber **▲** + elevation),
  drawn as clean billboarded coin badges (DynamicTexture: filled circle + white ring +
  glyph) on thin pin stems; kept always-on-top (`depthFunction = ALWAYS`) as findable
  waypoints.
* **Hover dot** — an orange core sphere + a pulsing radial-gradient glow halo, **depth-
  tested** so it is occluded when the hovered point is behind a mountain. Driven by a
  linear nearest-point scan over the draped points (no KD-tree).
* **Chart cross-link** — `gpx-profile-chart.js` renders a standalone SVG elevation
  profile coloured by per-segment slope; hovering the chart calls back into the scene to
  move the dot, and terrain hover highlights the chart, sharing one point index space.
* **Camera** — `ArcRotateCamera` with distance-proportional zoom (`wheelDeltaPercentage`,
  1..20 slider), preset views via a self-removing eased tween, and a track-following
  fly-through. (The tween is hand-rolled because the vendored UMD build does not expose
  the `ANIMATION­LOOP_CONSTANT` constant, which made `CreateAndStartAnimation` loop.)

### Key technology decisions & justifications

* **glTF 2.0 as the transport** — an open, compact, widely-supported 3D format; lets the
  server own all geometry/elevation/texturing logic in Python and the client stay a thin
  renderer. Buffers embedded as base64 keep it a single self-contained response.
* **Babylon.js, vendored, not CDN** — a capable, well-documented WebGL engine with a
  first-class glTF loader, billboards, ray-casting and animation. Vendored locally
  (8.6 MB core + loaders) to satisfy the **offline** requirement of the desktop app.
* **Tubes for the trail (not GreasedLine)** — a screen-space line (`CreateGreasedLine`,
  constant pixel width) is the "ideal" SOTA choice, but it **cannot be rendered by the
  headless software GL (swiftshader)** used for automated visual verification, so it could
  not be confirmed. Depth-tested emissive **tubes** render everywhere (including
  swiftshader), give proper terrain occlusion, and per-run colour gives the gradient.
  Trade-off: world-unit tubes scale slightly with zoom; a small radius keeps them elegant.
* **Mostly-emissive map material** — re-lighting a flat raster map as a normal PBR
  surface darkens slopes facing away from the sun ("dark cave"); making it largely
  emissive shows the map at true brightness with only gentle added relief, the CubeTrek
  look.
* **SRTM-3 (~90 m) over SRTM-1 (~30 m)** — far smaller downloads/cache for terrain that
  is viewed at activity scale; the difference is visually negligible here.
* **Master-grid DEM stitching** — guarantees C0-continuous tile borders (no seam walls)
  without post-processing, by construction.
* **Same-origin tile proxy + disk cache + placeholder** — solves CORS, enables offline,
  respects upstream usage policy (cache, real User-Agent), and degrades gracefully.
* **Feature flag `MYTRAL_FF_GPX_3D_MAP`** — lets the feature ship dark and be enabled per
  deployment.

## Tests

* **Unit** — `tests/test_gpx_terrain.py` (**33 tests**, all `@pytest.mark.mytral`, no
  network/disk-dependent on real downloads). Coverage by module: coordinates (haversine,
  bbox, metres-per-degree), gpx_worker (parse, RDP reduces/preserves, stats, elevation
  normalization, GeoJSON coordinate layout), map_tile (zoom/bbox/auto-zoom budget, URL
  templating), hgt_loader (void filling, multi-tile grid via a stub cache), mesh_builder
  (index/vertex counts, UV presence, height scaling, enclosure walls), gltf_writer (valid
  JSON, required sections, texture-URL injection, mostly-unlit material, wall nodes),
  terrain_service (Tatra GPX → glTF **tile-seam continuity**, asserting a single DEM load
  and shared edges), tile_cache (miss→put→hit round-trip, maptype path-traversal guard).
* **Manual / visual** — during development the rendered scene was verified end-to-end by
  loading the real JS in **headless Chrome** against exported demo assets with real OSM
  tiles (scene introspection + screenshots), used to diagnose and confirm the coordinate,
  occlusion, lighting and trail-visibility fixes (see Appendix).
* **Lint** — `uv run make py-lint` (ruff + isort) clean; JS validated with `node --check`.

## Benchmarks

Indicative, for a ~16 km Tatra hike (≈ 800 track points, 16 map tiles at the chosen zoom):

* glTF size ≈ 1.9 MB (geometry base64; tile images fetched separately via the proxy).
* GeoJSON ≈ 28 KB.
* First view does N tile fetches (≤ 48) + SRTM download for the area; **repeat views are
  served from the in-memory glTF cache and on-disk tile/SRTM caches** (no upstream).
* Client downsamples the track to ≤ 2000 points; surface ray-casts and the per-mousemove
  nearest-point scan are linear over that bounded set (interactive).

(No formal load/longevity benchmark; the in-memory glTF cache is bounded to 16 entries to
cap memory on a long-lived process.)

# References

* [CubeTrek](https://cubetrek.com/) — inspiration and algorithmic reference (TopoLibrary
  `TrackViewerService`, `GPXWorker`, `HGTWorker`, `GLTFDatafile`).
* [Babylon.js](https://www.babylonjs.com/) — WebGL engine (vendored 9.14.0).
* [glTF 2.0 specification](https://www.khronos.org/gltf/) — asset format.
* [SRTM / srtm.py](https://github.com/tkrajina/srtm.py) — elevation data + loader.
* [OpenStreetMap](https://www.openstreetmap.org/copyright) / [MapTiler](https://www.maptiler.com/)
  — map tiles.
* [Ramer–Douglas–Peucker algorithm](https://en.wikipedia.org/wiki/Ramer–Douglas–Peucker_algorithm)
  — track simplification.
* Sibling design docs: `BHR_3D_GPX.md` (review), `GPX_3D_OPUS_NG.md` (fix log).

# Appendices

## Appendix A — Coordinate spaces

| Space | Definition |
| --- | --- |
| Geographic | `(lat, lon, ele)` degrees / metres |
| Mesh (raw glTF) | `vx = (lat−c_lat)·mpd_lat·sf`, `vy = (ele−shift)·sf·zexag`, `vz = (lon−c_lon)·mpd_lon·sf` |
| World (rendered) | mesh with `__root__` applied → **X negated**: `worldX = −vx`, `worldZ = vz` |
| Client placement | `sceneXZ` negates X to match world; Y from a downward ray-cast onto the mesh |

## Appendix B — Notable defects found & fixed during development

| Symptom | Root cause | Fix |
| --- | --- | --- |
| Trail invisible | `scene.createOrUpdateSelectionOctree()` made Babylon select active meshes from the octree, excluding everything created after it (trail, markers, dot) | Removed the octree calls |
| Start/finish on opposite sides; trail mirrored | client `sceneXZ` ignored the glTF `__root__` X-negation | Negate X in `sceneXZ` |
| Map too dark, then too washed-out | re-lighting a flat map; then over-correcting | Mostly-emissive material + balanced fixed-sun lighting + raised tone-map contrast |
| Trail drew through mountains | trail material forced `depthFunction = ALWAYS` | Removed it; tightened camera near/far for crisp depth occlusion |
| Trail rendered solid black | a wider concentric "casing" tube enclosed the colour core once not always-on-top | Dropped the casing; colour-core only |
| Camera presets looped forever | vendored UMD lacks `ANIMATIONLOOP_CONSTANT` → `CreateAndStartAnimation` defaulted to looping | Hand-rolled self-removing eased tween |
| One bad tile blanked the scene | `ImportMeshAsync` rejects on any texture 404/502 | Tile proxy returns a placeholder PNG (200) on failure |

## Appendix C — Configuration

| Env var | Effect |
| --- | --- |
| `MYTRAL_FF_GPX_3D_MAP` | Enables the feature (flag). |
| `MYTRAL_MAPTILER_KEY` | Optional; enables MapTiler `standard`/`satellite` styles (OSM otherwise). |

Client look/feel is tuned via the `CONFIG` block in `terrain3d.js`
(`trailRadiusFactor`, `ribbonLiftM`, `trailZOffset`, `markerBadge`, `markerStem`,
`dotCore`, `dotHalo`, lighting, zoom, `flySeconds`).
