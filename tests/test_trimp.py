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
import datetime
import math
from types import SimpleNamespace

import flask
import pytest

from mytral import charts
from mytral import settings
from mytral.backends import entities
from mytral.blueprints import trimp_uri_space


def _activity(
    year: int,
    month: int,
    day: int,
    duration_seconds: int,
    avg_hr: int,
    max_hr: int,
    min_hr: int = 0,
    key: str = "",
) -> entities.ActivityEntity:
    return entities.ActivityEntity(
        key=key,
        when_year=year,
        when_month=month,
        when_day=day,
        duration_seconds=duration_seconds,
        avg_hr=avg_hr,
        max_hr=max_hr,
        min_hr=min_hr,
    )


@pytest.mark.mytral
def test_calc_activity_trimp_gender_and_none_fallback():
    # GIVEN
    activity = _activity(2026, 6, 1, duration_seconds=3600, avg_hr=150, max_hr=190)
    hrr = (150.0 - 60.0) / (190.0 - 60.0)
    expected_man = 60.0 * hrr * (0.65 * math.exp(1.92 * hrr))
    expected_woman = 60.0 * hrr * (0.86 * math.exp(1.67 * hrr))

    profile = settings.UserProfile(
        user_id="u1",
        user="user",
        email="user@example.com",
        password_enc="x",
        dataset_name="main",
        dataset_names=["main"],
        gender=None,
        age=40,
    )

    # WHEN
    trimp_man = trimp_uri_space._calc_activity_trimp(
        activity=activity,
        hr_rest=60.0,
        hr_max=190.0,
        is_man=True,
    )
    trimp_woman = trimp_uri_space._calc_activity_trimp(
        activity=activity,
        hr_rest=60.0,
        hr_max=190.0,
        is_man=False,
    )
    rows_none_gender = trimp_uri_space._calc_daily_trimp_rows(
        activities=[activity],
        user_profile=profile,
        resting_hr_fallback=60.0,
        profile_max_hr_fallback=190.0,
    )

    # THEN
    assert trimp_man == pytest.approx(expected_man)
    assert trimp_woman == pytest.approx(expected_woman)
    assert rows_none_gender[0]["trimp"] == pytest.approx(expected_man)
    print("DONE: gender-specific TRIMP and undefined gender fallback to man work")


@pytest.mark.mytral
def test_calc_activity_trimp_uses_fractional_minutes():
    # GIVEN
    activity = _activity(2026, 6, 1, duration_seconds=90, avg_hr=140, max_hr=180)
    hrr = (140.0 - 60.0) / (180.0 - 60.0)
    expected = 1.5 * hrr * (0.65 * math.exp(1.92 * hrr))

    # WHEN
    trimp = trimp_uri_space._calc_activity_trimp(
        activity=activity,
        hr_rest=60.0,
        hr_max=180.0,
        is_man=True,
    )

    # THEN
    assert trimp == pytest.approx(expected)
    print("DONE: duration_seconds are converted to fractional minutes")


@pytest.mark.mytral
def test_daily_trimp_rows_aggregate_gaps_and_ema():
    # GIVEN
    profile = settings.UserProfile(
        user_id="u1",
        user="user",
        email="user@example.com",
        password_enc="x",
        dataset_name="main",
        dataset_names=["main"],
        gender=True,
        age=40,
    )
    activities = [
        _activity(2026, 6, 1, duration_seconds=3600, avg_hr=150, max_hr=190, min_hr=55),
        _activity(
            2026,
            6,
            1,
            duration_seconds=1800,
            avg_hr=145,
            max_hr=188,
            min_hr=55,
            key="b",
        ),
        _activity(2026, 6, 3, duration_seconds=3600, avg_hr=155, max_hr=192, min_hr=56),
    ]

    # WHEN
    rows = trimp_uri_space._calc_daily_trimp_rows(
        activities=activities,
        user_profile=profile,
        resting_hr_fallback=60.0,
        profile_max_hr_fallback=190.0,
    )

    # THEN
    assert len(rows) == 3
    assert rows[1]["date"].isoformat() == "2026-06-02"
    assert rows[1]["trimp"] == pytest.approx(0.0)

    day1 = rows[0]["trimp"]
    expected_day2_atrimp = day1 + ((0.0 - day1) / 7.0)
    expected_day2_ctrimp = day1 + ((0.0 - day1) / 42.0)
    assert rows[1]["atrimp"] == pytest.approx(expected_day2_atrimp)
    assert rows[1]["ctrimp"] == pytest.approx(expected_day2_ctrimp)
    assert rows[2]["btrimp"] == pytest.approx(rows[2]["ctrimp"] - rows[2]["atrimp"])
    print("DONE: daily aggregation, gap fill and EMA formulas are correct")


