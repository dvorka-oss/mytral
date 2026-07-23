# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""Tests for Polar Flow export recording import (TCX build, parquet, task wiring)."""

import datetime
import pathlib
import zipfile

import pytest

from mytral import blobstore as blobstore_pkg
from mytral import config
from mytral import tasks
from mytral.blobstore import activity_service as blob_svc_module
from mytral.integrations import polar_flow
from mytral.integrations import polar_flow_recording
from mytral.recordings import parquet_converter
from mytral.recordings import tcx_extractor
from mytral.tasks.do import polar_flow_export_import
from tests import _given

_EXPORT_FIXTURES = (
    pathlib.Path(__file__).parent / "data" / "import" / "polar-flow-export"
)


def _load_fixture(name: str) -> dict:
    import json

    return json.loads((_EXPORT_FIXTURES / name).read_text(encoding="utf-8"))


def _channels(recording_data) -> set[str]:
    """Return the set of channels that carry any data in a RecordingData."""
    present = set()
    if any(v is not None for v in recording_data.hr_values):
        present.add("hr")
    if recording_data.has_speed:
        present.add("speed")
    if recording_data.has_cadence:
        present.add("cadence")
    if recording_data.has_altitude:
        present.add("altitude")
    if recording_data.has_gps:
        present.add("gps")
    if recording_data.has_power:
        present.add("power")
    return present


@pytest.mark.mytral
def test_session_to_tcx_captures_all_channels():
    """A full outdoor session round-trips every channel through TCX to parquet."""
    #
    # GIVEN
    #
    session = _load_fixture("training-session_2025-01-19T09-33-04_road-ride.json")

    #
    # WHEN
    #
    tcx_bytes = polar_flow_recording.session_to_tcx(session)
    recording = parquet_converter.load_parquet(
        parquet_converter.tcx_to_parquet(tcx_bytes)
    )

    #
    # THEN
    #
    # every recorded channel survives the export -> TCX -> parquet round-trip
    assert _channels(recording) == {
        "hr",
        "speed",
        "cadence",
        "altitude",
        "gps",
        "power",
    }
    # four 1 Hz samples; the "NaN" cadence sample is dropped, the rest kept
    assert len(recording.timestamps) == 4
    assert sum(1 for v in recording.hr_values if v is not None) == 4
    assert sum(1 for v in recording.cadence_values if v is not None) == 3
    assert sum(1 for v in recording.power_values if v is not None) == 4
    # the GPS track is recoverable for the map
    points = tcx_extractor.extract_gps_points(tcx_bytes)
    assert len(points) == 4
    print("DONE: outdoor session TCX carries HR/speed/cadence/altitude/GPS/power")


@pytest.mark.mytral
def test_session_to_tcx_hr_only_indoor():
    """An indoor session with only HR samples yields an HR-only recording, no GPS."""
    #
    # GIVEN - HR samples, no GPS track, no other channels
    #
    session = {
        "identifier": {"id": "1"},
        "startTime": "2025-02-01T18:00:00.000",
        "timezoneOffsetMinutes": 60,
        "sport": {"id": "15"},
        "exercises": [
            {
                "startTime": "2025-02-01T18:00:00.000",
                "sport": {"id": "15"},
                "samples": {
                    "samples": [
                        {
                            "type": "HEART_RATE",
                            "intervalMillis": 1000,
                            "values": [95.0, 100.0, 110.0],
                        }
                    ]
                },
                "routes": {},
            }
        ],
    }

    #
    # WHEN
    #
    tcx_bytes = polar_flow_recording.session_to_tcx(session)
    recording = parquet_converter.load_parquet(
        parquet_converter.tcx_to_parquet(tcx_bytes)
    )

    #
    # THEN
    #
    assert _channels(recording) == {"hr"}
    assert len(recording.timestamps) == 3
    print("DONE: indoor HR-only session yields an HR recording with no GPS")


@pytest.mark.mytral
def test_session_to_tcx_none_without_samples_or_gps():
    """A session with no per-second samples and no GPS produces no recording."""
    #
    # GIVEN / WHEN / THEN
    #
    manual = {
        "identifier": {"id": "1"},
        "startTime": "2025-03-01T07:00:00.000",
        "sport": {"id": "1"},
        "exercises": [{"startTime": "2025-03-01T07:00:00.000", "sport": {"id": "1"}}],
    }
    assert polar_flow_recording.session_to_tcx(manual) is None
    # the committed indoor-strength fixture also has empty samples/routes
    strength = _load_fixture(
        "training-session_2025-02-01T18-00-00_strength-indoor.json"
    )
    assert polar_flow_recording.session_to_tcx(strength) is None
    print("DONE: manual/empty sessions produce no recording (None)")


