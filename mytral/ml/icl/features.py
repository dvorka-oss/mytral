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
"""Feature engineering utilities for ICL-based training predictions.

Transforms MyTraL activity JSON data into tabular feature matrices suitable
for TabPFN in-context learning.
"""

import math
from datetime import date
from datetime import timedelta

import pandas as pd

#
# Data format adapter
#


def build_activities_json_for_icl(activities: dict) -> dict:
    """Convert a dict of ActivityEntity objects to the ICL activities_json format.

    The ICL features expect the following layout::

        {
            "activities": {
                "2024": [
                    {"date": "2024-01-01", "distance": 10.2, "hr_max": 168,
                     "avg_hr": 145, "activity_type_key": "run", "intensity": "easy",
                     "duration_seconds": 3600, "race": False}
                ]
            },
            "sick": ["2024-02-10", "2024-02-11"]
        }

    Parameters
    ----------
    activities : dict
        ``{key: ActivityEntity}`` mapping returned by ``ds.all_activities()``.

    Returns
    -------
    dict
        ICL-ready dataset dictionary.
    """
    activities_by_year: dict[str, list] = {}
    sick_dates: list[str] = []

    for entity in activities.values():
        year_int = getattr(entity, "when_year", None)
        month_int = getattr(entity, "when_month", None)
        day_int = getattr(entity, "when_day", None)
        if not (year_int and month_int and day_int):
            continue

        date_str = f"{year_int}-{month_int:02d}-{day_int:02d}"
        year_str = str(year_int)
        activity_type_key = getattr(entity, "activity_type_key", "") or ""

        if activity_type_key == "sick":
            sick_dates.append(date_str)
            continue

        # distance is stored in meters in ActivityEntity
        distance_m = float(getattr(entity, "distance", 0) or 0)
        duration_s = int(getattr(entity, "duration_seconds", 0) or 0)
        max_hr = int(getattr(entity, "max_hr", 0) or 0)
        avg_hr_val = int(getattr(entity, "avg_hr", 0) or 0)
        intensity = getattr(entity, "intensity", "") or ""
        is_race = bool(getattr(entity, "race", False))

        if year_str not in activities_by_year:
            activities_by_year[year_str] = []

        activities_by_year[year_str].append(
            {
                "date": date_str,
                "distance": round(distance_m / 1000.0, 3),
                "hr_max": max_hr,
                "avg_hr": avg_hr_val,
                "activity_type_key": activity_type_key,
                "intensity": intensity,
                "duration_seconds": duration_s,
                "race": is_race,
            }
        )

    return {"activities": activities_by_year, "sick": sick_dates}


#
# Shared rolling-aggregate helpers
#


def _build_daily_aggregates(
    activities_json: dict, start: date, end: date
) -> tuple[dict, dict, dict, dict, dict, dict]:
    """Build per-day aggregate dictionaries from the activities_json.

    Returns
    -------
    tuple
        (daily_km, daily_sessions, daily_hr_max, daily_avg_hr,
         daily_duration_s, daily_run_pace)  keyed by ``date`` objects.
    """
    daily_km: dict[date, float] = {}
    daily_sessions: dict[date, int] = {}
    daily_hr_max: dict[date, float] = {}
    daily_avg_hr: dict[date, float] = {}
    daily_duration_s: dict[date, int] = {}
    daily_run_pace: dict[date, list[float]] = {}  # min/km values

    for _year_str, year_activities in activities_json.get("activities", {}).items():
        for act in year_activities if isinstance(year_activities, list) else []:
            act_date_str = act.get("date", "")
            if not act_date_str:
                continue
            try:
                act_date = date.fromisoformat(act_date_str)
            except ValueError:
                continue
            if act_date < start or act_date > end:
                continue

            dist_km = float(act.get("distance", 0) or 0)
            hr_max_val = float(act.get("hr_max", 0) or 0)
            avg_hr_val = float(act.get("avg_hr", 0) or 0)
            dur_s = int(act.get("duration_seconds", 0) or 0)
            sport = str(act.get("activity_type_key", "") or "")

            daily_km[act_date] = daily_km.get(act_date, 0.0) + dist_km
            daily_sessions[act_date] = daily_sessions.get(act_date, 0) + 1
            if hr_max_val > daily_hr_max.get(act_date, 0.0):
                daily_hr_max[act_date] = hr_max_val
            if avg_hr_val > 0:
                daily_avg_hr[act_date] = avg_hr_val
            daily_duration_s[act_date] = daily_duration_s.get(act_date, 0) + dur_s

            # collect per-km pace for run/walk/hike activities
            if sport in {"run", "walk", "hike", "trail"} and dist_km > 0 and dur_s > 0:
                pace_min_km = (dur_s / 60.0) / dist_km
                if act_date not in daily_run_pace:
                    daily_run_pace[act_date] = []
                daily_run_pace[act_date].append(pace_min_km)

    return (
        daily_km,
        daily_sessions,
        daily_hr_max,
        daily_avg_hr,
        daily_duration_s,
        daily_run_pace,
    )