@pytest.mark.mytral
def test_daily_trimp_rows_fallbacks_and_skips():
    # GIVEN
    profile = settings.UserProfile(
        user_id="u1",
        user="user",
        email="user@example.com",
        password_enc="x",
        dataset_name="main",
        dataset_names=["main"],
        gender=True,
        age=45,
    )
    activities = [
        _activity(2026, 6, 1, duration_seconds=3600, avg_hr=0, max_hr=180, min_hr=55),
        _activity(2026, 6, 2, duration_seconds=3600, avg_hr=140, max_hr=50, min_hr=60),
        _activity(2026, 6, 3, duration_seconds=3600, avg_hr=140, max_hr=0, min_hr=58),
    ]

    # WHEN
    rows = trimp_uri_space._calc_daily_trimp_rows(
        activities=activities,
        user_profile=profile,
        resting_hr_fallback=60.0,
        profile_max_hr_fallback=185.0,
    )

    # THEN
    assert len(rows) == 1
    assert rows[0]["date"].isoformat() == "2026-06-03"
    assert rows[0]["trimp"] > 0
    print("DONE: invalid activities are skipped and max-hr fallback is used")


@pytest.mark.mytral
def test_daily_trimp_rows_are_order_invariant():
    # GIVEN
    profile = settings.UserProfile(
        user_id="u1",
        user="user",
        email="user@example.com",
        password_enc="x",
        dataset_name="main",
        dataset_names=["main"],
        gender=True,
        age=35,
    )
    activities_asc = [
        _activity(2026, 6, 1, duration_seconds=1200, avg_hr=135, max_hr=185, min_hr=55),
        _activity(2026, 6, 2, duration_seconds=2400, avg_hr=145, max_hr=188, min_hr=56),
        _activity(2026, 6, 3, duration_seconds=3600, avg_hr=150, max_hr=190, min_hr=57),
    ]
    activities_desc = list(reversed(activities_asc))

    # WHEN
    rows_asc = trimp_uri_space._calc_daily_trimp_rows(
        activities=activities_asc,
        user_profile=profile,
        resting_hr_fallback=60.0,
        profile_max_hr_fallback=190.0,
    )
    rows_desc = trimp_uri_space._calc_daily_trimp_rows(
        activities=activities_desc,
        user_profile=profile,
        resting_hr_fallback=60.0,
        profile_max_hr_fallback=190.0,
    )

    # THEN
    assert len(rows_asc) == len(rows_desc)
    for left, right in zip(rows_asc, rows_desc):
        assert left["date"] == right["date"]
        assert left["trimp"] == pytest.approx(right["trimp"])
        assert left["atrimp"] == pytest.approx(right["atrimp"])
        assert left["ctrimp"] == pytest.approx(right["ctrimp"])
        assert left["btrimp"] == pytest.approx(right["btrimp"])
    print("DONE: TRIMP series is invariant to activity input ordering")


@pytest.mark.mytral
def test_trimp_chart_smoke():
    # GIVEN
    rows = [
        {
            "date": datetime.date(2026, 6, 1),
            "trimp": 70.0,
            "atrimp": 70.0,
            "ctrimp": 70.0,
            "btrimp": 0.0,
            "sessions": 1,
            "duration_min": 60.0,
        }
    ]

    # WHEN
    script, div = charts.trimp_composite(rows)

    # THEN
    assert "Bokeh" in script
    assert "<div" in div
    print("DONE: TRIMP chart returns Bokeh components")


@pytest.mark.mytral
def test_insight_trimp_route_renders(monkeypatch):
    # GIVEN
    captured = {}
    profile = SimpleNamespace(
        dataset_name="main",
        athlete_metrics=SimpleNamespace(e_max_hr=182),
        age=39,
        gender=True,
        user="user",
    )
    activities = [
        _activity(2026, 6, 1, duration_seconds=3600, avg_hr=145, max_hr=188, min_hr=55)
    ]

    def fake_render_template(template_name, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "ok"

    monkeypatch.setattr(trimp_uri_space.ds, "profile", lambda user_id: profile)
    monkeypatch.setattr(
        trimp_uri_space.ds, "list_activities", lambda **kwargs: activities
    )
    monkeypatch.setattr(
        trimp_uri_space.stats.UserProfileStats,
        "from_entity",
        lambda user_profile, activities, logger: SimpleNamespace(resting_hr=56),
    )
    monkeypatch.setattr(
        trimp_uri_space.charts,
        "trimp_composite",
        lambda daily_rows, is_mobile_view: (
            "<script>Bokeh</script>",
            "<div>chart</div>",
        ),
    )
    monkeypatch.setattr(flask, "render_template", fake_render_template)

    with trimp_uri_space.flask_app.test_request_context("/insight/trimp", method="GET"):
        flask.session[trimp_uri_space.COOKIE_USER] = "user-1"

        # WHEN
        response = trimp_uri_space.insight_trimp()

    # THEN
    assert response == "ok"
    assert captured["template_name"] == "insight-trimp.html"
    assert captured["context"]["div"] == "<div>chart</div>"
    assert captured["context"]["script"] == "<script>Bokeh</script>"
    print("DONE: /insight/trimp route renders TRIMP template")
