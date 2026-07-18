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

"""Tests for the Polar Flow (AccessLink API + GDPR export) import plugin."""

import os
import pathlib
import zipfile

import pytest

from mytral import commons
from mytral import config
from mytral import plugins
from mytral.integrations import icommons
from mytral.integrations import polar_flow
from mytral.integrations import polar_flow_export
from tests import _given

# opt-in real-archive test: point this at a real Polar "Download your data" ZIP to
# exercise the full parser against production data; skipped when unset/missing
_REAL_EXPORT_ZIP = os.environ.get("MYTRAL_POLAR_EXPORT_TEST_ZIP", "")
_REAL_EXPORT_AVAILABLE = (
    bool(_REAL_EXPORT_ZIP) and pathlib.Path(_REAL_EXPORT_ZIP).is_file()
)

# committed real-shape GDPR export fixtures (Polar "Download your data" format)
_EXPORT_FIXTURES = (
    pathlib.Path(__file__).parent / "data" / "import" / "polar-flow-export"
)

# a representative Polar AccessLink v3 exercise summary (API channel shape)
_SAMPLE_EXERCISE = {
    "id": 1937529874,
    "start-time": "2023-05-20T08:30:00",
    "duration": "PT1H5M30S",
    "distance": 12000.5,
    "calories": 720,
    "heart-rate": {"average": 145, "maximum": 176},
    "sport": "RUNNING",
    "detailed-sport-info": "TRAIL_RUNNING",
    "has-route": True,
}


def _summary_by_src_key(summaries: list[dict], src_key: str) -> dict:
    """Return the parsed summary whose id matches *src_key* (test helper)."""
    for summary in summaries:
        if summary["id"] == src_key:
            return summary
    raise AssertionError(f"no summary with id {src_key} in {len(summaries)} summaries")


@pytest.mark.mytral
def test_raw_exercise_import(tmp_path: pathlib.Path, monkeypatch):
    """import_activity maps a Polar exercise summary to a MyTraL ActivityEntity."""
    #
    # GIVEN
    #
    _, user_ds, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_polar_flow_user",
    )
    # point the plugin at the test dataset (activity types + key generation)
    monkeypatch.setattr(polar_flow, "app_user_ds", user_ds)
    plugin = plugins.registry.get_plugin(polar_flow.PolarFlowActivityImportPlugin.NAME)

    #
    # WHEN
    #
    activity = plugin.import_activity(
        dataset_item=_SAMPLE_EXERCISE, user_profile=user_profile
    )

    #
    # THEN
    #
    assert activity.when_year == 2023
    assert activity.when_month == 5
    assert activity.when_day == 20
    assert activity.when_hour == 8
    assert activity.when_minute == 30
    assert (activity.hours, activity.minutes, activity.seconds) == (1, 5, 30)
    assert activity.distance == 12000
    assert activity.kcal == 720
    assert activity.avg_hr == 145
    assert activity.max_hr == 176
    assert activity.activity_type_key == commons.AT_RUN_TRAIL
    assert activity.src == polar_flow.SRC_POLAR_FLOW
    assert activity.src_key == "1937529874"
    assert activity.src_url.endswith("1937529874")
    print(
        "DONE: raw exercise import maps summary to entity "
        f"(type={activity.activity_type_key}, src_key={activity.src_key})"
    )


@pytest.mark.mytral
def test_gdpr_export_parses_real_schema():
    """The parser reads the real GDPR schema (dict sport, millis, meters, HR)."""
    #
    # GIVEN / WHEN
    #
    summaries = polar_flow_export.parse_export(_EXPORT_FIXTURES)

    #
    # THEN
    #
    # the non-training "activity-*.json" file is ignored; 4 sessions remain
    assert len(summaries) == 4

    ride = _summary_by_src_key(summaries, "8067285121")
    # durationMillis 9178000 -> ISO PT2H32M58S; distanceMeters -> int metres
    assert ride["duration"] == "PT2H32M58S"
    assert ride["distance"] == 60160
    assert ride["calories"] == 1466
    # HR is carried at the SESSION level (hrAvg/hrMax), not on the exercise
    assert ride["heart-rate"] == {"average": 141, "maximum": 174}
    # elevation gain comes from the exercise ascentMeters
    assert ride["elevation-gain"] == 395
    # the {"id": "38"} sport dict resolves to a name string, never a dict
    assert ride["detailed-sport-info"] == "road_biking"
    assert not isinstance(ride["sport"], dict)
    print("DONE: real GDPR schema parsed (millis/meters/session-HR/dict-sport)")


