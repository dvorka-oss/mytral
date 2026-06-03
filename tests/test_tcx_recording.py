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

"""Tests for TCX recording import and extraction."""

import datetime
import pathlib
from types import SimpleNamespace

import pytest

from mytral import commons
from mytral import tasks
from mytral.backends import entities
from mytral.integrations import tcx_recording
from mytral.recordings import tcx_extractor
from mytral.recordings.models import RecordingSummary
from mytral.tasks.do import tcx_import as tcx_import_task_module


class FakeBlobService:
    """Minimal blob service used by TCX helper tests."""

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
    """Blob service stub used by TCX task tests."""

    def __init__(self, store, dataset, config) -> None:
        self.store = store
        self.dataset = dataset
        self.config = config
        self.saved_parquet: list[tuple[str, str, str, bytes]] = []
        self.map_data: list[tuple[str, str, str]] = []

    def open_recording(self, user_id: str, activity_key: str, blob_key: str):
        tcx_data = (
            b'<?xml version="1.0"?><TrainingCenterDatabase></TrainingCenterDatabase>'
        )
        meta = SimpleNamespace(
            original_file_name="track.tcx",
            file_name="data.tcx",
        )
        return SimpleNamespace(read=lambda: tcx_data, close=lambda: None), meta

    def save_parquet(
        self,
        user_id: str,
        activity_key: str,
        source_blob_key: str,
        parquet_data: bytes,
    ) -> None:
        self.saved_parquet.append(
            (user_id, activity_key, source_blob_key, parquet_data)
        )

    def ensure_gpx_map_data(
        self,
        user_id: str,
        activity_key: str,
        blob_key: str,
        **kwargs,
    ) -> None:
        self.map_data.append((user_id, activity_key, blob_key))


class FakeTaskDataset:
    """Dataset stub used by TCX task tests."""

    def __init__(self) -> None:
        self.activity = entities.ActivityEntity()
        self.activity.key = "activity-1"
        self.activity.activity_type_key = ""
        self.updated_entities: list[entities.ActivityEntity] = []

    def get_activity(
        self,
        user_id: str,
        dataset_name: str,
        key: str,
    ) -> entities.ActivityEntity | None:
        if key != self.activity.key:
            return None
        return self.activity

    def update_activity(
        self,
        user_id: str,
        dataset_name: str,
        entity: entities.ActivityEntity,
    ) -> entities.ActivityEntity:
        self.updated_entities.append(entity)
        self.activity = entity
        return entity


def _make_tcx_task_entity() -> tasks.TaskEntity:
    return tasks.TaskEntity(
        key="task-1",
        user_id="test_user",
        task_type=tcx_import_task_module.TcxImportTask.TASK_TYPE,
        status=tasks.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters={
            "user_id": "test_user",
            "dataset_name": "dataset",
            "activity_key": "activity-1",
            "source_blob_uuid": "blob-123",
            "extract_summary": True,
        },
        is_cancelled=False,
    )


@pytest.mark.mytral
def test_tcx_extractor_parses_fixture():
    """Test TCX extractor derives summary data from a fixture."""
    # GIVEN
    tcx_path = pathlib.Path(__file__).parent.joinpath(
        "data", "import", "tcx", "2009_08_30_21_17_25.tcx"
    )
    tcx_data = tcx_path.read_bytes()

    # WHEN
    track_count, track_point_count = tcx_extractor.parse_tcx(tcx_data)
    points = tcx_extractor.extract_gps_points(tcx_data)
    profile = tcx_extractor.extract_elevation_profile(tcx_data)
    summary = tcx_extractor.extract_tcx_summary(tcx_data)

    # THEN
    assert track_count > 0
    assert track_point_count == len(points)
    assert profile
    assert summary.activity_type_key == commons.AT_RIDE
    assert summary.when is not None
    assert summary.when.year == 2009
    assert summary.distance is not None and summary.distance > 0
    assert summary.avg_hr is not None and summary.avg_hr > 0
    assert summary.max_hr == 154
    assert summary.kcal == 714
    print("TCX extractor fixture parsed: DONE")


@pytest.mark.mytral
def test_tcx_import_helper_uploads_parquet_and_summary(monkeypatch):
    """Test TCX import helper uploads blob, parquet and map data."""
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
    tcx_data = b'<?xml version="1.0"?><TrainingCenterDatabase></TrainingCenterDatabase>'

    monkeypatch.setattr(
        tcx_recording.parquet_converter,
        "tcx_to_parquet",
        lambda data: b"parquet-bytes",
    )
    monkeypatch.setattr(
        tcx_recording.tcx_extractor,
        "extract_tcx_summary",
        lambda data: summary,
    )

    def _persist_summary(recording_summary: RecordingSummary) -> None:
        tcx_recording.apply_tcx_summary(activity, recording_summary)

    # WHEN
    blob_key = tcx_recording.import_tcx_recording_bytes(
        user_id="test_user",
        activity_key=activity.key,
        tcx_data=tcx_data,
        original_filename="track.tcx",
        blob_svc=blob_svc,
        extract_summary=True,
        summary_handler=_persist_summary,
        log=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )

    # THEN
    assert blob_key == "blob-123"
    assert blob_svc.uploaded_recordings == [("track.tcx", tcx_data)]
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
    print("TCX recording helper imported summary and parquet: DONE")


@pytest.mark.mytral
def test_tcx_task_generates_parquet_for_existing_blob(monkeypatch):
    """Test TCX task processes existing blob without creating a duplicate blob."""
    # GIVEN
    dataset = FakeTaskDataset()
    task_entity = _make_tcx_task_entity()
    summary = RecordingSummary(
        activity_type_key=commons.AT_RIDE,
        when=datetime.datetime(2024, 1, 1, 6, 7, 8),
        distance=12345,
        avg_hr=150,
        max_hr=170,
    )
    blob_service = FakeTaskBlobService(store=object(), dataset=dataset, config=object())

    monkeypatch.setattr(
        tcx_import_task_module.blob_svc_module,
        "ActivityBlobService",
        lambda store, dataset, config: blob_service,
    )
    monkeypatch.setattr(
        tcx_import_task_module.parquet_converter,
        "tcx_to_parquet",
        lambda data: b"parquet-bytes",
    )
    monkeypatch.setattr(
        tcx_import_task_module.tcx_extractor,
        "extract_tcx_summary",
        lambda data: summary,
    )

    task = tcx_import_task_module.TcxImportTask(
        task_entity=task_entity,
        logger=SimpleNamespace(info=lambda *args, **kwargs: None),
        log_callback=None,
        config=SimpleNamespace(),
        dataset=dataset,
        blobstore=object(),
    )

    # WHEN
    task.execute()

    # THEN
    assert blob_service.saved_parquet == [
        ("test_user", "activity-1", "blob-123", b"parquet-bytes")
    ]
    assert blob_service.map_data == [("test_user", "activity-1", "blob-123")]
    assert dataset.updated_entities
    assert dataset.activity.activity_type_key == commons.AT_RIDE
    assert task_entity.progress == 100
    print("TCX task processed existing blob without duplicate upload: DONE")
