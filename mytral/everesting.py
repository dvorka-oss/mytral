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
"""Everesting - sport-aware vertical accumulation toward Mt. Everest (8848 m).

Pure computation helpers shared by the dashboard card, the elevation charts and
the single-activity achievement badges. No I/O, no Flask, no persistence.
"""

import dataclasses
import datetime
import math

from mytral import commons
from mytral.backends import entities


@dataclasses.dataclass
class EverestingProgress:
    """Progress of a single meta sport toward Everest within one period."""

    meta_sport: str | None
    meta_sport_label: str
    period: commons.StatsPeriod
    climbed_m: int
    target_m: int
    pct: float
    summited: bool
    eta_days: int | None


def _activity_date(activity: entities.ActivityEntity) -> datetime.date | None:
    """Return the activity's calendar date, or None when it is incomplete."""
    if not (activity.when_year and activity.when_month and activity.when_day):
        return None
    try:
        return datetime.date(activity.when_year, activity.when_month, activity.when_day)
    except ValueError:
        return None


def in_period(
    activity: entities.ActivityEntity,
    period: commons.StatsPeriod,
    today: datetime.date,
) -> bool:
    """Is the activity within the current day / week / month / year up to today?"""
    day = _activity_date(activity)
    if day is None or day > today:
        return False
    if period == commons.StatsPeriod.DAY:
        return day == today
    if period == commons.StatsPeriod.WEEK:
        start_of_week = today - datetime.timedelta(days=today.weekday())
        return day >= start_of_week
    if period == commons.StatsPeriod.MONTH:
        return day.year == today.year and day.month == today.month
    if period == commons.StatsPeriod.YEAR:
        return day.year == today.year
    return False


def _days_elapsed(period: commons.StatsPeriod, today: datetime.date) -> int:
    """Number of days elapsed in the period so far (>= 1), for pace/ETA."""
    if period == commons.StatsPeriod.DAY:
        return 1
    if period == commons.StatsPeriod.WEEK:
        return today.weekday() + 1
    if period == commons.StatsPeriod.MONTH:
        return today.day
    if period == commons.StatsPeriod.YEAR:
        return today.timetuple().tm_yday
    return 1


def _climbing_activity_type_keys(meta_sport: str | None) -> set[str]:
    """Activity type keys that count as climbing for the given meta sport.

    ``None`` means the union of all climbing meta sports.
    """
    if meta_sport is None:
        keys: set[str] = set()
        for meta in commons.EVERESTING_CLIMBING_META_SPORTS:
            keys.update(commons.AT_TAXONOMY.get(meta, []))
        return keys
    return set(commons.AT_TAXONOMY.get(meta_sport, []))


def climbing_activities(
    activities: list[entities.ActivityEntity], meta_sport: str | None
) -> list[entities.ActivityEntity]:
    """Filter activities to those of the given climbing meta sport."""
    keys = _climbing_activity_type_keys(meta_sport)
    return [a for a in activities if a.activity_type_key in keys]


def climbed_meters(
    activities: list[entities.ActivityEntity],
    meta_sport: str | None,
    period: commons.StatsPeriod,
    today: datetime.date,
) -> int:
    """Total elevation gain climbed by a meta sport within the period."""
    return sum(
        a.elevation_gain
        for a in climbing_activities(activities, meta_sport)
        if in_period(a, period, today)
    )


def top_climbing_meta_sport(
    activities: list[entities.ActivityEntity], today: datetime.date
) -> str | None:
    """Climbing meta sport with the most vertical this year, or None."""
    best_meta: str | None = None
    best_m = 0
    for meta in commons.EVERESTING_CLIMBING_META_SPORTS:
        meters = climbed_meters(activities, meta, commons.StatsPeriod.YEAR, today)
        if meters > best_m:
            best_m = meters
            best_meta = meta
    return best_meta


def _meta_sport_label(meta_sport: str | None) -> str:
    """Human label for a meta sport (or the all-sports roll-up)."""
    if meta_sport is None:
        return "All climbing"
    return commons.M_AT_DISPLAY_NAMES.get(meta_sport, meta_sport)


def progress(
    activities: list[entities.ActivityEntity],
    meta_sport: str | None,
    period: commons.StatsPeriod,
    today: datetime.date,
) -> EverestingProgress:
    """Build the Everesting progress for a meta sport within a period."""
    climbed = climbed_meters(activities, meta_sport, period, today)
    target = commons.EVERESTING_M
    pct = climbed / target * 100.0 if target else 0.0
    summited = climbed >= target

    eta_days: int | None = None
    if not summited and climbed > 0 and period != commons.StatsPeriod.DAY:
        rate = climbed / _days_elapsed(period, today)
        if rate > 0:
            eta_days = math.ceil((target - climbed) / rate)

    return EverestingProgress(
        meta_sport=meta_sport,
        meta_sport_label=_meta_sport_label(meta_sport),
        period=period,
        climbed_m=climbed,
        target_m=target,
        pct=pct,
        summited=summited,
        eta_days=eta_days,
    )


def dashboard_periods(
    activities: list[entities.ActivityEntity], today: datetime.date
) -> dict[str, EverestingProgress]:
    """Everesting progress for day/week/month/year of the top climbing sport.

    Returns an empty dict when there is no climbing data (card is hidden).
    """
    meta_sport = top_climbing_meta_sport(activities, today)
    if meta_sport is None:
        return {}
    periods = {
        "day": commons.StatsPeriod.DAY,
        "week": commons.StatsPeriod.WEEK,
        "month": commons.StatsPeriod.MONTH,
        "year": commons.StatsPeriod.YEAR,
    }
    return {
        name: progress(activities, meta_sport, period, today)
        for name, period in periods.items()
    }


def lifetime_vertical_m(activities: list[entities.ActivityEntity]) -> int:
    """Total elevation gain climbed across a lifetime of activities."""
    return sum(a.elevation_gain for a in activities)


def everests_climbed(total_m: int) -> float:
    """How many Everests the total vertical represents."""
    return total_m / commons.EVERESTING_M if commons.EVERESTING_M else 0.0
