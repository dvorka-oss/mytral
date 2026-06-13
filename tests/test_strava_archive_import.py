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

"""Tests for Strava archive recording import."""

import datetime
import gzip
import json
import pathlib
import uuid
from types import SimpleNamespace

import pandas
import pytest

from mytral import config
from mytral import loggers
from mytral import persistences
from mytral import tasks
from mytral.backends import entities
from mytral.integrations import gpx_recording
from mytral.integrations import strava_user_archive
from mytral.recordings.models import RecordingSummary
from mytral.tasks.do import strava_archive_import
from tests import _given


class FakeLogger:
    """Minimal logger used by task tests."""

    def info(self, *args, **kwargs) -> None:
        pass

    def warning(self, *args, **kwargs) -> None:
        pass


class FakeDataset:
    """Minimal dataset used by task tests."""

    def __init__(self, dataset_name: str) -> None:
        self.dataset_name = dataset_name
        self.created_activities: list[entities.ActivityEntity] = []
        self.activities: dict[str, entities.ActivityEntity] = {}

    def profile(self, user_id: str) -> SimpleNamespace:
        return SimpleNamespace(dataset_name=self.dataset_name)

    def create_activities(
        self,
        user_id: str,
        dataset_name: str,
        entity_list: list[entities.ActivityEntity],
    ) -> None:
        self.created_activities.extend(entity_list)
        for activity in entity_list:
            self.activities[activity.key] = activity

    def get_activity(
        self, user_id: str, dataset_name: str, key: str
    ) -> entities.ActivityEntity | None:
        return self.activities.get(key)

    def update_activity(
        self,
        user_id: str,
        dataset_name: str,
        entity: entities.ActivityEntity,
    ) -> entities.ActivityEntity:
        self.activities[entity.key] = entity
        return entity

    def update_activities(
        self,
        user_id: str,
        dataset_name: str,
        activities: list[entities.ActivityEntity],
    ) -> None:
        for activity in activities:
            self.activities[activity.key] = activity

    def list_activities(
        self,
        user_id: str,
        dataset_name: str,
        year: int | None = None,
    ) -> list[entities.ActivityEntity]:
        if year is not None:
            return [
                a
                for a in self.activities.values()
                if getattr(a, "when_year", 0) == year
            ]
        return list(self.activities.values())


class FakeBlobService:
    """Minimal blob service used by helper tests."""

    def __init__(self) -> None:
        self.uploaded_recordings: list[tuple[str, bytes]] = []
        self.saved_parquet: list[tuple[str, bytes]] = []
        self.map_data: list[tuple[str, str]] = []

    def upload_recording(
        self,
        user_id: str,
        activity_key: str,
        uploaded_file,
        original_filename: str,
        content_type: str = "",
        **kwargs,
    ) -> SimpleNamespace:
        self.uploaded_recordings.append((original_filename, uploaded_file.read()))
        return SimpleNamespace(blob_key="blob-123")

    def save_parquet(
        self,
        user_id: str,
        activity_key: str,
        source_blob_key: str,
        parquet_data: bytes,
    ) -> None:
        self.saved_parquet.append((source_blob_key, parquet_data))

    def ensure_gpx_map_data(
        self,
        user_id: str,
        activity_key: str,
        blob_key: str,
        **kwargs,
    ) -> None:
        self.map_data.append((activity_key, blob_key))


class FakeTaskBlobService:
    """Blob service stub for archive task tests."""

    def __init__(self, store, dataset, config) -> None:
        self.store = store
        self.dataset = dataset
        self.config = config
        self.deleted_activity_blobs: list[str] = []

    def delete_all_activity_blobs(self, user_id: str, activity_key: str) -> None:
        self.deleted_activity_blobs.append(activity_key)


def _make_task_entity(
    data_dir: pathlib.Path, extra_parameters: dict | None = None
) -> tasks.TaskEntity:
    parameters = {
        "user_id": "test_user",
        "dataset_name": "dataset",
        strava_archive_import.StravaArchiveImportTask.DATA_DIR_KEY: str(data_dir),
        "correlation_id": "corr-1",
    }
    if extra_parameters:
        parameters.update(extra_parameters)
    return tasks.TaskEntity(
        key="task-1",
        user_id="test_user",
        task_type=strava_archive_import.StravaArchiveImportTask.TASK_TYPE,
        status=tasks.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters=parameters,
        is_cancelled=False,
    )


