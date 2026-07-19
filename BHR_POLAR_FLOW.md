# Brutally Honest Review - Polar "Flow" Integration

Scope reviewed: the Polar import feature, i.e. the Polar Precision Performance
(PPP) `.hrm` + `.pdd` importer.

- `mytral/integrations/polar_hrm.py` (parser + `PolarHrmImportPlugin`)
- `mytral/tasks/do/polar_hrm_import.py` (`PolarHrmImportTask` + Bulldozer blob job)
- `mytral/recordings/parquet_converter.py::hrm_to_parquet`
- `mytral/blueprints/import_uri_space.py::tool_import_polar_hrm`
- `mytral/forms.py::ImportPolarHrmForm`
- `mytral/blobstore/validation.py` (`.hrm` magic check)
- `tests/test_plugin_import_polar_hrm.py`

## Preface: this is not "Polar Flow"

There is no Polar Flow (the modern Polar cloud/web service) integration in this
branch. What exists is a **Polar Precision Performance** desktop-file importer
(S720i, model 12; `.hrm` + `.pdd`). The enum `UserGear.SERVICE_POLAR_FLOW`
(`settings.py:1880`) and its sibling `SERVICE_POLAR_PPP` are both declared and
**never referenced anywhere** - dead constants. Also note: none of this code is
in the `main...HEAD` diff of `dev/1.59.0`; it was merged in earlier commits
(`c986722`, `dbfb033`, `0f7a332`). The branch under review contains zero Polar
changes.

## Findings

| # | Severity | Area | Location | Finding |
|---|----------|------|----------|---------|
| 1 | Critical | Correctness | `polar_hrm_import.py:438-444` | `on_conflict="override"` persists updates then unconditionally `raise NotImplementedError` - the task crashes AFTER writing, leaving a half-applied import marked as failed. The whole override path is broken. |
| 2 | High | Tests | `test_plugin_import_polar_hrm.py:33-40` | All 4 real-data integration tests point at `.../Polar Precision Performance/Marco/`, but the committed data lives under `.../dvorka/`. Every one silently `SKIPPED`. Zero real-data coverage runs in CI. |
| 3 | High | Tests | `test_plugin_import_polar_hrm.py:239,268-273` | Two of those skipped tests are also broken: they call `polar_hrm.build_fit()` (does not exist) and assert `"activity_type_index" in ex` (parser returns `sport_index`). They would FAIL, not pass, if the path in #2 were fixed. Dead tests hiding behind a wrong `skipif`. |
| 4 | High | Performance / DRY | `polar_hrm.py:742` + `polar_hrm_import.py:155` | Every `.hrm` is parsed twice. The plugin parallel-parses all HRM into `_hrm_data_cache` for activity stats, then that cache is discarded (it lives in the parent process). The Bulldozer subprocess re-reads and re-parses each `.hrm` from disk to build Parquet. Up to 3 disk reads / 2 full parses per file. |
| 5 | Medium | Design | `settings.py:1880-1882` | `SERVICE_POLAR_FLOW` and `SERVICE_POLAR_PPP` are unused dead code; and the feature is mislabelled "Flow" throughout the ask. |
| 6 | Medium | Correctness | `polar_hrm.py:54-68` | `_SPORT_MAP` carries a `TODO` admitting it is wrong ("every user has their own sport index mapping"). A known-incorrect, hardcoded sport-index -> activity-type map ships as-is; users with different watch profiles get wrong activity types. |
| 7 | Medium | Performance | `polar_hrm.py:1023` + `polar_hrm_import.py:416` | `evaluate_activity()` runs twice per activity - once in the plugin's `_build_activity`, again in the task's conflict loop. Redundant recompute of every derived metric. |
| 8 | Medium | Clean code | `polar_hrm.py:707,769,898` | Three `app_logger` calls are missing the `f` prefix, so they log the literal string `{self._log_name}` instead of the plugin name. |
| 9 | Medium | DRY | `polar_hrm.py:364-370` and `521-528` | The `[Section]` INI-scanner is copy-pasted verbatim in `parse_hrm` and `parse_pdd`. Extract one helper. |
| 10 | Low | KISS / magic numbers | `polar_hrm.py:952-975` | The cm-inflation heuristic (`150`, `* 50`, `// 100`) and speed-reclassification (`25.0`) are dense, undocumented literals inside `_build_activity`. Project rule is "no magic numbers - use named constants from `commons.py`". |
| 11 | Low | KISS / DRY | `polar_hrm.py:110-115` | `_parse_start_time` is a pure alias of `_parse_duration` ("named separately for clarity") - noise. |
| 12 | Low | Clean code | `polar_hrm.py:159` / tests | `parse_smode` returns `mph` as its 5th value; the tests unpack it as `has_balance` and assert on it. The value is never consumed anywhere in production. Semantic drift + dead output. |
| 13 | Low | Robustness / UX | throughout both files | Pervasive `except Exception: continue`. Bad files are silently dropped with only a log warning; the import result surfaced to the user never reports which/how many files were skipped. Silent data loss. |
| 14 | Low | Robustness | `polar_hrm.py:880` + `polar_hrm_import.py:117-120` | The absolute `KEY_HRM_PATH` is serialized through JSON into the Bulldozer subprocess, which re-reads the original file location. Works only because the feature is desktop/single-machine; brittle coupling. |

