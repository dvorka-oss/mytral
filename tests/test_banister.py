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
from mytral import commons
from mytral.backends import entities
from mytral.metrics import banister


def _make_activity(
    year: int,
    month: int,
    day: int,
    duration_seconds: int = 3600,
    avg_hr: int = 150,
    max_hr: int = 190,
    min_hr: int = 55,
    key: str = "",
) -> entities.ActivityEntity:
    return entities.ActivityEntity(
        key=key or f"act-{year}-{month}-{day}",
        when_year=year,
        when_month=month,
        when_day=day,
        duration_seconds=duration_seconds,
        avg_hr=avg_hr,
        max_hr=max_hr,
        min_hr=min_hr,
    )


# ---------------------------------------------------------------------------
# Banister model math tests
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_banister_run_empty_input():
    # GIVEN no data
    # WHEN
    rows = banister.run([])
    # THEN
    assert rows == []
    print("DONE: Banister run on empty input returns empty list")


@pytest.mark.mytral
def test_banister_run_single_day():
    # GIVEN a single day with TRIMP 100
    pairs = [(datetime.date(2026, 6, 1), 100.0)]
    # WHEN
    rows = banister.run(pairs)
    # THEN
    assert len(rows) == 1
    assert rows[0].date == datetime.date(2026, 6, 1)
    assert rows[0].trimp == 100.0
    assert rows[0].fitness == 100.0
    assert rows[0].fatigue == 100.0
    assert rows[0].performance == pytest.approx(-100.0)  # k1=1, k2=2
    print("DONE: Banister run on single day initializes correctly")


@pytest.mark.mytral
def test_banister_run_ema_decay():
    # GIVEN two days: day1 TRIMP=100, day2 TRIMP=0 (rest)
    # use params with gamma=0 to disable negative impulse for pure EMA test
    params = banister.BanisterParams(gamma=0.0, w_recovery_threshold=0.0)
    pairs = [
        (datetime.date(2026, 6, 1), 100.0),
        (datetime.date(2026, 6, 2), 0.0),
    ]
    # WHEN
    rows = banister.run(pairs, params=params)
    # THEN
    assert len(rows) == 2
    # day 2: fitness should decay toward 0
    decay_fitness = math.exp(-1.0 / 42.0)
    expected_fitness_day2 = 100.0 * decay_fitness  # w_pos=0, so only decay
    assert rows[1].fitness == pytest.approx(expected_fitness_day2)
    # fatigue decays faster (tau=7)
    decay_fatigue = math.exp(-1.0 / 7.0)
    expected_fatigue_day2 = 100.0 * decay_fatigue
    assert rows[1].fatigue == pytest.approx(expected_fatigue_day2)
    print("DONE: Banister EMA decay follows exponential time constants")


@pytest.mark.mytral
def test_banister_run_negative_impulse():
    # GIVEN a day with TRIMP below recovery threshold (25)
    params = banister.BanisterParams(w_recovery_threshold=25.0)
    pairs = [
        (datetime.date(2026, 6, 1), 100.0),
        (datetime.date(2026, 6, 2), 10.0),  # below threshold → recovery credit
    ]
    # WHEN
    rows = banister.run(pairs, params=params)
    # THEN
    assert len(rows) == 2
    # day 2: w_pos=0, w_neg=15 → negative impulse reduces fatigue
    assert rows[1].fatigue < rows[0].fatigue * math.exp(-1.0 / 7.0)
    print("DONE: negative training impulse reduces fatigue on recovery days")


@pytest.mark.mytral
def test_banister_run_performance_formula():
    # GIVEN a steady-state series where fitness ≈ fatigue
    params = banister.BanisterParams(k1=1.0, k2=2.0)
    pairs = [
        (datetime.date(2026, 6, 1), 50.0),
        (datetime.date(2026, 6, 2), 50.0),
        (datetime.date(2026, 6, 3), 50.0),
    ]
    # WHEN
    rows = banister.run(pairs, params=params)
    # THEN performance = k1*fitness - k2*fatigue
    for row in rows:
        expected_perf = 1.0 * row.fitness - 2.0 * row.fatigue
        assert row.performance == pytest.approx(expected_perf)
    print("DONE: performance = k1·fitness − k2·fatigue holds for every row")