def _rolling_km(daily_km: dict[date, float], current: date, days: int) -> float:
    """Return the rolling km sum over the preceding ``days`` days."""
    return sum(daily_km.get(current - timedelta(days=d), 0.0) for d in range(days))


def _consecutive_training_days(daily_sessions: dict[date, int], current: date) -> int:
    """Count consecutive days with at least one training session up to and including
    *current*.

    """
    count = 0
    d = current
    while daily_sessions.get(d, 0) > 0:
        count += 1
        d -= timedelta(days=1)
    return count


def _days_since_rest(daily_sessions: dict[date, int], current: date) -> int:
    """Return number of days since the last rest day (0 = today is a rest day)."""
    d = current
    count = 0
    while daily_sessions.get(d, 0) > 0:
        count += 1
        d -= timedelta(days=1)
    return count


#
# Illness risk features (use case 1)
#


def extract_sick_features(
    activities_json: dict,
    lookback_days: int = 180,
) -> pd.DataFrame:
    """Build a per-day feature DataFrame for illness risk prediction.

    Each row represents one calendar day.  Features encode recent training
    load and historical illness patterns that serve as the ICL context.

    Parameters
    ----------
    activities_json : dict
        Top-level MyTraL dataset dictionary.  Must contain an ``"activities"``
        key mapping year strings to activity dicts, and optionally a
        ``"sick"`` key with a list of ``"YYYY-MM-DD"`` date strings.
    lookback_days : int
        How many days of history to include in the feature matrix.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns: ``date``, ``sick`` (label, 0/1),
        ``km_7d``, ``km_14d``, ``sessions_7d``, ``hr_max_7d``,
        ``sick_lag_1`` … ``sick_lag_7``, ``year_day``, ``month``.
    """
    today = date.today()
    start = today - timedelta(days=lookback_days)

    daily_km, daily_sessions, daily_hr_max, _, _, _ = _build_daily_aggregates(
        activities_json, start, today
    )

    sick_dates: set[date] = set()
    for sick_str in activities_json.get("sick", []):
        try:
            sick_dates.add(date.fromisoformat(sick_str))
        except ValueError:
            continue

    rows = []
    window = [start + timedelta(days=i) for i in range(lookback_days + 1)]

    for current in window:
        km_7d = _rolling_km(daily_km, current, 7)
        km_14d = _rolling_km(daily_km, current, 14)
        sessions_7d = sum(
            daily_sessions.get(current - timedelta(days=d), 0) for d in range(7)
        )
        hr_max_7d = max(
            (daily_hr_max.get(current - timedelta(days=d), 0.0) for d in range(7)),
            default=0.0,
        )
        sick_lags = {
            f"sick_lag_{i}": 1 if (current - timedelta(days=i)) in sick_dates else 0
            for i in range(1, 8)
        }
        row: dict = {
            "date": current.isoformat(),
            "sick": 1 if current in sick_dates else 0,
            "km_7d": round(km_7d, 2),
            "km_14d": round(km_14d, 2),
            "sessions_7d": sessions_7d,
            "hr_max_7d": round(hr_max_7d, 1),
            "year_day": current.timetuple().tm_yday,
            "month": current.month,
        }
        row.update(sick_lags)
        rows.append(row)

    return pd.DataFrame(rows)