def _make_task(zip_path, tmp_path):
    """Build a PolarFlowExportImportTask wired to a real dataset and blob store."""
    cfg = config.MytralConfig(persistence_data_dir=tmp_path)
    ds, user_ds, profile = _given.given_test(cfg, user_id="polar_rec_task_user")
    polar_flow.app_user_ds = user_ds
    store = blobstore_pkg.create_blobstore(cfg)
    task_entity = tasks.TaskEntity(
        key="task-rec",
        user_id=profile.user_id,
        task_type=polar_flow_export_import.PolarFlowExportImportTask.TASK_TYPE,
        status=tasks.TaskStatus.QUEUED,
        created_at=datetime.datetime(2025, 1, 1),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters={
            "user_id": profile.user_id,
            "dataset_name": profile.dataset_name,
            "zip_path": str(zip_path),
            "on_conflict": polar_flow_export_import.ON_CONFLICT_SKIP,
        },
        is_cancelled=False,
    )
    task = polar_flow_export_import.PolarFlowExportImportTask(
        task_entity=task_entity,
        logger=polar_flow.app_logger,
        log_callback=None,
        config=cfg,
        dataset=user_ds,
        blobstore=store,
    )
    return task, user_ds, profile, store, cfg


@pytest.mark.mytral
def test_export_task_imports_activities_and_recordings(tmp_path: pathlib.Path):
    """The full task imports summaries AND attaches recordings with all channels."""
    #
    # GIVEN - a ZIP of the committed real-shape fixtures
    #
    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for json_file in sorted(_EXPORT_FIXTURES.glob("*.json")):
            archive.write(json_file, arcname=json_file.name)

    task, user_ds, profile, store, cfg = _make_task(zip_path, tmp_path)
    blob_svc = blob_svc_module.ActivityBlobService(
        store=store, dataset=user_ds, config=cfg
    )

    #
    # WHEN
    #
    task.execute()

    #
    # THEN
    #
    stored = user_ds.all_activities(profile.user_id, profile.dataset_name)
    by_src = {a.src_key: a for a in stored.values()}

    # the outdoor ride carries a recording with every channel
    ride = by_src["8067285121"]
    assert len(ride.recorded_blob_keys or []) == 1
    assert len(ride.recorded_parquet_keys or {}) == 1
    source_uuid = next(iter(ride.recorded_parquet_keys))
    stream, _meta = blob_svc.open_parquet(profile.user_id, ride.key, source_uuid)
    recording = parquet_converter.load_parquet(stream.read())
    assert _channels(recording) == {
        "hr",
        "speed",
        "cadence",
        "altitude",
        "gps",
        "power",
    }

    # the indoor-strength session has no per-second data -> no recording
    strength = by_src["9000000001"]
    assert not (strength.recorded_blob_keys or [])
    print("DONE: export task imported activities and a full-channel ride recording")


@pytest.mark.mytral
def test_export_task_precomputes_gps_map(tmp_path: pathlib.Path):
    """The task precomputes map polylines so the feed never blocks encoding them.

    Regression: recordings imported without precomputed maps made the activity feed
    (which renders a mini-map per activity) lazily encode hundreds of tracks at once.
    """
    #
    # GIVEN - the road-ride recording imported via the task
    #
    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for json_file in sorted(_EXPORT_FIXTURES.glob("*.json")):
            archive.write(json_file, arcname=json_file.name)
    task, user_ds, profile, store, cfg = _make_task(zip_path, tmp_path)
    task.execute()
    stored = user_ds.all_activities(profile.user_id, profile.dataset_name)
    ride = {a.src_key: a for a in stored.values()}["8067285121"]
    blob_key = ride.recorded_blob_keys[0].split(".")[0]

    #
    # WHEN - the feed reads the map metadata WITHOUT triggering generation
    #
    meta = store.get_blob_metadata(profile.user_id, blob_key)

    #
    # THEN - the polyline is already present (precomputed at import)
    #
    assert meta.summary_polyline, "map polyline was not precomputed at import"
    assert meta.summary_bbox is not None
    assert meta.track_point_count == 4
    print("DONE: import precomputed the GPS map, so the feed does not block")