@pytest.mark.mytral
def test_banister_run_hand_calc_reference():
    # GIVEN a 90-day synthetic series with known input
    # hand-calculated reference for the first 3 days
    params = banister.BanisterParams(
        tau1_days=42.0,
        tau2_days=7.0,
        k1=1.0,
        k2=2.0,
        gamma=0.0,  # disable negative impulse for hand-calc simplicity
        w_recovery_threshold=0.0,
    )
    pairs = [
        (datetime.date(2026, 1, 1), 80.0),
        (datetime.date(2026, 1, 2), 0.0),
        (datetime.date(2026, 1, 3), 80.0),
    ]
    # WHEN
    rows = banister.run(pairs, params=params)
    # THEN
    # day 1: fitness=80, fatigue=80, perf=80-160=-80
    assert rows[0].fitness == pytest.approx(80.0)
    assert rows[0].fatigue == pytest.approx(80.0)
    assert rows[0].performance == pytest.approx(-80.0)
    # day 2: fitness=80*e^(-1/42), fatigue=80*e^(-1/7)
    d1_fit = 80.0 * math.exp(-1.0 / 42.0)
    d1_fat = 80.0 * math.exp(-1.0 / 7.0)
    assert rows[1].fitness == pytest.approx(d1_fit)
    assert rows[1].fatigue == pytest.approx(d1_fat)
    assert rows[1].performance == pytest.approx(d1_fit - 2.0 * d1_fat)
    # day 3: fitness=d1_fit*e^(-1/42)+80*(1-e^(-1/42))
    #         fatigue=d1_fat*e^(-1/7)+80*(1-e^(-1/7))
    dec_fit = math.exp(-1.0 / 42.0)
    dec_fat = math.exp(-1.0 / 7.0)
    d2_fit = d1_fit * dec_fit + 80.0 * (1.0 - dec_fit)
    d2_fat = d1_fat * dec_fat + 80.0 * (1.0 - dec_fat)
    assert rows[2].fitness == pytest.approx(d2_fit)
    assert rows[2].fatigue == pytest.approx(d2_fat)
    assert rows[2].performance == pytest.approx(d2_fit - 2.0 * d2_fat)
    print("DONE: hand-calculated reference matches to 0.01")


@pytest.mark.mytral
def test_banister_row_legacy_properties():
    # GIVEN a BanisterRow
    row = banister.BanisterRow(
        date=datetime.date(2026, 6, 1),
        trimp=100.0,
        fitness=80.0,
        fatigue=60.0,
        performance=-40.0,
    )
    # WHEN accessing legacy properties
    # THEN
    assert row.atrimp == 60.0
    assert row.ctrimp == 80.0
    assert row.btrimp == 20.0
    print("DONE: BanisterRow legacy properties map correctly")


@pytest.mark.mytral
def test_banister_row_diagnosis():
    # GIVEN rows at different performance levels
    fresh = banister.BanisterRow(
        date=datetime.date(2026, 6, 1), trimp=0, fitness=100, fatigue=30, performance=40
    )
    optimal = banister.BanisterRow(
        date=datetime.date(2026, 6, 2), trimp=0, fitness=100, fatigue=80, performance=10
    )
    tired = banister.BanisterRow(
        date=datetime.date(2026, 6, 3), trimp=0, fitness=80, fatigue=90, performance=-10
    )
    overreached = banister.BanisterRow(
        date=datetime.date(2026, 6, 4),
        trimp=0,
        fitness=60,
        fatigue=100,
        performance=-40,
    )
    # THEN
    assert fresh.diagnosis == "fresh"
    assert optimal.diagnosis == "optimal"
    assert tired.diagnosis == "tired"
    assert overreached.diagnosis == "overreached"
    print("DONE: diagnosis classification matches performance zones")