## Detail on the load-bearing issues

### 1. `raise NotImplementedError` corrupts the override path (Critical)

```python
if activities_to_update:
    self._dataset.update_activities(..., entity_list=activities_to_update)
    raise NotImplementedError
```

The write happens, then the task throws. Result: with `on_conflict="override"`
and any existing match, the dataset is mutated and the task is reported as
failed. Either implement update support or reject "override" at the form/route
boundary before any writes. Shipping a user-selectable radio option
("Override") whose only outcome is a crash-after-write is the worst of both
worlds.

### 2 + 3. The integration tests do not run and would not pass

```python
_POLAR_DATA_DIR = .../"Polar Precision Performance"/"Marco"   # committed dir is "dvorka"
_POLAR_HAS_DATA = _POLAR_DATA_DIR.is_dir()                    # -> False -> everything skips
```

Observed: `test_parse_hrm_real_file`, `test_parse_pdd_real_file`,
`test_build_fit_produces_valid_bytes`, `test_plugin_import_activities_2003` all
report `SKIPPED`. Point the constant at `dvorka` and two of them break
immediately (`build_fit` removed; `sport_index` renamed). The pure-function
tests (`parse_smode`, `compute_*`) are fine and genuinely pass - but the parser
and the end-to-end import have no executing test. For a binary-format parser
full of index-arithmetic (`rows[8][1]`, `trip_lines[5]`, tab-column offsets)
this is the single biggest risk to correctness.

### 4. The parallel parse is thrown away

`_parallel_parse_hrm_files` spins up a `ThreadPoolExecutor` to populate
`_hrm_data_cache`, used only to compute stats on the `ActivityEntity`. The
Parquet - the actual heavy artifact - is built in `_polar_hrm_blob_job_impl`,
which calls `polar_hrm.parse_hrm(hrm_path)` again from scratch in a separate
process. The cache never crosses the process boundary, so the "optimization"
just adds a second full parse. Either pass the parsed rows into the job payload
(they are already being serialized to JSON) or drop the plugin-side parallel
parse and parse once, in the worker.

## Resolution status (all findings addressed)

