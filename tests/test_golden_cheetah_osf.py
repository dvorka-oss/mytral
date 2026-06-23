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

"""Unit and integration tests for the GoldenCheetah OSF import plugin and task."""

import datetime
import io
import json
import os
import pathlib
import zipfile

import pytest

from mytral import commons
from mytral import config as mytral_config
from mytral import settings
from mytral import tasks
from mytral.backends import entities
from mytral.blobstore.filesystem import FilesystemBlobStore
from mytral.integrations import golden_cheetah_osf
from mytral.integrations.golden_cheetah_osf import _metric_float
from mytral.integrations.golden_cheetah_osf import _ride_to_activity
from mytral.integrations.golden_cheetah_osf import GoldenCheetahOsfImportPlugin
from mytral.tasks.do import golden_cheetah_osf_import
from mytral.tasks.do.golden_cheetah_osf_import import _gc_csv_blob_job_impl

_ATHLETE_UUID = "aabbccdd-1234-5678-abcd-000000000001"

_FULL_METRICS = {
    "workout_time": "3661.00000",  # 1h 0m 1s
    "total_distance": "30.500",  # 30.5 km → 30500 m
    "average_hr": ["145.50000", "3000.00000"],  # weighted average list
    "max_heartrate": 175.0,
    "average_power": ["200.00000", "3000.00000"],
    "max_power": 450.0,
    "average_cad": ["85.00000", "3000.00000"],
    "max_cadence": 120.0,
    "max_speed": 55.5,
    "elevation_gain": 273.7,
    "total_kcalories": 980.0,
}

_FULL_RIDE = {
    "date": "2020/02/21 13:35:12 UTC",
    "sport": "Bike",
    "data": "TDSP-HC-AGL-E---",
    "METRICS": _FULL_METRICS,
}


# ---------------------------------------------------------------------------
# _metric_float
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_metric_float_from_float():
    # GIVEN
    metrics = {"val": 42.5}

    # WHEN
    result = _metric_float(metrics, "val")

    # THEN
    assert result == 42.5
    print("DONE: _metric_float extracts plain float")


@pytest.mark.mytral
def test_metric_float_from_string():
    # GIVEN
    metrics = {"val": "4010.00000"}

    # WHEN
    result = _metric_float(metrics, "val")

    # THEN
    assert result == 4010.0
    print("DONE: _metric_float extracts numeric string")


@pytest.mark.mytral
def test_metric_float_from_weighted_list():
    # GIVEN
    metrics = {"val": ["123.37956", "8535.00000"]}

    # WHEN
    result = _metric_float(metrics, "val")

    # THEN
    assert abs(result - 123.37956) < 1e-5
    print("DONE: _metric_float extracts first element of weighted-average list")


@pytest.mark.mytral
def test_metric_float_missing_returns_default():
    # GIVEN
    metrics = {}

    # WHEN
    result = _metric_float(metrics, "nonexistent")

    # THEN
    assert result == 0.0
    print("DONE: _metric_float returns default for missing key")


@pytest.mark.mytral
def test_metric_float_none_returns_default():
    # GIVEN
    metrics = {"val": None}

    # WHEN
    result = _metric_float(metrics, "val", default=-1.0)

    # THEN
    assert result == -1.0
    print("DONE: _metric_float returns default when value is None")


# ---------------------------------------------------------------------------
# _ride_to_activity
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_ride_to_activity_basic_fields():
    # GIVEN
    ride = _FULL_RIDE

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN — date parsed correctly
    assert activity is not None
    assert activity.when_year == 2020
    assert activity.when_month == 2
    assert activity.when_day == 21
    assert activity.when_hour == 13
    assert activity.when_minute == 35
    assert activity.when_second == 12
    print("DONE: _ride_to_activity parses date correctly")