SICK_FEATURE_COLS = [
    "km_7d",
    "km_14d",
    "sessions_7d",
    "hr_max_7d",
    "sick_lag_1",
    "sick_lag_2",
    "sick_lag_3",
    "sick_lag_4",
    "sick_lag_5",
    "sick_lag_6",
    "sick_lag_7",
    "year_day",
    "month",
]
"""Ordered list of feature column names used for illness risk prediction."""


def predict_row_for_today(activities_json: dict) -> pd.DataFrame:
    """Build a single-row feature DataFrame representing today.

    Used to generate the X_test input for the illness risk predictor.

    Parameters
    ----------
    activities_json : dict
        Top-level MyTraL dataset dictionary.

    Returns
    -------
    pd.DataFrame
        Single-row DataFrame with only the columns in ``SICK_FEATURE_COLS``.
    """
    df = extract_sick_features(activities_json, lookback_days=30)
    if df.empty:
        # return a row of zeros if there is no data
        return pd.DataFrame([{col: 0 for col in SICK_FEATURE_COLS}])
    today_row = df[df["date"] == date.today().isoformat()]
    if today_row.empty:
        today_row = df.tail(1)
    return today_row[SICK_FEATURE_COLS].reset_index(drop=True)


def sufficient_data(df: pd.DataFrame, min_sick_days: int = 3) -> bool:
    """Return True if the DataFrame has enough labelled illness days to train.

    Parameters
    ----------
    df : pd.DataFrame
        Feature DataFrame produced by ``extract_sick_features``.
    min_sick_days : int
        Minimum number of sick days required for a meaningful prediction.

    Returns
    -------
    bool
        True when there is sufficient training data.
    """
    if df.empty:
        return False
    n_sick = int(df["sick"].sum()) if "sick" in df.columns else 0
    return n_sick >= min_sick_days and not math.isnan(n_sick)


#
# Fatigue / readiness features (use case 3)
#


def extract_fatigue_features(
    activities_json: dict,
    lookback_days: int = 90,
) -> pd.DataFrame:
    """Build a per-day feature DataFrame for fatigue / readiness prediction.

    Labels are derived heuristically from training stress balance (TSB).

    Parameters
    ----------
    activities_json : dict
        Top-level MyTraL dataset dictionary.
    lookback_days : int
        How many days of history to include.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns in ``FATIGUE_FEATURE_COLS`` plus ``fatigue_class``.
    """
    today = date.today()
    start = today - timedelta(days=lookback_days)

    daily_km, daily_sessions, daily_hr_max, _, _, _ = _build_daily_aggregates(
        activities_json, start, today
    )

    sick_dates: set[date] = set()
    for sick_str in activities_json.get("sick", []):
        try:
            sick_dates.add(date.fromisoformat(sick_str))
        except ValueError:
            continue

    rows = []
    window = [start + timedelta(days=i) for i in range(lookback_days + 1)]

    for current in window:
        atl_7d = _rolling_km(daily_km, current, 7)
        ctl_42d = _rolling_km(daily_km, current, 42) / 6.0  # normalise to weekly avg
        tsb = ctl_42d - atl_7d
        sessions_7d = sum(
            daily_sessions.get(current - timedelta(days=d), 0) for d in range(7)
        )
        consec = _consecutive_training_days(daily_sessions, current)
        days_rest = _days_since_rest(daily_sessions, current)
        hr_max_7d = max(
            (daily_hr_max.get(current - timedelta(days=d), 0.0) for d in range(7)),
            default=0.0,
        )
        sick_lag_1 = 1 if (current - timedelta(days=1)) in sick_dates else 0
        sick_lag_2 = 1 if (current - timedelta(days=2)) in sick_dates else 0
        sick_lag_3 = 1 if (current - timedelta(days=3)) in sick_dates else 0

        # derive label from TSB
        if tsb < -15:
            fatigue_class = "overreaching"
        elif tsb < 0:
            fatigue_class = "fatigued"
        elif tsb < 10:
            fatigue_class = "normal"
        else:
            fatigue_class = "fresh"

        rows.append(
            {
                "date": current.isoformat(),
                "atl_7d": round(atl_7d, 2),
                "ctl_42d": round(ctl_42d, 2),
                "tsb": round(tsb, 2),
                "sessions_7d": sessions_7d,
                "consecutive_training_days": consec,
                "days_since_rest": days_rest,
                "hr_max_7d": round(hr_max_7d, 1),
                "sick_lag_1": sick_lag_1,
                "sick_lag_2": sick_lag_2,
                "sick_lag_3": sick_lag_3,
                "year_day": current.timetuple().tm_yday,
                "month": current.month,
                "fatigue_class": fatigue_class,
            }
        )

    return pd.DataFrame(rows)


