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

"""Tests for TabPFN feature engineering and illness risk prediction."""

from datetime import date
from datetime import timedelta

import pandas as pd
import pytest

from mytral import commons
from mytral.ml.icl import features as icl_features
from mytral.ml.icl import manager as icl_manager
from mytral.ml.icl.predictions import anomaly as icl_anomaly
from mytral.ml.icl.predictions import fatigue as icl_fatigue
from mytral.ml.icl.predictions import performance as icl_performance
from mytral.ml.icl.predictions import rest_day as icl_rest_day
from mytral.ml.icl.predictions import sick as icl_sick


def _make_activities_json(
    sick_dates: list[str] | None = None,
    activity_dates: list[str] | None = None,
) -> dict:
    """Build a minimal activities_json fixture.

    Parameters
    ----------
    sick_dates : list[str] | None
        ISO date strings of sick days.
    activity_dates : list[str] | None
        ISO date strings of training days (distance=10 km each).

    Returns
    -------
    dict
        Minimal MyTraL dataset dictionary.
    """
    activities: dict = {}
    for d_str in activity_dates or []:
        year = d_str[:4]
        if year not in activities:
            activities[year] = []
        activities[year].append({"date": d_str, "distance": 10.0, "hr_max": 160.0})
    return {
        "activities": activities,
        "sick": sick_dates or [],
    }


#
# extract_sick_features
#


@pytest.mark.mytral
def test_extract_sick_features_empty_activities():
    """Test extract_sick_features with no activities returns valid DataFrame."""
    # GIVEN
    activities_json = _make_activities_json()

    # WHEN
    df = icl_features.extract_sick_features(activities_json, lookback_days=7)

    # THEN
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 8  # 7 + 1 (inclusive range)
    assert "sick" in df.columns
    assert df["sick"].sum() == 0
    assert "km_7d" in df.columns
    print("DONE: extract_sick_features returns valid DataFrame for empty activities")


@pytest.mark.mytral
def test_extract_sick_features_marks_sick_days():
    """Test extract_sick_features correctly labels sick days."""
    # GIVEN
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    activities_json = _make_activities_json(sick_dates=[yesterday])

    # WHEN
    df = icl_features.extract_sick_features(activities_json, lookback_days=7)

    # THEN
    assert df["sick"].sum() >= 1
    sick_rows = df[df["sick"] == 1]
    assert yesterday in sick_rows["date"].values
    print("DONE: extract_sick_features marks sick days correctly")


@pytest.mark.mytral
def test_extract_sick_features_km_accumulation():
    """Test extract_sick_features accumulates km_7d correctly."""
    # GIVEN
    today = date.today()
    three_days_ago = (today - timedelta(days=3)).isoformat()
    activities_json = _make_activities_json(
        activity_dates=[three_days_ago]  # 10 km 3 days ago
    )

    # WHEN
    df = icl_features.extract_sick_features(activities_json, lookback_days=14)
    today_row = df[df["date"] == today.isoformat()]

    # THEN
    assert not today_row.empty
    # 10 km from 3 days ago should appear in km_7d for today
    assert float(today_row["km_7d"].iloc[0]) == pytest.approx(10.0)
    print("DONE: extract_sick_features accumulates km_7d correctly")


@pytest.mark.mytral
def test_extract_sick_features_has_all_feature_columns():
    """Test that extracted features DataFrame contains all SICK_FEATURE_COLS."""
    # GIVEN
    activities_json = _make_activities_json()

    # WHEN
    df = icl_features.extract_sick_features(activities_json, lookback_days=10)

    # THEN
    for col in icl_features.SICK_FEATURE_COLS:
        assert col in df.columns, f"missing column: {col}"
    print("DONE: extract_sick_features DataFrame contains all required feature columns")


@pytest.mark.mytral
def test_extract_sick_features_sick_lag_1():
    """Test that sick_lag_1 is 1 the day after a sick day."""
    # GIVEN
    today = date.today()
    yesterday = today - timedelta(days=1)
    activities_json = _make_activities_json(sick_dates=[yesterday.isoformat()])

    # WHEN
    df = icl_features.extract_sick_features(activities_json, lookback_days=7)
    today_row = df[df["date"] == today.isoformat()]

    # THEN
    assert not today_row.empty
    assert int(today_row["sick_lag_1"].iloc[0]) == 1
    print("DONE: sick_lag_1 is 1 the day after a sick day")