| # | Status | What changed |
|---|--------|--------------|
| 1 | Fixed | Deleted the stray `raise NotImplementedError`; the "override" path now persists updates like every other importer. |
| 2 | Fixed | `_POLAR_DATA_DIR` repointed from `Marco/` to the committed `dvorka/` data; expected values updated. The 4 integration tests now run and pass. |
| 3 | Fixed | `test_build_fit_*` rewritten as `test_hrm_to_parquet_produces_valid_bytes` (tests the real pipeline); `activity_type_index` -> `sport_index`; `parse_smode` test var `has_balance` -> `mph`. |
| 4 | Fixed | Plugin now forwards its parsed HRM (`KEY_HRM_DATA`) to the Bulldozer blob job, which reuses it instead of re-parsing. Single parse; the parallel-parse result is no longer thrown away. |
| 5 | Fixed | Dead `SERVICE_POLAR_FLOW` and `SERVICE_POLAR_PPP` enums removed from `settings.py`. |
| 6 | Documented | The `_SPORT_MAP` "this is wrong" TODO replaced with a clear known-limitation note; the existing speed-based reclassification is the mitigation. True per-user sport-profile mapping remains a separate feature (needs Polar profile-format work), not a bug fix. |
| 7 | Fixed | Removed the redundant task-side `evaluate_activity` - this also stops the plugin's `avg_speed <= max_speed` cap from being silently recomputed away on persist. |
| 8 | Fixed | Added the missing `f` prefix on the three log calls. |
| 9 | Fixed | Extracted `_parse_ini_sections()`; both `parse_hrm` and `parse_pdd` use it. |
| 10 | Fixed | Heuristic literals moved to named module constants (`_CM_INFLATION_GRADIENT_M_PER_KM`, `_CM_INFLATION_MAX_RATIO`, `_CM_PER_M`, `_MAX_PLAUSIBLE_RUN_SPEED_KMH`). |
| 11 | Fixed | Removed the `_parse_start_time` alias; caller uses `_parse_duration`. |
| 12 | Fixed | Tests renamed the 5th `parse_smode` value to `mph` (its real meaning). |
| 13 | Fixed | Plugin now counts un-buildable exercises (`last_failed_count`); the task logs "N exercise(s) could not be parsed and were skipped" and includes a "failed to parse" count in the completion line. |
| 14 | Left as-is | The absolute `KEY_HRM_PATH` through JSON is inherent to the desktop-only, single-machine design and is already guarded (`is_file()`); changing it would be redesign, not a fix. |

Also cleaned up (project ASCII-only rule): all non-ASCII glyphs (em-dashes,
arrows, `x`, `~`) in the three touched files replaced with ASCII equivalents.

Verification: `uv run make py-lint` passes; `uv run make test` passes
(517 passed, 104 skipped, 0 failed). The Polar test file is 16/16 passing, up
from 12 passing + 4 silently skipped.

## What is actually good

- The core intent - deriving `max_speed`/`elevation_gain` from the `[HRData]`
  time series instead of the known-broken `[Trip]` section - is correct, well
  documented, and covered by a committed synthetic fixture (the one genuinely
  solid test, `test_build_activity_uses_hrdata_not_trip_ci`).
- `hrm_to_parquet` emits the same canonical schema as the FIT/GPX/TCX
  converters, so downstream analysis is format-agnostic. Good reuse.
- The `.hrm` magic-byte check in `validation.py` follows the existing
  FIT/GPX/TCX pattern cleanly.
- Parser helpers (`compute_max_speed_kmh`, `compute_elevation_gain`,
  `parse_smode`) are small, pure, and unit-tested - the right shape.

## Recommended order of fixes

1. Remove/replace the `raise NotImplementedError` (Critical, data integrity).
2. Fix the test data path and repair the two broken integration tests, or
   delete them - do not leave permanently-skipped tests implying coverage.
3. Parse each `.hrm` once (collapse #4 and #7).
4. Delete the dead `SERVICE_POLAR_*` enums; rename the feature honestly
   (it is Polar Precision Performance, not Polar Flow).
5. Address the per-user sport-index `TODO` or document it as a known limitation
   in the import UI.
6. Sweep the small stuff: the three missing `f` prefixes, the duplicated INI
   scanner, magic numbers to `commons.py`, and a user-visible "N files skipped"
   line in the import result.