FATIGUE_FEATURE_COLS = [
    "atl_7d",
    "ctl_42d",
    "tsb",
    "sessions_7d",
    "consecutive_training_days",
    "days_since_rest",
    "hr_max_7d",
    "sick_lag_1",
    "sick_lag_2",
    "sick_lag_3",
    "year_day",
    "month",
]
"""Ordered list of feature column names used for fatigue prediction."""


#
# Optimal rest day features (use case 4)
#


def extract_rest_day_features(
    activities_json: dict,
    lookback_days: int = 90,
) -> pd.DataFrame:
    """Build a per-day feature DataFrame for rest day prediction.

    The label ``should_rest`` is 1 when the FOLLOWING day had no activity OR
    when that day preceded a sick event within 2 days.

    Parameters
    ----------
    activities_json : dict
        Top-level MyTraL dataset dictionary.
    lookback_days : int
        How many days of history to include.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns in ``REST_DAY_FEATURE_COLS`` plus ``should_rest``.
    """
    today = date.today()
    start = today - timedelta(days=lookback_days)

    daily_km, daily_sessions, daily_hr_max, _, _, _ = _build_daily_aggregates(
        activities_json, start, today
    )

    sick_dates: set[date] = set()
    for sick_str in activities_json.get("sick", []):
        try:
            sick_dates.add(date.fromisoformat(sick_str))
        except ValueError:
            continue

    rows = []
    # exclude last row: we cannot know tomorrow's rest status for today
    window = [start + timedelta(days=i) for i in range(lookback_days)]

    for current in window:
        atl_7d = _rolling_km(daily_km, current, 7)
        ctl_42d = _rolling_km(daily_km, current, 42) / 6.0
        tsb = ctl_42d - atl_7d
        sessions_7d = sum(
            daily_sessions.get(current - timedelta(days=d), 0) for d in range(7)
        )
        consec = _consecutive_training_days(daily_sessions, current)
        days_rest = _days_since_rest(daily_sessions, current)
        hr_max_7d = max(
            (daily_hr_max.get(current - timedelta(days=d), 0.0) for d in range(7)),
            default=0.0,
        )
        km_7d = _rolling_km(daily_km, current, 7)
        km_14d = _rolling_km(daily_km, current, 14)
        sick_lag_1 = 1 if (current - timedelta(days=1)) in sick_dates else 0
        sick_lag_2 = 1 if (current - timedelta(days=2)) in sick_dates else 0
        sick_lag_3 = 1 if (current - timedelta(days=3)) in sick_dates else 0

        tomorrow = current + timedelta(days=1)
        pre_sick = any((current + timedelta(days=k)) in sick_dates for k in range(1, 3))
        should_rest = 1 if (daily_sessions.get(tomorrow, 0) == 0 or pre_sick) else 0

        rows.append(
            {
                "date": current.isoformat(),
                "km_7d": round(km_7d, 2),
                "km_14d": round(km_14d, 2),
                "atl_7d": round(atl_7d, 2),
                "ctl_42d": round(ctl_42d, 2),
                "tsb": round(tsb, 2),
                "sessions_7d": sessions_7d,
                "consecutive_training_days": consec,
                "days_since_rest": days_rest,
                "hr_max_7d": round(hr_max_7d, 1),
                "sick_lag_1": sick_lag_1,
                "sick_lag_2": sick_lag_2,
                "sick_lag_3": sick_lag_3,
                "year_day": current.timetuple().tm_yday,
                "month": current.month,
                "should_rest": should_rest,
            }
        )

    return pd.DataFrame(rows)