#
# sufficient_data
#


@pytest.mark.mytral
def test_sufficient_data_returns_false_for_empty_df():
    """Test sufficient_data returns False for empty DataFrame."""
    # GIVEN
    df = pd.DataFrame()

    # WHEN
    result = icl_features.sufficient_data(df)

    # THEN
    assert result is False
    print("DONE: sufficient_data returns False for empty DataFrame")


@pytest.mark.mytral
def test_sufficient_data_returns_false_for_too_few_sick_days():
    """Test sufficient_data returns False when fewer sick days than threshold."""
    # GIVEN
    activities_json = _make_activities_json(
        sick_dates=[(date.today() - timedelta(days=i)).isoformat() for i in range(2)]
    )
    df = icl_features.extract_sick_features(activities_json, lookback_days=60)

    # WHEN
    result = icl_features.sufficient_data(df, min_sick_days=3)

    # THEN
    assert result is False
    print("DONE: sufficient_data returns False for too few sick days")


@pytest.mark.mytral
def test_sufficient_data_returns_true_for_enough_sick_days():
    """Test sufficient_data returns True when enough sick days are present."""
    # GIVEN
    sick_list = [(date.today() - timedelta(days=i * 10)).isoformat() for i in range(5)]
    activities_json = _make_activities_json(sick_dates=sick_list)
    df = icl_features.extract_sick_features(activities_json, lookback_days=90)

    # WHEN
    result = icl_features.sufficient_data(df, min_sick_days=3)

    # THEN
    assert result is True
    print("DONE: sufficient_data returns True for enough sick days")


#
# predict_row_for_today
#


@pytest.mark.mytral
def test_predict_row_for_today_returns_single_row():
    """Test predict_row_for_today returns a single-row DataFrame."""
    # GIVEN
    activities_json = _make_activities_json()

    # WHEN
    df = icl_features.predict_row_for_today(activities_json)

    # THEN
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert list(df.columns) == icl_features.SICK_FEATURE_COLS
    print("DONE: predict_row_for_today returns a single-row DataFrame")


#
# IclSickPredictor
#


@pytest.mark.mytral
def test_icl_sick_predictor_unavailable_when_not_installed(monkeypatch):
    """Test IclSickPredictor.predict returns unavailable when tabpfn not installed."""
    # GIVEN
    monkeypatch.setattr(icl_manager, "is_tabpfn_installed", lambda: False)
    predictor = icl_sick.IclSickPredictor()
    activities_json = _make_activities_json()

    # WHEN
    result = predictor.predict(activities_json)

    # THEN
    assert result["available"] is False
    assert result["probability"] is None
    assert result["label"] is None
    assert "not installed" in result["reason"].lower()
    print("DONE: IclSickPredictor returns unavailable when tabpfn not installed")


@pytest.mark.mytral
def test_icl_sick_predictor_unavailable_when_weights_missing(monkeypatch):
    """Test IclSickPredictor.predict returns unavailable when weights not downloaded."""
    # GIVEN
    monkeypatch.setattr(icl_manager, "is_tabpfn_installed", lambda: True)
    monkeypatch.setattr(icl_manager, "is_weights_cached", lambda: False)
    predictor = icl_sick.IclSickPredictor()
    activities_json = _make_activities_json()

    # WHEN
    result = predictor.predict(activities_json)

    # THEN
    assert result["available"] is False
    assert "not downloaded" in result["reason"].lower()
    print("DONE: IclSickPredictor returns unavailable when weights not downloaded")