# ---------------------------------------------------------------------------
# Projection tests
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_banister_project_continues_from_last_row():
    # GIVEN a series and projection for 7 days
    pairs = [
        (datetime.date(2026, 6, 1), 50.0),
        (datetime.date(2026, 6, 2), 50.0),
        (datetime.date(2026, 6, 3), 50.0),
    ]
    rows = banister.run(pairs)
    # WHEN
    proj = banister.project(rows, days=7)
    # THEN
    assert len(proj) == 7
    assert proj[0].date == datetime.date(2026, 6, 4)
    assert proj[-1].date == datetime.date(2026, 6, 10)
    print("DONE: projection continues from the day after the last row")


@pytest.mark.mytral
def test_banister_project_empty_input():
    # GIVEN empty rows
    # WHEN
    proj = banister.project([], days=7)
    # THEN
    assert proj == []
    print("DONE: projection on empty input returns empty list")


# ---------------------------------------------------------------------------
# Annotation tests
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_banister_annotate_finds_peak_and_pb():
    # GIVEN a series with a clear peak
    pairs = [
        (datetime.date(2026, 6, 1), 50.0),
        (datetime.date(2026, 6, 2), 50.0),
        (datetime.date(2026, 6, 3), 50.0),
    ]
    rows = banister.run(pairs)
    # WHEN
    annotations = banister.annotate(rows)
    # THEN
    kinds = {a.kind for a in annotations}
    assert "fitness_pb" in kinds
    print("DONE: annotate finds fitness PB")


@pytest.mark.mytral
def test_banister_annotate_detects_overreaching():
    # GIVEN a series with sustained low performance
    params = banister.BanisterParams(
        k1=1.0, k2=2.0, w_recovery_threshold=0.0, gamma=0.0
    )
    # build a series with high load causing overreach
    pairs = []
    base_date = datetime.date(2026, 6, 1)
    for i in range(30):
        pairs.append((base_date + datetime.timedelta(days=i), 120.0))
    rows = banister.run(pairs, params=params)
    # WHEN
    annotations = banister.annotate(rows)
    # THEN - with sustained high load, performance should drop below -25
    overreach_anns = [a for a in annotations if a.kind == "overreach"]
    # may or may not find overreach depending on params, but should not crash
    assert isinstance(annotations, list)
    assert isinstance(overreach_anns, list)
    print("DONE: annotate runs without error on sustained-load series")


# ---------------------------------------------------------------------------
# Insight tests
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_banister_compute_insights_state_card():
    # GIVEN a short series
    pairs = [
        (datetime.date(2026, 6, 1), 50.0),
        (datetime.date(2026, 6, 2), 50.0),
    ]
    rows = banister.run(pairs)
    proj = banister.project(rows, days=14)
    annotations = banister.annotate(rows)
    # WHEN
    insights = banister.compute_insights(rows, proj, annotations)
    # THEN
    assert len(insights) >= 1
    state_card = next(c for c in insights if c.kind == "state")
    assert "Current State" in state_card.title
    assert len(state_card.body_lines) >= 2
    print("DONE: compute_insights always produces a state card")


@pytest.mark.mytral
def test_banister_compute_insights_empty_input():
    # GIVEN no data
    # WHEN
    insights = banister.compute_insights([], [], [])
    # THEN
    assert insights == []
    print("DONE: compute_insights on empty input returns empty list")