@pytest.mark.mytral
def test_ride_to_activity_duration():
    # GIVEN
    ride = dict(_FULL_RIDE)
    ride["METRICS"] = dict(_FULL_METRICS, workout_time="7265.00000")  # 2h 1m 5s

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.hours == 2
    assert activity.minutes == 1
    assert activity.seconds == 5
    print("DONE: _ride_to_activity splits duration into h/m/s")


@pytest.mark.mytral
def test_ride_to_activity_distance():
    # GIVEN
    ride = _FULL_RIDE

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN — 30.5 km → 30500 m
    assert activity is not None
    assert activity.distance == 30500
    print("DONE: _ride_to_activity converts km to metres")


@pytest.mark.mytral
def test_ride_to_activity_metrics():
    # GIVEN
    ride = _FULL_RIDE

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert abs(activity.avg_hr - 145.5) < 1e-3
    assert activity.max_hr == 175.0
    assert abs(activity.avg_watts - 200.0) < 1e-3
    assert activity.max_watts == 450.0
    assert abs(activity.avg_cadence - 85.0) < 1e-3
    assert activity.max_cadence == 120.0
    assert activity.max_speed == 55.5
    assert activity.elevation_gain == 273  # rounded from 273.7
    assert activity.kcal == 980
    print("DONE: _ride_to_activity maps all metrics correctly")


@pytest.mark.mytral
def test_ride_to_activity_sport_bike():
    # GIVEN
    ride = dict(_FULL_RIDE, sport="Bike")

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.activity_type_key == commons.AT_RIDE
    print("DONE: _ride_to_activity maps Bike sport to AT_RIDE")


@pytest.mark.mytral
def test_ride_to_activity_sport_run():
    # GIVEN
    ride = dict(_FULL_RIDE, sport="Run")

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.activity_type_key == commons.AT_RUN
    print("DONE: _ride_to_activity maps Run sport to AT_RUN")


@pytest.mark.mytral
def test_ride_to_activity_empty_sport_defaults_to_ride():
    # GIVEN
    ride = dict(_FULL_RIDE, sport="")

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.activity_type_key == commons.AT_RIDE
    print("DONE: _ride_to_activity defaults empty sport to AT_RIDE")


@pytest.mark.mytral
def test_ride_to_activity_sport_virtual_ride():
    # GIVEN
    ride = dict(_FULL_RIDE, sport="VirtualRide")

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.activity_type_key == commons.AT_RIDE_VIRTUAL
    print("DONE: _ride_to_activity maps VirtualRide sport to AT_RIDE_VIRTUAL")


@pytest.mark.mytral
def test_ride_to_activity_sport_walk():
    # GIVEN
    ride = dict(_FULL_RIDE, sport="Walk")

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.activity_type_key == commons.AT_WALK
    print("DONE: _ride_to_activity maps Walk sport to AT_WALK")


@pytest.mark.mytral
def test_ride_to_activity_sport_hike():
    # GIVEN
    ride = dict(_FULL_RIDE, sport="Hike")

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.activity_type_key == commons.AT_HIKE
    print("DONE: _ride_to_activity maps Hike sport to AT_HIKE")


@pytest.mark.mytral
def test_ride_to_activity_sport_weight_training():
    # GIVEN
    ride = dict(_FULL_RIDE, sport="WeightTraining")

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.activity_type_key == commons.AT_GYM
    print("DONE: _ride_to_activity maps WeightTraining sport to AT_GYM")


@pytest.mark.mytral
def test_ride_to_activity_sport_nordic_ski():
    # GIVEN
    ride = dict(_FULL_RIDE, sport="NordicSki")

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.activity_type_key == commons.AT_SKI_DP
    print("DONE: _ride_to_activity maps NordicSki sport to AT_SKI_DP")


@pytest.mark.mytral
def test_ride_to_activity_sport_stand_up_paddling():
    # GIVEN
    ride = dict(_FULL_RIDE, sport="StandUpPaddling")

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.activity_type_key == commons.AT_PADDLE
    print("DONE: _ride_to_activity maps StandUpPaddling sport to AT_PADDLE")