@pytest.mark.mytral
def test_icl_sick_predictor_unavailable_when_insufficient_data(monkeypatch):
    """Test IclSickPredictor.predict returns unavailable for insufficient data."""
    # GIVEN
    monkeypatch.setattr(icl_manager, "is_tabpfn_installed", lambda: True)
    monkeypatch.setattr(icl_manager, "is_weights_cached", lambda: True)
    predictor = icl_sick.IclSickPredictor()
    activities_json = _make_activities_json()  # no sick days

    # WHEN
    result = predictor.predict(activities_json)

    # THEN
    assert result["available"] is False
    assert "not enough" in result["reason"].lower()
    print("DONE: IclSickPredictor returns unavailable for insufficient data")


@pytest.mark.mytral
def test_risk_label_thresholds():
    """Test _risk_label returns correct labels for key probability values."""
    # GIVEN / WHEN / THEN
    assert icl_sick._risk_label(0.05) == "low"
    assert icl_sick._risk_label(0.20) == "moderate"
    assert icl_sick._risk_label(0.50) == "high"
    assert icl_sick._risk_label(0.75) == "very_high"
    print("DONE: _risk_label returns correct labels for key probability values")


#
# build_activities_json_for_icl
#


@pytest.mark.mytral
def test_build_activities_json_for_icl_basic():
    """Test build_activities_json_for_icl converts ActivityEntity dict correctly."""
    # GIVEN
    from mytral.backends.entities import ActivityEntity

    entity = ActivityEntity(
        key="a1",
        when_year=2024,
        when_month=6,
        when_day=1,
        activity_type_key="run",
        distance=10000,  # 10 km in metres
        duration_seconds=3600,
        max_hr=165,
        avg_hr=145,
        intensity=commons.INTENSITY_EASY,
        race=False,
    )
    raw_activities = {"a1": entity}

    # WHEN
    result = icl_features.build_activities_json_for_icl(raw_activities)

    # THEN
    assert "activities" in result
    assert "sick" in result
    assert "2024" in result["activities"]
    row = result["activities"]["2024"][0]
    assert row["date"] == "2024-06-01"
    assert abs(row["distance"] - 10.0) < 0.01
    assert row["hr_max"] == 165
    assert row["activity_type_key"] == "run"
    assert result["sick"] == []
    print("DONE: build_activities_json_for_icl converts ActivityEntity dict correctly")


@pytest.mark.mytral
def test_build_activities_json_for_icl_sick_activity():
    """Test build_activities_json_for_icl moves sick activity type activities
    to sick list.

    """
    # GIVEN
    from mytral.backends.entities import ActivityEntity

    sick_entity = ActivityEntity(
        key="s1",
        when_year=2024,
        when_month=3,
        when_day=10,
        activity_type_key="sick",
        distance=0,
        duration_seconds=0,
        max_hr=0,
        avg_hr=0,
        intensity="",
        race=False,
    )
    raw_activities = {"s1": sick_entity}

    # WHEN
    result = icl_features.build_activities_json_for_icl(raw_activities)

    # THEN
    assert "2024-03-10" in result["sick"]
    # sick activity should NOT appear in the activities dict
    assert not any(
        row.get("activity_type_key") == "sick"
        for year_rows in result["activities"].values()
        for row in year_rows
    )
    print(
        "DONE: build_activities_json_for_icl moves sick activity type activities to "
        "sick list"
    )


#
# extract_fatigue_features
#


@pytest.mark.mytral
def test_extract_fatigue_features_empty():
    """Test extract_fatigue_features returns valid DataFrame for empty activities."""
    # GIVEN
    activities_json = _make_activities_json()

    # WHEN
    df = icl_features.extract_fatigue_features(activities_json, lookback_days=30)

    # THEN
    assert isinstance(df, pd.DataFrame)
    for col in icl_features.FATIGUE_FEATURE_COLS:
        assert col in df.columns, f"missing column: {col}"
    print("DONE: extract_fatigue_features returns valid DataFrame for empty activities")


@pytest.mark.mytral
def test_extract_fatigue_features_with_data():
    """Test extract_fatigue_features computes non-zero features from activity data."""
    # GIVEN
    today = date.today()
    activity_dates = [
        (today - timedelta(days=i)).isoformat()
        for i in range(20)
        if i % 2 == 0  # every other day
    ]
    activities_json = _make_activities_json(activity_dates=activity_dates)

    # WHEN
    df = icl_features.extract_fatigue_features(activities_json, lookback_days=30)

    # THEN
    assert not df.empty
    assert "fatigue_class" in df.columns
    assert df["atl_7d"].max() > 0
    print(
        "DONE: extract_fatigue_features computes non-zero features from activity data"
    )


