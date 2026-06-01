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
import pathlib
from types import SimpleNamespace

import pandas
import pytest

from mytral import tasks
from mytral.backends import entities
from mytral.integrations import gpx_recording
from mytral.integrations import strava_user_archive
from mytral.recordings.models import RecordingSummary
from mytral.tasks.do import strava_archive_import


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
    row[3] = "Ride"
    row[4] = "Archive description"
    row[5] = "1:00:00"
    row[6] = "42.0"
    row[7] = "150"
    row[12] = "activities/track.gpx.gz"
    row[-1] = "media/photo.jpg"
    frame = pandas.DataFrame([row], columns=columns)
    monkeypatch.setattr(pandas, "read_csv", lambda *args, **kwargs: frame)

    archive_dir = tmp_path / "strava-archive"
    archive_dir.mkdir()
    plugin = strava_user_archive.StravaUserArchiveActivitiesImportPlugin()

    # WHEN
    activities = plugin.import_activities(
        datasets={strava_user_archive.STRAVA_ARCHIVE_DATA_DIR_KEY: archive_dir},
        user_profile=None,
        correlation_id="corr-1",
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
    # GIVEN
    archive_dir = tmp_path / "archive"
    recordings_dir = archive_dir / "activities"
    recordings_dir.mkdir(parents=True)
    (archive_dir / "activities.csv").write_text("placeholder", encoding="utf-8")

    raw_gpx = b'<?xml version="1.0"?><gpx/>'
    (recordings_dir / "track.gpx.gz").write_bytes(gzip.compress(raw_gpx))
    (recordings_dir / "ignored.tcx.gz").write_bytes(gzip.compress(b"<tcx/>"))

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

    class FakePlugin:
        def import_activities(self, datasets, user_profile, correlation_id):
            return [gpx_activity, tcx_activity]

    captured: list[tuple[str, str, bytes, str]] = []

    def _fake_import_gpx_recording_bytes(
        *,
        user_id: str,
        activity_key: str,
        gpx_data: bytes,
        original_filename: str,
        blob_svc,
        extract_summary: bool = False,
        summary_handler=None,
        log=None,
    ) -> str:
        captured.append((user_id, activity_key, gpx_data, original_filename))
        return "blob-123"

    def _fake_import_tcx_recording_bytes(
        *,
        user_id: str,
        activity_key: str,
        tcx_data: bytes,
        original_filename: str,
        blob_svc,
        extract_summary: bool = False,
        summary_handler=None,
        log=None,
    ) -> str:
        captured.append((user_id, activity_key, tcx_data, original_filename))
        return "blob-456"

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
    monkeypatch.setattr(
        strava_archive_import.gpx_recording,
        "import_gpx_recording_bytes",
        _fake_import_gpx_recording_bytes,
    )
    monkeypatch.setattr(
        strava_archive_import.tcx_recording,
        "import_tcx_recording_bytes",
        _fake_import_tcx_recording_bytes,
    )

    dataset = FakeDataset(dataset_name="dataset")
    task_entity = _make_task_entity(archive_dir)
    task = strava_archive_import.StravaArchiveImportTask(
        task_entity=task_entity,
        logger=FakeLogger(),
        log_callback=None,
        config=SimpleNamespace(),
        dataset=dataset,
        blobstore=object(),
    )

    # WHEN
    task.execute()

    # THEN
    assert captured == [
        ("test_user", "activity-gpx", raw_gpx, "track.gpx"),
        ("test_user", "activity-tcx", b"<tcx/>", "ignored.tcx"),
    ]
    assert task_entity.progress == 100
    print("DONE: Strava archive task imported GPX and TCX")


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

    class StrictBlobService(FakeTaskBlobService):
        def upload_photos(self, *args, **kwargs):
            raise AssertionError("photos should not be uploaded when disabled")

    monkeypatch.setattr(
        strava_archive_import.plugins.registry,
        "get_plugin",
        lambda name: FakePlugin(),
    )
    monkeypatch.setattr(
        strava_archive_import.blob_svc_module,
        "ActivityBlobService",
        StrictBlobService,
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
        config=SimpleNamespace(),
        dataset=dataset,
        blobstore=object(),
    )
    monkeypatch.setattr(
        task,
        "_import_recording",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("recordings should not be imported when disabled")
        ),
    )

    # WHEN
    task.execute()

    # THEN
    assert [activity.key for activity in dataset.created_activities] == ["a-in-range"]
    assert task_entity.progress == 100
    print("DONE: Strava archive task applies toggles and date range filtering")