@pytest.mark.mytral
def test_strava_archive_plugin_parses_recording_filename(monkeypatch, tmp_path):
    # GIVEN
    columns = list(
        strava_user_archive.StravaUserArchiveActivitiesImportPlugin._COLS_A_CSV
    )
    row = [""] * len(columns)
    row[0] = 123456
    row[1] = "Jan 1, 2024, 1:02:03 AM"
    row[2] = "Morning ride"
    row[3] = ""
    row[4] = "Ride"
    row[5] = "Archive description"
    row[6] = "1:00:00"
    row[7] = "42.0"
    row[8] = "150"
    row[15] = "activities/track.gpx.gz"
    row[-1] = "media/photo.jpg"
    frame = pandas.DataFrame([row], columns=columns)
    monkeypatch.setattr(pandas, "read_csv", lambda *args, **kwargs: frame)

    archive_dir = tmp_path / "strava-archive"
    archive_dir.mkdir()
    plugin = strava_user_archive.StravaUserArchiveActivitiesImportPlugin()

    # WHEN
    app_config = config.MytralConfig(persistence_data_dir=tmp_path)
    user_id: str = str(uuid.uuid4())
    user_display_name: str = "Strava Archive"
    user_name: str = "strava"
    user_password: str = "archive"
    _, u_ds, user_profile = _given.given_test(
        test_config=app_config,
        user_id=user_id,
        user_name=user_name,
        user_display_name=user_display_name,
        user_password=user_password,
    )

    activities = plugin.import_activities(
        datasets={strava_user_archive.STRAVA_ARCHIVE_DATA_DIR_KEY: archive_dir},
        user_profile=user_profile,
        correlation_id=str(uuid.uuid4()),
    )

    # THEN
    assert len(activities) == 1
    assert activities[0]._recording_path == "activities/track.gpx.gz"
    assert activities[0]._photo_paths == ["media/photo.jpg"]
    print("DONE: Strava archive recording filename parsed")


@pytest.mark.mytral
def test_import_gpx_recording_bytes_generates_parquet_and_summary(monkeypatch):
    # GIVEN
    blob_svc = FakeBlobService()
    activity = entities.ActivityEntity()
    activity.key = "activity-1"
    activity.activity_type_key = ""
    activity.hours = 0
    activity.minutes = 0
    activity.seconds = 0
    summary = RecordingSummary(
        activity_type_key="ride",
        when=datetime.datetime(2024, 1, 1, 6, 7, 8),
        hours=1,
        minutes=2,
        seconds=3,
        distance=12345,
        avg_hr=150,
        max_hr=170,
        elevation_gain=250,
        name_hint="Morning ride",
    )
    gpx_data = b'<?xml version="1.0"?><gpx/>'

    monkeypatch.setattr(
        gpx_recording.parquet_converter,
        "gpx_to_parquet",
        lambda data: b"parquet-bytes",
    )
    monkeypatch.setattr(
        gpx_recording.gpx_extractor,
        "extract_gpx_summary",
        lambda data: summary,
    )

    def _persist_summary(recording_summary: RecordingSummary) -> None:
        gpx_recording.apply_gpx_summary(activity, recording_summary)

    # WHEN
    blob_key = gpx_recording.import_gpx_recording_bytes(
        user_id="test_user",
        activity_key=activity.key,
        gpx_data=gpx_data,
        original_filename="track.gpx",
        blob_svc=blob_svc,
        extract_summary=True,
        summary_handler=_persist_summary,
        log=FakeLogger(),
    )

    # THEN
    assert blob_key == "blob-123"
    assert blob_svc.uploaded_recordings == [("track.gpx", gpx_data)]
    assert blob_svc.saved_parquet == [("blob-123", b"parquet-bytes")]
    assert blob_svc.map_data == [("activity-1", "blob-123")]
    assert activity.activity_type_key == "ride"
    assert activity.when_year == 2024
    assert activity.when_month == 1
    assert activity.when_day == 1
    assert activity.when_hour == 6
    assert activity.when_minute == 7
    assert activity.when_second == 8
    assert activity.hours == 1
    assert activity.minutes == 2
    assert activity.seconds == 3
    assert activity.distance == 12345
    assert activity.avg_hr == 150
    assert activity.max_hr == 170
    assert activity.elevation_gain == 250
    assert activity.name == "Morning ride"
    print("DONE: GPX recording helper imported summary and parquet")