@pytest.mark.mytral
def test_ride_to_activity_sport_canoeing():
    # GIVEN
    ride = dict(_FULL_RIDE, sport="Canoeing")

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.activity_type_key == commons.AT_CANOEING
    print("DONE: _ride_to_activity maps Canoeing sport to AT_CANOEING")


@pytest.mark.mytral
def test_ride_to_activity_sport_other():
    # GIVEN
    ride = dict(_FULL_RIDE, sport="Other")

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.activity_type_key == commons.AT_WORKOUT
    print("DONE: _ride_to_activity maps Other sport to AT_WORKOUT")


@pytest.mark.mytral
def test_ride_to_activity_unknown_sport_defaults_to_ride():
    # GIVEN
    ride = dict(_FULL_RIDE, sport="Yoga")

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.activity_type_key == commons.AT_RIDE
    print("DONE: _ride_to_activity falls back to AT_RIDE for unknown sport")


@pytest.mark.mytral
def test_ride_to_activity_src_tracking():
    # GIVEN
    ride = dict(_FULL_RIDE)

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.src == golden_cheetah_osf.GC_OSF_SRC
    assert activity.src_key == f"{_ATHLETE_UUID}/2020_02_21_13_35_12"
    print("DONE: _ride_to_activity sets correct src and src_key")


@pytest.mark.mytral
def test_ride_to_activity_missing_date_returns_none():
    # GIVEN
    ride = {"sport": "Bike", "METRICS": _FULL_METRICS}

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is None
    print("DONE: _ride_to_activity returns None for missing date")


@pytest.mark.mytral
def test_ride_to_activity_invalid_date_returns_none():
    # GIVEN
    ride = dict(_FULL_RIDE, date="not-a-date")

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is None
    print("DONE: _ride_to_activity returns None for invalid date format")


@pytest.mark.mytral
def test_ride_to_activity_zero_metrics_no_crash():
    # GIVEN — all numeric metrics are 0 or absent
    ride = {
        "date": "2020/02/21 13:35:12 UTC",
        "sport": "Bike",
        "METRICS": {},
    }

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.distance == 0
    assert activity.hours == 0
    assert activity.minutes == 0
    assert activity.seconds == 0
    assert activity.avg_hr == 0.0
    assert activity.elevation_gain == 0
    assert activity.kcal == 0
    print("DONE: _ride_to_activity handles all-zero metrics without crash")


@pytest.mark.mytral
def test_ride_to_activity_none_metrics_no_crash():
    # GIVEN — GoldenCheetah sends None for metrics without sensor data
    ride = {
        "date": "2020/02/21 13:35:12 UTC",
        "sport": "Bike",
        "METRICS": {
            "workout_time": "3600.00000",
            "total_distance": "20.0",
            "average_hr": None,
            "max_heartrate": None,
            "average_power": None,
            "max_power": None,
            "total_kcalories": None,
        },
    }

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN — None metrics become 0.0, no exception raised
    assert activity is not None
    assert activity.avg_hr == 0.0
    assert activity.max_hr == 0.0
    assert activity.avg_watts == 0.0
    assert activity.kcal == 0
    print("DONE: _ride_to_activity handles None metric values without crash")


@pytest.mark.mytral
def test_ride_to_activity_key_generated():
    # GIVEN
    ride = _FULL_RIDE

    # WHEN
    activity = _ride_to_activity(ride, _ATHLETE_UUID)

    # THEN
    assert activity is not None
    assert activity.key != ""
    print("DONE: _ride_to_activity generates a non-empty key")


# ---------------------------------------------------------------------------
# GoldenCheetahOsfImportPlugin.import_activities
# ---------------------------------------------------------------------------