REST_DAY_FEATURE_COLS = [
    "km_7d",
    "km_14d",
    "atl_7d",
    "ctl_42d",
    "tsb",
    "sessions_7d",
    "consecutive_training_days",
    "days_since_rest",
    "hr_max_7d",
    "sick_lag_1",
    "sick_lag_2",
    "sick_lag_3",
    "year_day",
    "month",
]
"""Ordered list of feature column names used for rest day prediction."""


#
# Anomaly detection features (use case 5)
#


def extract_anomaly_features(
    activities_json: dict,
    lookback_days: int = 180,
) -> pd.DataFrame:
    """Build a per-activity feature DataFrame for anomaly detection.

    Each row represents one individual activity.  The label ``is_anomaly``
    is derived by comparing the activity's metrics against rolling baselines.

    Parameters
    ----------
    activities_json : dict
        Top-level MyTraL dataset dictionary.
    lookback_days : int
        How many days of history to include.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns in ``ANOMALY_FEATURE_COLS`` plus ``is_anomaly``.
    """
    today = date.today()
    start = today - timedelta(days=lookback_days)

    # collect all activity rows first for rolling-baseline computation
    act_rows: list[dict] = []

    for _year_str, year_activities in activities_json.get("activities", {}).items():
        for act in year_activities if isinstance(year_activities, list) else []:
            act_date_str = act.get("date", "")
            if not act_date_str:
                continue
            try:
                act_date = date.fromisoformat(act_date_str)
            except ValueError:
                continue
            if act_date < start or act_date > today:
                continue

            dist_km = float(act.get("distance", 0) or 0)
            hr_max_val = float(act.get("hr_max", 0) or 0)
            avg_hr_val = float(act.get("avg_hr", 0) or 0)
            dur_s = float(act.get("duration_seconds", 0) or 0)
            avg_speed = (dist_km / (dur_s / 3600.0)) if dur_s > 0 else 0.0

            act_rows.append(
                {
                    "date": act_date,
                    "date_str": act_date_str,
                    "distance_km": dist_km,
                    "hr_max": hr_max_val,
                    "avg_hr": avg_hr_val,
                    "duration_seconds": dur_s,
                    "avg_speed_kmh": round(avg_speed, 2),
                    "year_day": act_date.timetuple().tm_yday,
                    "month": act_date.month,
                }
            )

    if not act_rows:
        return pd.DataFrame()

    # sort by date to compute running statistics
    act_rows.sort(key=lambda r: r["date"])

    # compute rolling mean/std for distance and hr using a 30-activity window
    distances = [r["distance_km"] for r in act_rows]
    hrs = [r["hr_max"] for r in act_rows]

    rows = []
    for i, row in enumerate(act_rows):
        window_start = max(0, i - 30)
        recent_dist = distances[window_start:i] if i > 0 else []
        recent_hrs = hrs[window_start:i] if i > 0 else []

        mean_dist = (
            sum(recent_dist) / len(recent_dist) if recent_dist else row["distance_km"]
        )
        std_dist = (
            math.sqrt(sum((x - mean_dist) ** 2 for x in recent_dist) / len(recent_dist))
            if len(recent_dist) > 1
            else 0.0
        )
        mean_hr = sum(recent_hrs) / len(recent_hrs) if recent_hrs else 0.0

        is_anomaly = 0
        if std_dist > 0 and abs(row["distance_km"] - mean_dist) > 2 * std_dist:
            is_anomaly = 1
        if row["hr_max"] > 200:
            is_anomaly = 1
        if mean_hr > 0 and row["hr_max"] > mean_hr * 1.2:
            is_anomaly = 1

        rows.append(
            {
                "date": row["date_str"],
                "distance_km": row["distance_km"],
                "hr_max": row["hr_max"],
                "avg_hr": row["avg_hr"],
                "duration_seconds": row["duration_seconds"],
                "avg_speed_kmh": row["avg_speed_kmh"],
                "year_day": row["year_day"],
                "month": row["month"],
                "is_anomaly": is_anomaly,
            }
        )

    return pd.DataFrame(rows)