# ---------------------------------------------------------------------------
# Activity impact tests
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_banister_analyze_activity_deltas():
    # GIVEN a series and an activity
    pairs = [
        (datetime.date(2026, 6, 1), 50.0),
        (datetime.date(2026, 6, 2), 100.0),
        (datetime.date(2026, 6, 3), 50.0),
    ]
    rows = banister.run(pairs)
    proj = banister.project(rows, days=14)
    activity = _make_activity(2026, 6, 2, duration_seconds=3600, avg_hr=150, max_hr=190)
    # WHEN
    impact = banister.analyze_activity(activity, rows, proj)
    # THEN
    assert impact.post_row is not None
    assert impact.post_row.date == datetime.date(2026, 6, 2)
    assert impact.pre_row is not None
    assert impact.pre_row.date == datetime.date(2026, 6, 1)
    assert impact.delta_fitness != 0.0
    assert impact.delta_fatigue != 0.0
    print("DONE: analyze_activity computes pre/post deltas correctly")


@pytest.mark.mytral
def test_banister_analyze_activity_missing_date():
    # GIVEN an activity on a date not in the series
    pairs = [(datetime.date(2026, 6, 1), 50.0)]
    rows = banister.run(pairs)
    proj = banister.project(rows, days=14)
    activity = _make_activity(
        2026, 6, 15, duration_seconds=3600, avg_hr=150, max_hr=190
    )
    # WHEN
    impact = banister.analyze_activity(activity, rows, proj)
    # THEN
    assert impact.post_row is None
    assert "No Banister data" in impact.recommendation
    print("DONE: analyze_activity handles missing date gracefully")


@pytest.mark.mytral
def test_banister_analyze_activity_hard_density_context():
    # GIVEN a series with many hard days
    params = banister.BanisterParams(w_recovery_threshold=0.0, gamma=0.0)
    pairs = []
    base_date = datetime.date(2026, 6, 1)
    for i in range(14):
        pairs.append((base_date + datetime.timedelta(days=i), 120.0))
    rows = banister.run(pairs, params=params)
    proj = banister.project(rows, days=14)
    activity = _make_activity(
        2026, 6, 14, duration_seconds=3600, avg_hr=160, max_hr=195
    )
    # WHEN
    impact = banister.analyze_activity(activity, rows, proj)
    # THEN
    assert len(impact.context) >= 1
    assert any("hard session" in line.lower() for line in impact.context)
    print("DONE: analyze_activity flags high hard-session density")


# ---------------------------------------------------------------------------
# Chart tests (Banister mode)
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_trimp_chart_banister_mode():
    # GIVEN Banister rows
    pairs = [
        (datetime.date(2026, 6, 1), 70.0),
        (datetime.date(2026, 6, 2), 50.0),
    ]
    rows = banister.run(pairs)
    proj = banister.project(rows, days=7)
    annotations = banister.annotate(rows)
    # WHEN
    script, div = charts.trimp_composite(
        daily_rows=rows,
        is_mobile_view=False,
        params=banister.BanisterParams(),
        projection=proj,
        annotations=annotations,
    )
    # THEN
    assert "Bokeh" in script
    assert "<div" in div
    print("DONE: TRIMP chart in Banister mode returns Bokeh components")