#
# extract_rest_day_features
#


@pytest.mark.mytral
def test_extract_rest_day_features_empty():
    """Test extract_rest_day_features returns valid DataFrame for empty activities."""
    # GIVEN
    activities_json = _make_activities_json()

    # WHEN
    df = icl_features.extract_rest_day_features(activities_json, lookback_days=30)

    # THEN
    assert isinstance(df, pd.DataFrame)
    for col in icl_features.REST_DAY_FEATURE_COLS:
        assert col in df.columns, f"missing column: {col}"
    print(
        "DONE: extract_rest_day_features returns valid DataFrame for empty activities"
    )


@pytest.mark.mytral
def test_extract_rest_day_features_with_data():
    """Test extract_rest_day_features assigns should_rest labels."""
    # GIVEN
    today = date.today()
    activity_dates = [
        (today - timedelta(days=i)).isoformat()
        for i in range(40)
        if i % 3 != 0  # most days active; every 3rd day is rest
    ]
    activities_json = _make_activities_json(activity_dates=activity_dates)

    # WHEN
    df = icl_features.extract_rest_day_features(activities_json, lookback_days=45)

    # THEN
    assert not df.empty
    assert "should_rest" in df.columns
    # label should be binary
    assert set(df["should_rest"].unique()).issubset({0, 1})
    print("DONE: extract_rest_day_features assigns should_rest labels")


#
# extract_anomaly_features
#


@pytest.mark.mytral
def test_extract_anomaly_features_empty():
    """Test extract_anomaly_features returns empty DataFrame when no activities
    provided.
    """
    # GIVEN
    activities_json = _make_activities_json()

    # WHEN
    df = icl_features.extract_anomaly_features(activities_json, lookback_days=30)

    # THEN
    assert isinstance(df, pd.DataFrame)
    # anomaly detection works on actual activity rows, so empty input => empty output
    assert len(df) == 0
    print("DONE: extract_anomaly_features returns valid DataFrame for empty activities")


@pytest.mark.mytral
def test_extract_anomaly_features_with_data():
    """Test extract_anomaly_features assigns is_anomaly labels and computes z-scores."""
    # GIVEN
    today = date.today()
    activity_dates = [(today - timedelta(days=i)).isoformat() for i in range(15)]
    activities_json = _make_activities_json(activity_dates=activity_dates)

    # WHEN
    df = icl_features.extract_anomaly_features(activities_json, lookback_days=20)

    # THEN
    assert not df.empty
    assert "is_anomaly" in df.columns
    assert set(df["is_anomaly"].unique()).issubset({0, 1})
    print(
        "DONE: extract_anomaly_features assigns is_anomaly labels and computes z-scores"
    )


#
# extract_performance_features
#


@pytest.mark.mytral
def test_extract_performance_features_empty():
    """Test extract_performance_features returns empty DataFrame for no
    run activities.
    """
    # GIVEN
    activities_json = _make_activities_json()

    # WHEN
    df = icl_features.extract_performance_features(activities_json, lookback_days=180)

    # THEN
    assert isinstance(df, pd.DataFrame)
    # no run activities -> empty
    assert len(df) == 0
    print(
        "DONE: extract_performance_features returns empty DataFrame for no run "
        "activities"
    )


@pytest.mark.mytral
def test_extract_performance_features_with_run_data():
    """Test extract_performance_features computes Riegel labels for running
    activities.
    """
    # GIVEN
    today = date.today()
    run_dates = [(today - timedelta(days=i * 3)).isoformat() for i in range(12)]
    # Use a plain activities_json dict with activity_type_key=run explicitly
    activities: dict = {}
    for d_str in run_dates:
        year = d_str[:4]
        if year not in activities:
            activities[year] = []
        activities[year].append(
            {
                "date": d_str,
                "distance": 8.0,
                "hr_max": 170.0,
                "avg_hr": 150.0,
                "activity_type_key": "run",
                "intensity": "moderate",
                "duration_seconds": 2400,
                "race": False,
            }
        )
    activities_json = {"activities": activities, "sick": []}

    # WHEN
    df = icl_features.extract_performance_features(activities_json, lookback_days=365)

    # THEN
    assert not df.empty
    assert "riegel_10k_min" in df.columns
    assert df["riegel_10k_min"].min() > 0
    for col in icl_features.PERFORMANCE_FEATURE_COLS:
        assert col in df.columns, f"missing column: {col}"
    print(
        "DONE: extract_performance_features computes Riegel labels for running "
        "activities"
    )


