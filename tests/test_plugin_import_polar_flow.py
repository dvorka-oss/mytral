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

import json
import pathlib

import pytest

from mytral import commons
from mytral import config
from mytral import plugins
from mytral.integrations import icommons
from mytral.integrations import polar_flow
from mytral.integrations import polar_flow_export
from tests import _given

# a representative Polar AccessLink v3 exercise summary
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
def test_gdpr_export_session_import(tmp_path: pathlib.Path, monkeypatch):
    """A GDPR export training session parses and maps to an ActivityEntity."""
    #
    # GIVEN
    #
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    session = {
        "name": "Morning ride",
        "exercises": [
            {
                "startTime": "2022-03-10T17:15:00.000",
                "duration": "PT0H45M0S",
                "distance": 15000.0,
                "kiloCalories": 400,
                "heartRate": {"average": 130, "maximum": 160},
                "sport": "CYCLING",
                "detailedSportInfo": "ROAD_CYCLING",
            }
        ],
    }
    (export_dir / "training-session-2022-03-10.json").write_text(
        json.dumps(session), encoding="utf-8"
    )

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
    summaries = polar_flow_export.parse_export(export_dir)
    activities = plugin.import_activities(
        datasets={plugin.USE_TYPE_POLAR_FLOW_LIST: summaries},
        user_profile=user_profile,
    )

    #
    # THEN
    #
    assert len(summaries) == 1
    assert len(activities) == 1
    activity = activities[0]
    assert activity.when_year == 2022
    assert activity.when_month == 3
    assert (activity.hours, activity.minutes, activity.seconds) == (0, 45, 0)
    assert activity.distance == 15000
    assert activity.kcal == 400
    assert activity.activity_type_key == commons.AT_RIDE
    assert activity.src == polar_flow.SRC_POLAR_FLOW
    assert activity.src_key == "20220310171500"
    print(
        "DONE: GDPR export session imported "
        f"(type={activity.activity_type_key}, src_key={activity.src_key})"
    )


@pytest.mark.mytral
def test_activity_type_mapping():
    """polar_flow_activity_type maps known sports and falls back for unknown ones."""
    #
    # GIVEN / WHEN / THEN
    #
    assert icommons.polar_flow_activity_type("RUNNING", []) == commons.AT_RUN
    assert (
        icommons.polar_flow_activity_type("Trail_Running", []) == commons.AT_RUN_TRAIL
    )
    assert (
        icommons.polar_flow_activity_type("MOUNTAIN_BIKING", [])
        == commons.AT_RIDE_MOUNTAIN
    )
    # unknown sport falls back to the default
    assert (
        icommons.polar_flow_activity_type("QUIDDITCH", [])
        == icommons.POLAR_FLOW_DEFAULT_AT
    )
    # a value that already matches a valid user activity type wins as-is
    assert icommons.polar_flow_activity_type("custom_x", ["custom_x"]) == "custom_x"
    print("DONE: activity-type mapping resolves known sports and falls back")