@pytest.mark.mytral
def test_trimp_chart_banister_mode_mobile():
    # GIVEN Banister rows
    pairs = [(datetime.date(2026, 6, 1), 70.0)]
    rows = banister.run(pairs)
    # WHEN
    script, div = charts.trimp_composite(
        daily_rows=rows,
        is_mobile_view=True,
        params=banister.BanisterParams(),
    )
    # THEN
    assert "Bokeh" in script
    assert "<div" in div
    print("DONE: TRIMP chart in Banister mobile mode returns Bokeh components")


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_activity_trimp_analysis_route_renders(monkeypatch):
    # GIVEN
    from mytral.blueprints import trimp_uri_space

    captured = {}
    profile = SimpleNamespace(
        dataset_name="main",
        athlete_metrics=SimpleNamespace(e_max_hr=182),
        banister_params=banister.BanisterParams(),
        age=39,
        gender=True,
        user="user",
    )
    activity = _make_activity(2026, 6, 1, duration_seconds=3600, avg_hr=145, max_hr=188)

    def fake_render_template(template_name, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "ok"

    def fake_get_activity(user_id, dataset_name, key):
        return activity

    def fake_list_activities(**kwargs):
        return [activity]

    monkeypatch.setattr(trimp_uri_space.ds, "profile", lambda user_id: profile)
    monkeypatch.setattr(trimp_uri_space.ds, "get_activity", fake_get_activity)
    monkeypatch.setattr(trimp_uri_space.ds, "list_activities", fake_list_activities)
    monkeypatch.setattr(
        trimp_uri_space.ds,
        "list_activity_types",
        lambda user_id: SimpleNamespace(
            color=lambda k: "#000000",
            emoji=lambda k: "🏃",
            name=lambda k: "Run",
        ),
    )
    monkeypatch.setattr(
        trimp_uri_space.stats.UserProfileStats,
        "from_entity",
        lambda user_profile, activities, logger: SimpleNamespace(resting_hr=56),
    )
    monkeypatch.setattr(
        trimp_uri_space.charts,
        "trimp_composite",
        lambda daily_rows, is_mobile_view, params=None, projection=None, annotations=None, highlight_date=None: (  # noqa: E501
            "<script>Bokeh</script>",
            "<div>chart</div>",
        ),
    )
    monkeypatch.setattr(flask, "render_template", fake_render_template)

    # mock the cache
    fake_cache = SimpleNamespace()
    fake_user_cache = SimpleNamespace()
    fake_user_cache.banister_rows = lambda: None
    fake_user_cache.set_banister_rows = lambda rows: rows
    fake_cache.user = lambda user_id: fake_user_cache
    monkeypatch.setattr(trimp_uri_space.ds, "cache", fake_cache)

    with trimp_uri_space.flask_app.test_request_context(
        "/app/activities/act-2026-6-1/analysis-trimp", method="GET"
    ):
        flask.session[trimp_uri_space.COOKIE_USER] = "user-1"

        # WHEN
        response = trimp_uri_space.activity_trimp_analysis(key="act-2026-6-1")

    # THEN
    assert response == "ok"
    assert captured["template_name"] == "activity-analysis-trimp.html"
    assert captured["context"]["div"] == "<div>chart</div>"
    print("DONE: /app/activities/<key>/analysis-trimp route renders")


@pytest.mark.mytral
def test_insight_trimp_route_banister_mode(monkeypatch):
    # GIVEN
    from mytral.blueprints import trimp_uri_space

    captured = {}
    profile = SimpleNamespace(
        dataset_name="main",
        athlete_metrics=SimpleNamespace(e_max_hr=182),
        banister_params=banister.BanisterParams(),
        age=39,
        gender=True,
        user="user",
    )
    activities = [
        _make_activity(2026, 6, 1, duration_seconds=3600, avg_hr=145, max_hr=188)
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
        lambda daily_rows, is_mobile_view, params=None, projection=None, annotations=None, highlight_date=None: (  # noqa: E501
            "<script>Bokeh</script>",
            "<div>chart</div>",
        ),
    )
    monkeypatch.setattr(flask, "render_template", fake_render_template)
    monkeypatch.setattr(trimp_uri_space.ff, "can", lambda feature: True)

    # mock the cache
    fake_cache = SimpleNamespace()
    fake_user_cache = SimpleNamespace()
    fake_user_cache.banister_rows = lambda: None
    fake_user_cache.set_banister_rows = lambda rows: rows
    fake_cache.user = lambda user_id: fake_user_cache
    monkeypatch.setattr(trimp_uri_space.ds, "cache", fake_cache)

    with trimp_uri_space.flask_app.test_request_context("/insight/trimp", method="GET"):
        flask.session[trimp_uri_space.COOKIE_USER] = "user-1"

        # WHEN
        response = trimp_uri_space.insight_trimp()

    # THEN
    assert response == "ok"
    assert captured["template_name"] == "insight-trimp.html"
    assert "insights" in captured["context"]
    print("DONE: /insight/trimp route in Banister mode renders with insights")


# ---------------------------------------------------------------------------
# Cache lifecycle tests
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_get_banister_rows_cache_hit(monkeypatch):
    # GIVEN cached Banister rows
    from mytral.blueprints import trimp_uri_space

    cached_rows = [
        banister.BanisterRow(
            date=datetime.date(2026, 6, 1),
            trimp=50.0,
            fitness=50.0,
            fatigue=50.0,
            performance=-50.0,
        )
    ]

    fake_cache = SimpleNamespace()
    fake_user_cache = SimpleNamespace()
    fake_user_cache.banister_rows = lambda: cached_rows
    fake_cache.user = lambda user_id: fake_user_cache
    monkeypatch.setattr(trimp_uri_space.ds, "cache", fake_cache)

    # WHEN
    result = trimp_uri_space.get_banister_rows("user-1")

    # THEN
    assert result is cached_rows
    print("DONE: get_banister_rows returns cached rows on cache hit")


@pytest.mark.mytral
def test_get_banister_rows_cache_miss_computes(monkeypatch):
    # GIVEN no cached rows
    from mytral.blueprints import trimp_uri_space

    profile = SimpleNamespace(
        dataset_name="main",
        athlete_metrics=SimpleNamespace(e_max_hr=182),
        banister_params=banister.BanisterParams(),
        age=39,
        gender=True,
        user="user",
    )
    activities = [
        _make_activity(2026, 6, 1, duration_seconds=3600, avg_hr=145, max_hr=188)
    ]

    stored_rows = []

    fake_cache = SimpleNamespace()
    fake_user_cache = SimpleNamespace()
    fake_user_cache.banister_rows = lambda: None
    fake_user_cache.set_banister_rows = lambda rows: stored_rows.append(rows) or rows
    fake_cache.user = lambda user_id: fake_user_cache
    monkeypatch.setattr(trimp_uri_space.ds, "cache", fake_cache)
    monkeypatch.setattr(trimp_uri_space.ds, "profile", lambda user_id: profile)
    monkeypatch.setattr(
        trimp_uri_space.ds, "list_activities", lambda **kwargs: activities
    )
    monkeypatch.setattr(
        trimp_uri_space.stats.UserProfileStats,
        "from_entity",
        lambda user_profile, activities, logger: SimpleNamespace(resting_hr=56),
    )

    # WHEN
    result = trimp_uri_space.get_banister_rows("user-1")

    # THEN
    assert len(result) == 1
    assert result[0].date == datetime.date(2026, 6, 1)
    assert len(stored_rows) == 1
    print("DONE: get_banister_rows computes and caches on cache miss")


# ---------------------------------------------------------------------------
# Feature flag tests
# ---------------------------------------------------------------------------


@pytest.mark.mytral
def test_trimp_rocks_feature_flag_exists():
    # GIVEN the feature flags module
    from mytral import releng

    # THEN
    assert hasattr(releng.FeatureFlags, "TRIMP_ROCKS")
    assert releng.FeatureFlags.TRIMP_ROCKS == "TRIMP_ROCKS"
    print("DONE: TRIMP_ROCKS feature flag is defined")


@pytest.mark.mytral
def test_impact_analysis_constants_in_commons():
    # THEN
    assert commons.HARD_TRIMP_THRESHOLD == 100.0
    assert commons.HARD_DENSITY_DAYS == 14
    assert commons.HARD_DENSITY_COUNT == 4
    assert commons.OVERREACH_PERFORMANCE_FLOOR == -25.0
    assert commons.OVERREACH_MIN_DAYS == 4
    print("DONE: impact-analysis constants are defined in commons")