@pytest.mark.mytral
def test_strava_archive_task_imports_gpx_gz_and_tcx_gz(monkeypatch, tmp_path):
    # GIVEN: a sandbox directory with GPX+TCX recording files and an input payload
    sandbox = tmp_path / "sandbox"
    input_dir = sandbox / "input"
    input_dir.mkdir(parents=True)
    data_dir = sandbox / "data"
    data_dir.mkdir(parents=True)
    recordings_dir = data_dir / "activities"
    recordings_dir.mkdir(parents=True)

    raw_gpx = b'<?xml version="1.0"?><gpx/>'
    raw_tcx = b"<tcx/>"
    (recordings_dir / "track.gpx.gz").write_bytes(gzip.compress(raw_gpx))
    (recordings_dir / "ignored.tcx.gz").write_bytes(gzip.compress(raw_tcx))

    gpx_activity = entities.ActivityEntity()
    gpx_activity.key = "activity-gpx"
    gpx_activity.name = "GPX Activity"
    gpx_activity._photo_paths = []
    gpx_activity._recording_path = "activities/track.gpx.gz"

    tcx_activity = entities.ActivityEntity()
    tcx_activity.key = "activity-tcx"
    tcx_activity.name = "TCX Activity"
    tcx_activity._photo_paths = []
    tcx_activity._recording_path = "activities/ignored.tcx.gz"

    def _to_payload_dict(a):
        d = a.to_dict()
        d["_recording_path"] = getattr(a, "_recording_path", "")
        d["_photo_paths"] = getattr(a, "_photo_paths", []) or []
        return d

    payload = {
        "user_id": "test_user",
        "data_dir": str(data_dir),
        "import_photos": False,
        "import_recordings": True,
        "activities": [_to_payload_dict(gpx_activity), _to_payload_dict(tcx_activity)],
    }
    with open(input_dir / "payload.json", "w") as fh:
        json.dump(payload, fh, cls=strava_archive_import._PathEncoder)

    # WHEN: run the blob job implementation directly
    strava_archive_import._strava_blob_job_impl(0, sandbox)

    # THEN: output payload has blob keys and summaries for both activities
    output_file = sandbox / "output" / "payload.json"
    assert output_file.exists()

    with open(output_file) as fh:
        result = json.load(fh)

    activities_out = result["activities"]
    assert len(activities_out) == 2

    gpx_out = next(a for a in activities_out if a["key"] == "activity-gpx")
    tcx_out = next(a for a in activities_out if a["key"] == "activity-tcx")
    assert len(gpx_out.get("recorded_blob_keys", [])) == 1
    assert len(tcx_out.get("recorded_blob_keys", [])) == 1

    summaries = result.get("summaries", {})
    assert "activity-gpx" in summaries or "activity-tcx" in summaries

    print("DONE: Strava archive blob job processed GPX and TCX recordings")


@pytest.mark.mytral
def test_strava_archive_task_applies_toggles_and_date_filter(monkeypatch, tmp_path):
    # GIVEN
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "activities.csv").write_text("placeholder", encoding="utf-8")

    def _new_activity(
        key: str, when: tuple[int, int, int], recording: str, photo: str
    ) -> entities.ActivityEntity:
        activity = entities.ActivityEntity()
        activity.key = key
        activity.name = key
        activity.when_year = when[0]
        activity.when_month = when[1]
        activity.when_day = when[2]
        activity._recording_path = recording
        activity._photo_paths = [photo]
        return activity

    early_activity = _new_activity(
        "a-early", (2024, 1, 2), "activities/a.gpx.gz", "x.jpg"
    )
    in_range_activity = _new_activity(
        "a-in-range",
        (2024, 1, 15),
        "activities/b.gpx.gz",
        "y.jpg",
    )
    late_activity = _new_activity(
        "a-late", (2024, 2, 4), "activities/c.gpx.gz", "z.jpg"
    )

    class FakePlugin:
        def import_activities(self, datasets, user_profile, correlation_id):
            return [early_activity, in_range_activity, late_activity]

    monkeypatch.setattr(
        strava_archive_import.plugins.registry,
        "get_plugin",
        lambda name: FakePlugin(),
    )

    # monkeypatch Bulldozer to be a no-op — write empty outputs per chunk dir
    class NoOpBulldozer(strava_archive_import.bulldozer.SubtaskBulldozer):
        def __init__(self, **kwargs):
            self._worker_to_cpu = 2
            self.logger = FakeLogger()
            self.usr_task_dir = kwargs.get("usr_task_dir", tmp_path)

        def make_sandbox(self):
            subtask_dir = self.usr_task_dir / "subtasks" / "noop"
            job_dirs = []
            for i in range(16):
                job_dir = subtask_dir / f"job-{i}"
                (job_dir / "input").mkdir(parents=True, exist_ok=True)
                (job_dir / "work").mkdir(parents=True, exist_ok=True)
                (job_dir / "output").mkdir(parents=True, exist_ok=True)
                job_dirs.append(job_dir)
            return job_dirs

        def run(self, *, job_dirs=None, job_function=None):
            # write empty output payloads so the collect phase passes
            for job_dir in job_dirs or []:
                out_dir = job_dir / "output"
                out_dir.mkdir(parents=True, exist_ok=True)
                with open(out_dir / "payload.json", "w") as fh:
                    json.dump({"activities": [], "summaries": {}}, fh)

    monkeypatch.setattr(
        strava_archive_import.bulldozer,
        "SubtaskBulldozer",
        NoOpBulldozer,
    )

    dataset = FakeDataset(dataset_name="dataset")
    task_entity = _make_task_entity(
        archive_dir,
        {
            strava_archive_import.StravaArchiveImportTask.IMPORT_PHOTOS_KEY: False,
            strava_archive_import.StravaArchiveImportTask.IMPORT_RECORDINGS_KEY: False,
            strava_archive_import.StravaArchiveImportTask.IMPORT_FROM_DATE_KEY: (
                "2024-01-10"
            ),
            strava_archive_import.StravaArchiveImportTask.IMPORT_TO_DATE_KEY: (
                "2024-01-31"
            ),
        },
    )
    task = strava_archive_import.StravaArchiveImportTask(
        task_entity=task_entity,
        logger=FakeLogger(),
        log_callback=None,
        config=SimpleNamespace(persistence_data_dir=tmp_path),
        dataset=dataset,
        blobstore=object(),
    )

    # WHEN
    task.execute()

    # THEN: only in-range activity is created (date filter), photos disabled
    assert [activity.key for activity in dataset.created_activities] == ["a-in-range"]
    assert task_entity.progress == 100
    print("DONE: Strava archive task applies toggles and date range filtering")