def _make_zip(athlete_uuid: str, rides: list) -> io.BytesIO:
    """Build an in-memory GoldenCheetah OSF ZIP with the given RIDES."""
    index = {
        "VERSION": "1.9",
        "ATHLETE": {"gender": "M", "yob": "1980", "id": f"{{{athlete_uuid}}}"},
        "RIDES": rides,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{{{athlete_uuid}}}.json", json.dumps(index))
    buf.seek(0)
    return buf


def _make_user_profile():
    """Return a minimal UserProfile for plugin tests."""
    return settings.UserProfile(
        user_id="test-user",
        user="test",
        email="test@example.com",
        password_enc="",
        dataset_name="lifelong",
        dataset_names=["lifelong"],
    )


@pytest.mark.mytral
def test_import_activities_returns_two_activities():
    # GIVEN
    rides = [_FULL_RIDE, dict(_FULL_RIDE, date="2020/05/03 05:31:31 UTC")]
    zip_buf = _make_zip(_ATHLETE_UUID, rides)
    plugin = GoldenCheetahOsfImportPlugin()
    user_profile = _make_user_profile()

    # WHEN — pass the BytesIO directly; ZipFile accepts file-like objects
    activities = plugin.import_activities(
        datasets={golden_cheetah_osf.GC_OSF_ZIP_PATH_KEY: zip_buf},
        user_profile=user_profile,
    )

    # THEN
    assert len(activities) == 2
    print("DONE: plugin returns one ActivityEntity per RIDES entry")


@pytest.mark.mytral
def test_import_activities_src_fields():
    # GIVEN
    rides = [_FULL_RIDE]
    zip_buf = _make_zip(_ATHLETE_UUID, rides)
    plugin = GoldenCheetahOsfImportPlugin()
    user_profile = _make_user_profile()

    # WHEN
    activities = plugin.import_activities(
        datasets={golden_cheetah_osf.GC_OSF_ZIP_PATH_KEY: zip_buf},
        user_profile=user_profile,
    )

    # THEN
    assert len(activities) == 1
    a = activities[0]
    assert a.src == golden_cheetah_osf.GC_OSF_SRC
    assert a.src_key.startswith(_ATHLETE_UUID)
    print("DONE: plugin sets correct src and src_key on imported activities")


@pytest.mark.mytral
def test_import_activities_skips_bad_dates():
    # GIVEN — one valid ride, one with bad date
    rides = [_FULL_RIDE, {"date": "", "sport": "Bike", "METRICS": {}}]
    zip_buf = _make_zip(_ATHLETE_UUID, rides)
    plugin = GoldenCheetahOsfImportPlugin()
    user_profile = _make_user_profile()

    # WHEN
    activities = plugin.import_activities(
        datasets={golden_cheetah_osf.GC_OSF_ZIP_PATH_KEY: zip_buf},
        user_profile=user_profile,
    )

    # THEN — only the valid ride is returned
    assert len(activities) == 1
    print("DONE: plugin skips rides with missing/invalid dates")


@pytest.mark.mytral
def test_import_activities_empty_rides():
    # GIVEN
    zip_buf = _make_zip(_ATHLETE_UUID, [])
    plugin = GoldenCheetahOsfImportPlugin()
    user_profile = _make_user_profile()

    # WHEN
    activities = plugin.import_activities(
        datasets={golden_cheetah_osf.GC_OSF_ZIP_PATH_KEY: zip_buf},
        user_profile=user_profile,
    )

    # THEN
    assert activities == []
    print("DONE: plugin handles empty RIDES array")


# ---------------------------------------------------------------------------
# Integration tests — real athlete ZIP from tests/data/import/golden-cheetah/
# ---------------------------------------------------------------------------

_REAL_ZIP = (
    pathlib.Path(__file__).parent
    / "data"
    / "import"
    / "golden-cheetah"
    / "000db8a2-a1f6-42bd-8228-fdfae659f476.zip"
)
_REAL_UUID = "000db8a2-a1f6-42bd-8228-fdfae659f476"


def _import_real_zip():
    """Run the plugin against the real ZIP and return the activity list."""
    plugin = GoldenCheetahOsfImportPlugin()
    user_profile = _make_user_profile()
    return plugin.import_activities(
        datasets={golden_cheetah_osf.GC_OSF_ZIP_PATH_KEY: _REAL_ZIP},
        user_profile=user_profile,
    )


@pytest.mark.mytral
def test_real_archive_total_count():
    # GIVEN
    # real ZIP: 26 Bike + 30 VirtualRide = 56 rides

    # WHEN
    activities = _import_real_zip()

    # THEN
    assert len(activities) == 56
    print("DONE: real archive imports exactly 56 activities")


@pytest.mark.mytral
def test_real_archive_first_ride_date_and_sport():
    # GIVEN / WHEN
    activities = _import_real_zip()

    # THEN — ride 0: 2018/07/07 16:18:38 UTC, Bike
    a = activities[0]
    assert a.when_year == 2018
    assert a.when_month == 7
    assert a.when_day == 7
    assert a.when_hour == 16
    assert a.when_minute == 18
    assert a.when_second == 38
    assert a.activity_type_key == commons.AT_RIDE
    print("DONE: real archive ride 0 has correct date and sport")


@pytest.mark.mytral
def test_real_archive_first_ride_duration_and_distance():
    # GIVEN / WHEN
    activities = _import_real_zip()

    # THEN — ride 0: 3244s = 0h 54m 4s, 19.3664 km = 19366 m
    a = activities[0]
    assert a.hours == 0
    assert a.minutes == 54
    assert a.seconds == 4
    assert a.distance == 19366
    print("DONE: real archive ride 0 has correct duration and distance")


@pytest.mark.mytral
def test_real_archive_first_ride_metrics():
    # GIVEN / WHEN
    activities = _import_real_zip()

    # THEN — ride 0 sensor fields from average_hr list, max_heartrate scalar, etc.
    a = activities[0]
    assert abs(a.avg_hr - 129.52081) < 1e-3
    assert a.max_hr == 152.0
    assert a.avg_watts == 0.0  # no power meter
    assert a.max_watts == 0.0
    assert abs(a.avg_cadence - 65.49882) < 1e-3
    assert a.max_cadence == 99.0
    assert a.max_speed == 42.48
    assert a.elevation_gain == 179  # int(179.37670)
    assert a.kcal == 674  # int(674.29523)
    print("DONE: real archive ride 0 has correct sensor metrics")


@pytest.mark.mytral
def test_real_archive_first_ride_src_tracking():
    # GIVEN / WHEN
    activities = _import_real_zip()

    # THEN — src and src_key uniquely identify the ride within the dataset
    a = activities[0]
    assert a.src == golden_cheetah_osf.GC_OSF_SRC
    assert a.src_key == f"{_REAL_UUID}/2018_07_07_16_18_38"
    print("DONE: real archive ride 0 has correct src and src_key")


@pytest.mark.mytral
def test_real_archive_first_ride_name():
    # GIVEN / WHEN
    activities = _import_real_zip()

    # THEN
    a = activities[0]
    assert a.name == "GC Bike 2018-07-07"
    print("DONE: real archive ride 0 has correct generated name")


@pytest.mark.mytral
def test_real_archive_ride_with_no_sensor_data():
    # GIVEN / WHEN
    activities = _import_real_zip()

    # THEN — ride 7: Bike, 2018/07/21, no HR / kcal / cadence sensor
    a = activities[7]
    assert a.when_year == 2018
    assert a.when_month == 7
    assert a.when_day == 21
    assert a.hours == 1
    assert a.minutes == 21
    assert a.seconds == 33
    assert a.distance == 33510  # int(33.51010 * 1000)
    assert a.avg_hr == 0.0
    assert a.max_hr == 0.0
    assert a.avg_watts == 0.0
    assert a.avg_cadence == 0.0
    assert a.kcal == 0
    print("DONE: real archive ride 7 handles all-None sensor metrics as zeros")


@pytest.mark.mytral
def test_real_archive_first_ride_with_power():
    # GIVEN / WHEN
    activities = _import_real_zip()

    # THEN — ride 12: first Bike ride that has power data
    a = activities[12]
    assert a.when_year == 2018
    assert a.when_month == 7
    assert a.when_day == 27
    assert a.hours == 0
    assert a.minutes == 13
    assert a.seconds == 56
    assert a.distance == 4560  # int(4.56040 * 1000)
    assert abs(a.avg_watts - 107.01794) < 1e-3
    assert a.max_watts == 414.0
    assert abs(a.avg_hr - 122.69378) < 1e-3
    assert a.max_hr == 151.0
    assert a.elevation_gain == 25  # int(25.20000)
    assert a.kcal == 161  # int(161.72326)
    assert a.src_key == f"{_REAL_UUID}/2018_07_27_17_15_38"
    print("DONE: real archive ride 12 maps power metrics correctly")


@pytest.mark.mytral
def test_real_archive_virtual_ride_sport_mapping():
    # GIVEN / WHEN
    activities = _import_real_zip()

    # THEN — ride 26: first VirtualRide (2018/08/27), maps to AT_RIDE_VIRTUAL
    a = activities[26]
    assert a.when_year == 2018
    assert a.when_month == 8
    assert a.when_day == 27
    assert a.activity_type_key == commons.AT_RIDE_VIRTUAL
    assert a.src_key == f"{_REAL_UUID}/2018_08_27_16_40_30"
    assert abs(a.avg_watts - 152.72198) < 1e-3
    print("DONE: real archive VirtualRide maps to AT_RIDE_VIRTUAL")


@pytest.mark.mytral
def test_real_archive_all_keys_non_empty():
    # GIVEN / WHEN
    activities = _import_real_zip()

    # THEN — every returned activity has a non-empty key
    for i, a in enumerate(activities):
        assert a.key, f"ride {i} has empty key"
    print("DONE: real archive all 56 activities have non-empty keys")


@pytest.mark.mytral
def test_real_archive_all_src_keys_unique():
    # GIVEN / WHEN
    activities = _import_real_zip()

    # THEN — src_key is unique per activity (no duplicate timestamps)
    src_keys = [a.src_key for a in activities]
    assert len(src_keys) == len(set(src_keys))
    print("DONE: real archive all 56 src_keys are unique")


# ---------------------------------------------------------------------------
# Task-level tests — worker function and full task execution
# ---------------------------------------------------------------------------


class _FakeDataset:
    """Minimal in-memory dataset for task integration tests."""

    def __init__(self) -> None:
        self.activities: dict[str, entities.ActivityEntity] = {}

    def profile(self, user_id: str) -> settings.UserProfile:
        return settings.UserProfile(
            user_id=user_id,
            user="test",
            email="test@example.com",
            password_enc="",
            dataset_name="lifelong",
            dataset_names=["lifelong"],
        )

    def create_activities(self, user_id, dataset_name, entity_list) -> None:
        for a in entity_list:
            self.activities[a.key] = a

    def update_activity(self, user_id, dataset_name, entity) -> entities.ActivityEntity:
        self.activities[entity.key] = entity
        return entity

    def update_activities(self, user_id, dataset_name, activities) -> None:
        for a in activities:
            self.activities[a.key] = a

    def list_activities(self, user_id, dataset_name=None, year=None) -> list:
        if year is not None:
            return [
                a
                for a in self.activities.values()
                if getattr(a, "when_year", 0) == year
            ]
        return list(self.activities.values())


class _FakeLogger:
    def info(self, *a, **kw) -> None:
        pass

    def warning(self, *a, **kw) -> None:
        pass


class _SyncBulldozer:
    """Runs Bulldozer job functions synchronously in-process (no subprocess)."""

    def __init__(self, usr_task_dir, logger=None, subtask_key="sync", **kwargs):
        self._task_dir = pathlib.Path(usr_task_dir) / "subtasks" / subtask_key

    def make_sandbox(self) -> list[pathlib.Path]:
        n_slots = max(1, (os.cpu_count() or 1) // 2)
        job_dirs = []
        for i in range(n_slots):
            job_dir = self._task_dir / f"job-{i}"
            (job_dir / "input").mkdir(parents=True, exist_ok=True)
            (job_dir / "work").mkdir(parents=True, exist_ok=True)
            (job_dir / "output").mkdir(parents=True, exist_ok=True)
            job_dirs.append(job_dir)
        return job_dirs

    def run(self, *, job_dirs=None, job_function=None) -> None:
        for i, job_dir in enumerate(job_dirs or []):
            if (job_dir / "input" / "payload.json").exists():
                job_function(i, job_dir)


def _make_task_entity(
    zip_path: pathlib.Path, on_conflict: str = "skip"
) -> tasks.TaskEntity:
    return tasks.TaskEntity(
        key="test-task-gc",
        user_id="test_user",
        task_type=golden_cheetah_osf_import.GoldenCheetahOsfImportTask.TASK_TYPE,
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
            "dataset_name": "lifelong",
            golden_cheetah_osf_import.GoldenCheetahOsfImportTask.ZIP_PATH_KEY: str(
                zip_path
            ),
            "on_conflict": on_conflict,
        },
        is_cancelled=False,
    )


@pytest.mark.mytral
def test_gc_csv_blob_job_impl_creates_csv_and_parquet_blobs(tmp_path):
    """_gc_csv_blob_job_impl stores CSV recording blob and Parquet blob per activity."""
    # GIVEN — import one activity from the real ZIP
    plugin = GoldenCheetahOsfImportPlugin()
    user_profile = _make_user_profile()
    activities = plugin.import_activities(
        datasets={golden_cheetah_osf.GC_OSF_ZIP_PATH_KEY: _REAL_ZIP},
        user_profile=user_profile,
    )
    activity = activities[0]  # 2018-07-07 16:18:38 UTC

    job_dir = tmp_path / "job-0"
    (job_dir / "input").mkdir(parents=True)
    (job_dir / "work").mkdir(parents=True)

    with open(job_dir / "input" / "payload.json", "w") as fh:
        json.dump(
            {
                "user_id": "test_user",
                "zip_path": str(_REAL_ZIP),
                "now_iso": "2026-01-01T00:00:00+00:00",
                "activities": [activity.to_dict()],
            },
            fh,
        )

    # WHEN
    _gc_csv_blob_job_impl(0, job_dir)

    # THEN — output payload exists and contains one updated activity
    output_file = job_dir / "output" / "payload.json"
    assert output_file.exists(), "worker did not produce output/payload.json"

    with open(output_file) as fh:
        result = json.load(fh)

    updated = result["activities"]
    assert len(updated) == 1, f"expected 1 updated activity, got {len(updated)}"

    d = updated[0]

    # recorded_blob_keys must contain exactly one "UUID.csv" entry
    blob_keys = d.get("recorded_blob_keys", [])
    assert len(blob_keys) == 1, f"expected 1 recorded_blob_key, got {blob_keys}"
    assert blob_keys[0].endswith(".csv"), f"blob key must end with .csv: {blob_keys[0]}"

    csv_uuid = blob_keys[0].removesuffix(".csv")
    assert csv_uuid, "CSV blob UUID must be non-empty"

    # recorded_parquet_keys maps CSV recording UUID → Parquet UUID
    pq_keys = d.get("recorded_parquet_keys", {})
    assert csv_uuid in pq_keys, (
        f"CSV UUID {csv_uuid!r} not found in recorded_parquet_keys {pq_keys}"
    )
    pq_uuid = pq_keys[csv_uuid]
    assert pq_uuid, "Parquet blob UUID must be non-empty"
    assert pq_uuid != csv_uuid, "Parquet UUID must differ from CSV UUID"

    # both blobs are readable from the sandbox blobstore
    sandbox_cfg = mytral_config.MytralConfig(persistence_data_dir=job_dir / "work")
    sandbox_store = FilesystemBlobStore(
        base_dir=sandbox_cfg.user_data_dir,
        blobs_subdir="blobs",
    )

    csv_stream = sandbox_store.open_blob("test_user", csv_uuid)
    csv_content = csv_stream.read()
    csv_stream.close()
    assert len(csv_content) > 0, "CSV blob content is empty in sandbox"
    assert b"secs" in csv_content or b"km" in csv_content, "CSV blob missing header"

    pq_stream = sandbox_store.open_blob("test_user", pq_uuid)
    pq_content = pq_stream.read()
    pq_stream.close()
    assert pq_content[:4] == b"PAR1", f"Parquet magic bytes wrong: {pq_content[:4]}"

    print(
        f"DONE: worker created CSV blob {csv_uuid[:8]}… and Parquet blob {pq_uuid[:8]}…"
    )


@pytest.mark.mytral
def test_gc_import_task_creates_blobs_in_blobstore(tmp_path, monkeypatch):
    """Full GoldenCheetahOsfImportTask creates CSV and Parquet blobs in blobstore."""
    # GIVEN
    app_config = mytral_config.MytralConfig(persistence_data_dir=tmp_path)
    blobstore = FilesystemBlobStore(
        base_dir=app_config.user_data_dir,
        blobs_subdir="blobs",
    )
    dataset = _FakeDataset()

    monkeypatch.setattr(
        golden_cheetah_osf_import.bulldozer, "SubtaskBulldozer", _SyncBulldozer
    )

    task_entity = _make_task_entity(_REAL_ZIP)
    task = golden_cheetah_osf_import.GoldenCheetahOsfImportTask(
        task_entity=task_entity,
        logger=_FakeLogger(),
        log_callback=None,
        config=app_config,
        dataset=dataset,
        blobstore=blobstore,
    )

    # WHEN
    task.execute()

    # THEN — all 56 activities imported
    assert len(dataset.activities) == 56
    assert task_entity.progress == 100

    # THEN — activities with matching CSVs have recorded_blob_keys populated
    activities_with_blobs = [
        a for a in dataset.activities.values() if a.recorded_blob_keys
    ]
    assert len(activities_with_blobs) > 0, "no activities have recorded_blob_keys set"

    # verify one activity in detail: first ride has a CSV in the archive
    first = next(
        a
        for a in dataset.activities.values()
        if a.when_year == 2018 and a.when_month == 7 and a.when_day == 7
    )
    assert len(first.recorded_blob_keys) == 1
    assert first.recorded_blob_keys[0].endswith(".csv")

    csv_uuid = first.recorded_blob_keys[0].removesuffix(".csv")
    assert csv_uuid in first.recorded_parquet_keys
    pq_uuid = first.recorded_parquet_keys[csv_uuid]
    assert pq_uuid

    # both blobs exist in the main blobstore and are readable
    csv_stream = blobstore.open_blob("test_user", csv_uuid)
    csv_content = csv_stream.read()
    csv_stream.close()
    assert len(csv_content) > 0, "CSV blob content is empty"
    assert b"secs" in csv_content or b"km" in csv_content, "CSV blob missing header"

    pq_stream = blobstore.open_blob("test_user", pq_uuid)
    pq_content = pq_stream.read()
    pq_stream.close()
    assert len(pq_content) > 0, "Parquet blob content is empty"
    # Parquet files start with the magic bytes PAR1
    assert pq_content[:4] == b"PAR1", f"Parquet magic bytes wrong: {pq_content[:4]}"

    print(f"DONE: task imported 56 activities, {len(activities_with_blobs)} with blobs")