#
# New predictor unavailability tests (tabpfn not installed)
#


@pytest.mark.mytral
def test_icl_fatigue_predictor_tabpfn_not_installed(monkeypatch):
    """Test IclFatiguePredictor.predict returns unavailable when tabpfn is missing."""
    # GIVEN
    monkeypatch.setattr(icl_manager, "is_tabpfn_installed", lambda: False)
    predictor = icl_fatigue.IclFatiguePredictor()
    activities_json = _make_activities_json()

    # WHEN
    result = predictor.predict(activities_json)

    # THEN
    assert result["available"] is False
    assert "tabpfn" in result["reason"].lower()
    assert result["label"] is None
    assert result["readiness_score"] is None
    print("DONE: IclFatiguePredictor returns unavailable when tabpfn is missing")


@pytest.mark.mytral
def test_icl_performance_predictor_tabpfn_not_installed(monkeypatch):
    """Test IclPerformancePredictor.predict returns unavailable when tabpfn is
    missing.
    """
    # GIVEN
    monkeypatch.setattr(icl_manager, "is_tabpfn_installed", lambda: False)
    predictor = icl_performance.IclPerformancePredictor()
    activities_json = _make_activities_json()

    # WHEN
    result = predictor.predict(activities_json)

    # THEN
    assert result["available"] is False
    assert "tabpfn" in result["reason"].lower()
    assert result["predicted_10k_minutes"] is None
    assert result["predicted_10k_label"] is None
    print("DONE: IclPerformancePredictor returns unavailable when tabpfn is missing")


@pytest.mark.mytral
def test_icl_rest_day_predictor_tabpfn_not_installed(monkeypatch):
    """Test IclRestDayPredictor.predict returns unavailable when tabpfn is missing."""
    # GIVEN
    monkeypatch.setattr(icl_manager, "is_tabpfn_installed", lambda: False)
    predictor = icl_rest_day.IclRestDayPredictor()
    activities_json = _make_activities_json()

    # WHEN
    result = predictor.predict(activities_json)

    # THEN
    assert result["available"] is False
    assert "tabpfn" in result["reason"].lower()
    assert result["should_rest"] is None
    assert result["label"] is None
    print("DONE: IclRestDayPredictor returns unavailable when tabpfn is missing")


@pytest.mark.mytral
def test_icl_anomaly_predictor_tabpfn_not_installed(monkeypatch):
    """Test IclAnomalyPredictor.predict returns unavailable when tabpfn is missing."""
    # GIVEN
    monkeypatch.setattr(icl_manager, "is_tabpfn_installed", lambda: False)
    predictor = icl_anomaly.IclAnomalyPredictor()
    activities_json = _make_activities_json()

    # WHEN
    result = predictor.predict(activities_json)

    # THEN
    assert result["available"] is False
    assert "tabpfn" in result["reason"].lower()
    assert result["is_anomaly"] is None
    assert result["label"] is None
    print("DONE: IclAnomalyPredictor returns unavailable when tabpfn is missing")


@pytest.mark.mytral
def test_minutes_to_label_format():
    """Test _minutes_to_label renders correct MM:SS and H:MM:SS formats."""
    # GIVEN / WHEN / THEN
    assert icl_performance._minutes_to_label(48.5) == "48:30"
    assert icl_performance._minutes_to_label(60.0) == "1:00:00"
    assert icl_performance._minutes_to_label(70.25) == "1:10:15"
    print("DONE: _minutes_to_label renders correct MM:SS and H:MM:SS formats")