ANOMALY_FEATURE_COLS = [
    "distance_km",
    "hr_max",
    "avg_hr",
    "duration_seconds",
    "avg_speed_kmh",
    "year_day",
    "month",
]
"""Ordered list of feature column names used for anomaly detection."""


#
# Race performance features (use case 2)
#


def _riegel_10k_minutes(distance_km: float, pace_min_km: float) -> float:
    """Estimate 10K finish time using the Riegel formula.

    Parameters
    ----------
    distance_km : float
        Actual race or training distance in km.
    pace_min_km : float
        Average pace in minutes per km.

    Returns
    -------
    float
        Estimated 10K finish time in minutes, or 0.0 if inputs are invalid.
    """
    if distance_km <= 0 or pace_min_km <= 0:
        return 0.0
    actual_time = distance_km * pace_min_km
    # Riegel: T2 = T1 * (D2 / D1) ^ 1.06
    predicted_time = actual_time * (10.0 / distance_km) ** 1.06
    return round(predicted_time, 2)


def extract_performance_features(
    activities_json: dict,
    lookback_days: int = 365,
) -> pd.DataFrame:
    """Build a per-run-activity feature DataFrame for race performance prediction.

    Only run/jog activities with at least 1 km and positive duration are included.
    The label is the Riegel-estimated 10K finish time in minutes.

    Parameters
    ----------
    activities_json : dict
        Top-level MyTraL dataset dictionary.
    lookback_days : int
        How many days of history to include.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns in ``PERFORMANCE_FEATURE_COLS`` plus ``riegel_10k_min``.
    """
    today = date.today()
    start = today - timedelta(days=lookback_days)

    daily_km, daily_sessions, _, _, _, _ = _build_daily_aggregates(
        activities_json, start, today
    )

    rows = []

    for _year_str, year_activities in activities_json.get("activities", {}).items():
        for act in year_activities if isinstance(year_activities, list) else []:
            act_date_str = act.get("date", "")
            if not act_date_str:
                continue
            try:
                act_date = date.fromisoformat(act_date_str)
            except ValueError:
                continue
            if act_date < start or act_date > today:
                continue

            sport = str(act.get("activity_type_key", "") or "")
            if sport not in {"run", "walk", "trail", "hike"}:
                continue

            dist_km = float(act.get("distance", 0) or 0)
            dur_s = float(act.get("duration_seconds", 0) or 0)
            if dist_km < 1.0 or dur_s <= 0:
                continue

            hr_max_val = float(act.get("hr_max", 0) or 0)
            pace_min_km = (dur_s / 60.0) / dist_km
            week_vol = _rolling_km(daily_km, act_date, 7)
            month_vol = _rolling_km(daily_km, act_date, 30)
            riegel = _riegel_10k_minutes(dist_km, pace_min_km)

            rows.append(
                {
                    "date": act_date_str,
                    "distance_km": round(dist_km, 2),
                    "avg_pace_min_km": round(pace_min_km, 3),
                    "hr_max": hr_max_val,
                    "week_volume_km": round(week_vol, 2),
                    "month_volume_km": round(month_vol, 2),
                    "year_day": act_date.timetuple().tm_yday,
                    "month": act_date.month,
                    "riegel_10k_min": riegel,
                }
            )

    return pd.DataFrame(rows)


PERFORMANCE_FEATURE_COLS = [
    "distance_km",
    "avg_pace_min_km",
    "hr_max",
    "week_volume_km",
    "month_volume_km",
    "year_day",
    "month",
]
"""Ordered list of feature column names used for race performance prediction."""