@pytest.mark.mytral
def test_strava_archive_task_on_conflict_skip_filters_existing(monkeypatch, tmp_path):
    # GIVEN
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "activities.csv").write_text("placeholder", encoding="utf-8")

    incoming = entities.ActivityEntity()
    incoming.key = "new-key"
    incoming.name = "Incoming duplicate"
    incoming.src = "strava"
    incoming.src_key = "12345"
    incoming._photo_paths = []
    incoming._recording_path = ""

    class FakePlugin:
        def import_activities(self, datasets, user_profile, correlation_id):
            return [incoming]

    monkeypatch.setattr(
        strava_archive_import.plugins.registry,
        "get_plugin",
        lambda name: FakePlugin(),
    )
    monkeypatch.setattr(
        strava_archive_import.blob_svc_module,
        "ActivityBlobService",
        FakeTaskBlobService,
    )

    dataset = FakeDataset(dataset_name="dataset")
    existing = entities.ActivityEntity()
    existing.key = "existing-key"
    existing.name = "Existing"
    existing.src = "strava"
    existing.src_key = "12345"
    dataset.activities[existing.key] = existing

    task_entity = _make_task_entity(
        archive_dir,
        {
            "on_conflict": "skip",
        },
    )
    task = strava_archive_import.StravaArchiveImportTask(
        task_entity=task_entity,
        logger=FakeLogger(),
        log_callback=None,
        config=SimpleNamespace(persistence_data_dir=tmp_path),
        dataset=dataset,
        blobstore=object(),
    )

    # WHEN
    task.execute()

    # THEN
    assert dataset.created_activities == []
    assert task_entity.progress == 100
    print("DONE: Strava archive on_conflict skip filters duplicates")


def test_plugin(tmp_path: pathlib.Path):
    #
    # GIVEN
    #
    archive_dir = _given.TEST_DATA_STRAVA_ARCHIVE

    app_config = config.MytralConfig(persistence_data_dir=tmp_path)
    user_id: str = str(uuid.uuid4())
    user_display_name: str = "Strava Archive"
    user_name: str = "strava"
    user_password: str = "archive"
    _, u_ds, user_profile = _given.given_test(
        test_config=app_config,
        user_id=user_id,
        user_name=user_name,
        user_display_name=user_display_name,
        user_password=user_password,
    )

    #
    # WHEN
    #
    plugin = strava_user_archive.StravaUserArchiveActivitiesImportPlugin(
        logger=loggers.MytralPrintLogger()
    )
    activities = plugin.import_activities(
        datasets={strava_user_archive.STRAVA_ARCHIVE_DATA_DIR_KEY: archive_dir},
        user_profile=user_profile,
        output_path=tmp_path,
        correlation_id="TEST-CORRELATION-ID",
    )

    #
    # THEN
    #
    print(f"{len(activities)} activities imported")

    # activities
    assert activities
    persistences.save_json(
        file_path=tmp_path / "data" / user_id / "LIFELONG-activities.json",
        data_dict=[a.to_dict() for a in activities],
    )

    # gear asserts
    gears_by_name = u_ds.list_gear(
        user_id=user_id, dataset_name=user_profile.dataset_name
    ).to_dict_by_name()
    # bike gear: spesl
    g = gears_by_name.get("Spešl 29er")
    assert g
    assert g.vendor
    assert g.model
    assert g.external_id_map