@pytest.mark.mytral
def test_gdpr_export_directory_import(tmp_path: pathlib.Path, monkeypatch):
    """Every fixture session maps to an ActivityEntity with correct fields/type."""
    #
    # GIVEN
    #
    _, user_ds, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_polar_flow_gdpr_user",
    )
    monkeypatch.setattr(polar_flow, "app_user_ds", user_ds)
    plugin = plugins.registry.get_plugin(
        polar_flow.PolarFlowActivitiesImportPlugin.NAME
    )

    #
    # WHEN
    #
    summaries = polar_flow_export.parse_export(_EXPORT_FIXTURES)
    activities = plugin.import_activities(
        datasets={plugin.USE_TYPE_POLAR_FLOW_LIST: summaries},
        user_profile=user_profile,
    )
    by_key = {a.src_key: a for a in activities}

    #
    # THEN
    #
    assert len(activities) == 4

    # road ride (sport id 38 -> road_biking -> ride)
    ride = by_key["8067285121"]
    assert ride.when_year == 2025 and ride.when_month == 1 and ride.when_day == 19
    assert (ride.hours, ride.minutes, ride.seconds) == (2, 32, 58)
    assert ride.distance == 60160
    assert ride.kcal == 1466
    assert ride.avg_hr == 141 and ride.max_hr == 174
    assert ride.elevation_gain == 395
    assert ride.activity_type_key == commons.AT_RIDE

    # indoor strength (sport id 15 -> strength_training -> gym), no distance/HR
    strength = by_key["9000000001"]
    assert (strength.hours, strength.minutes, strength.seconds) == (0, 45, 0)
    assert strength.distance == 0
    assert strength.avg_hr == 0 and strength.max_hr == 0
    assert strength.activity_type_key == commons.AT_GYM

    # run stored as a session with no exercises array (fallback branch)
    run = by_key["5000000001"]
    assert (run.hours, run.minutes, run.seconds) == (0, 30, 30)
    assert run.distance == 5141
    assert run.elevation_gain == 30
    assert run.activity_type_key == commons.AT_RUN

    print(f"DONE: {len(activities)} GDPR sessions imported with correct fields")


@pytest.mark.mytral
def test_gdpr_export_zip_import(tmp_path: pathlib.Path):
    """Parsing a ZIP yields the same sessions as parsing the extracted directory."""
    #
    # GIVEN - zip the committed fixture session files
    #
    zip_path = tmp_path / "polar-user-data-export.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for json_file in sorted(_EXPORT_FIXTURES.glob("*.json")):
            archive.write(json_file, arcname=json_file.name)

    #
    # WHEN
    #
    from_zip = polar_flow_export.parse_export(zip_path)
    from_dir = polar_flow_export.parse_export(_EXPORT_FIXTURES)

    #
    # THEN
    #
    assert len(from_zip) == 4
    assert {s["id"] for s in from_zip} == {s["id"] for s in from_dir}
    print("DONE: ZIP and directory parsing agree (4 sessions each)")


@pytest.mark.mytral
def test_unmapped_sport_id_falls_back_to_default(tmp_path: pathlib.Path, monkeypatch):
    """An unknown Polar sport id imports safely as the default activity type."""
    #
    # GIVEN
    #
    _, user_ds, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_polar_flow_unmapped_user",
    )
    monkeypatch.setattr(polar_flow, "app_user_ds", user_ds)
    plugin = plugins.registry.get_plugin(
        polar_flow.PolarFlowActivitiesImportPlugin.NAME
    )

    #
    # WHEN
    #
    summaries = polar_flow_export.parse_export(_EXPORT_FIXTURES)
    activities = plugin.import_activities(
        datasets={plugin.USE_TYPE_POLAR_FLOW_LIST: summaries},
        user_profile=user_profile,
    )
    unknown = {a.src_key: a for a in activities}["9000000002"]

    #
    # THEN
    #
    # unknown sport id 777 must not crash and must use the safe default
    assert unknown.activity_type_key == icommons.POLAR_FLOW_DEFAULT_AT
    # the rest of the data is still imported
    assert unknown.distance == 8000
    assert unknown.kcal == 300
    assert unknown.avg_hr == 120
    print("DONE: unmapped sport id 777 imported as default activity type, data intact")


@pytest.mark.mytral
def test_dict_sport_does_not_crash_import(tmp_path: pathlib.Path, monkeypatch):
    """Regression: a raw {"id": ...} sport dict must not raise AttributeError.

    Reproduces the original crash: ``'dict' object has no attribute 'strip'`` when a
    GDPR-shape sport dict reached ``polar_flow_activity_type``.
    """
    #
    # GIVEN
    #
    _, user_ds, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_polar_flow_dictsport_user",
    )
    monkeypatch.setattr(polar_flow, "app_user_ds", user_ds)
    plugin = plugins.registry.get_plugin(polar_flow.PolarFlowActivityImportPlugin.NAME)
    dict_sport_summary = {
        "id": "42",
        "start-time": "2025-05-01T06:00:00",
        "duration": "PT1H0M0S",
        "distance": 10000,
        "calories": 500,
        "heart-rate": {"average": 130, "maximum": 160},
        "sport": {"id": "38"},
        "detailed-sport-info": {"id": "38"},
    }

    #
    # WHEN
    #
    activity = plugin.import_activity(
        dataset_item=dict_sport_summary, user_profile=user_profile
    )

    #
    # THEN
    #
    assert activity.activity_type_key == commons.AT_RIDE
    assert activity.distance == 10000
    print("DONE: dict-shaped sport imports without crashing (id 38 -> ride)")


@pytest.mark.mytral
def test_sport_name_normalization():
    """polar_flow_sport_name resolves every Polar sport shape to a canonical name."""
    #
    # GIVEN / WHEN / THEN
    #
    # GDPR export dict shape
    assert icommons.polar_flow_sport_name({"id": "38"}) == "road_biking"
    assert icommons.polar_flow_sport_name({"id": "1"}) == "running"
    # bare numeric id
    assert icommons.polar_flow_sport_name("5") == "mountain_biking"
    # name strings (API shape), any case
    assert icommons.polar_flow_sport_name("RUNNING") == "running"
    assert icommons.polar_flow_sport_name("Trail_Running") == "trail_running"
    # unresolvable inputs
    assert icommons.polar_flow_sport_name("777") == ""
    assert icommons.polar_flow_sport_name({"id": "777"}) == ""
    assert icommons.polar_flow_sport_name(None) == ""
    assert icommons.polar_flow_sport_name({}) == ""
    print("DONE: sport-name normalization handles dict/id/name/None")


@pytest.mark.mytral
def test_activity_type_mapping():
    """polar_flow_activity_type maps names, ids and dicts, and falls back safely."""
    #
    # GIVEN / WHEN / THEN
    #
    # name strings
    assert icommons.polar_flow_activity_type("RUNNING", []) == commons.AT_RUN
    assert (
        icommons.polar_flow_activity_type("Trail_Running", []) == commons.AT_RUN_TRAIL
    )
    # numeric id and dict shapes (GDPR export)
    assert icommons.polar_flow_activity_type("38", []) == commons.AT_RIDE
    assert (
        icommons.polar_flow_activity_type({"id": "5"}, []) == commons.AT_RIDE_MOUNTAIN
    )
    # unknown sport (string or id) falls back to the default
    assert (
        icommons.polar_flow_activity_type("QUIDDITCH", [])
        == icommons.POLAR_FLOW_DEFAULT_AT
    )
    assert (
        icommons.polar_flow_activity_type({"id": "777"}, [])
        == icommons.POLAR_FLOW_DEFAULT_AT
    )
    # a value that already matches a valid user activity type wins as-is
    assert icommons.polar_flow_activity_type("custom_x", ["custom_x"]) == "custom_x"
    print("DONE: activity-type mapping resolves names, ids and dicts, falls back")


@pytest.mark.mytral
def test_parallel_parse_matches_serial(tmp_path: pathlib.Path):
    """Parallel ZIP parsing yields exactly the same summaries as serial parsing.

    Built from many copies of the committed fixtures to cross the parallel
    threshold, so the multiprocessing path is actually exercised in CI.
    """
    #
    # GIVEN - a ZIP with enough sessions to trigger the parallel path
    #
    copies = polar_flow_export._PARALLEL_MIN_FILES + 20
    session_files = sorted(_EXPORT_FIXTURES.glob("training-session_*.json"))
    zip_path = tmp_path / "big-export.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for i in range(copies):
            src = session_files[i % len(session_files)]
            archive.writestr(
                f"training-session_copy{i:04d}_{src.name}", src.read_bytes()
            )

    #
    # WHEN
    #
    serial = polar_flow_export.parse_export(zip_path, workers=1)
    parallel = polar_flow_export.parse_export(zip_path, workers=4)

    #
    # THEN
    #
    assert len(serial) == len(parallel) == copies

    def sorted_keys(summaries):
        return sorted(s["id"] + s["start-time"] for s in summaries)

    assert sorted_keys(serial) == sorted_keys(parallel)
    print(f"DONE: parallel parse of {copies} sessions matches serial exactly")


@pytest.mark.mytral
@pytest.mark.skipif(
    not _REAL_EXPORT_AVAILABLE,
    reason="set MYTRAL_POLAR_EXPORT_TEST_ZIP to a real Polar export ZIP to run",
)
def test_real_export_archive_imports_cleanly(tmp_path: pathlib.Path, monkeypatch):
    """A real Polar export ZIP parses and maps end-to-end without any crash."""
    #
    # GIVEN
    #
    _, user_ds, user_profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id="test_polar_flow_real_user",
    )
    monkeypatch.setattr(polar_flow, "app_user_ds", user_ds)
    plugin = plugins.registry.get_plugin(
        polar_flow.PolarFlowActivitiesImportPlugin.NAME
    )

    #
    # WHEN
    #
    summaries = polar_flow_export.parse_export(_REAL_EXPORT_ZIP)
    activities = plugin.import_activities(
        datasets={plugin.USE_TYPE_POLAR_FLOW_LIST: summaries},
        user_profile=user_profile,
    )

    #
    # THEN
    #
    assert len(summaries) > 0
    assert len(activities) == len(summaries)
    # no dict-typed sport leaks through, every activity gets a type and a start
    for activity in activities:
        assert activity.activity_type_key
        assert activity.when_year > 0
    print(f"DONE: real export archive imported {len(activities)} activities cleanly")


@pytest.mark.mytral
def test_millis_to_iso_duration():
    """durationMillis converts to an ISO-8601 duration parseable back to h/m/s."""
    #
    # GIVEN / WHEN / THEN
    #
    assert polar_flow_export._millis_to_iso_duration(9178000) == "PT2H32M58S"
    assert polar_flow_export._millis_to_iso_duration(2700000) == "PT0H45M0S"
    assert polar_flow_export._millis_to_iso_duration(0) == ""
    assert polar_flow_export._millis_to_iso_duration(None) == ""
    # round-trips through the ISO parser used by import_activity
    assert polar_flow.parse_iso_duration("PT2H32M58S") == (2, 32, 58)
    print("DONE: millis->ISO duration converts and round-trips")
