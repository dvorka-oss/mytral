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
"""Per-activity impact analysis for the Banister model."""

import datetime

from mytral import commons
from mytral.backends import entities as entities_mod
from mytral.metrics.banister import _entities


def _compute_impact_deltas(
    post_row: _entities.BanisterRow, pre_row: _entities.BanisterRow | None
) -> tuple[float, float, float]:
    """Compute delta fitness, fatigue, performance from pre/post rows."""
    pre_fit = pre_row.fitness if pre_row else 0.0
    pre_fat = pre_row.fatigue if pre_row else 0.0
    pre_perf = pre_row.performance if pre_row else 0.0
    return (
        post_row.fitness - pre_fit,
        post_row.fatigue - pre_fat,
        post_row.performance - pre_perf,
    )


def _compute_eta_fresh(projection: list[_entities.BanisterRow]) -> int:
    """Scan projection for first day where performance > 0."""
    for i, p in enumerate(projection):
        if p.performance > 0:
            return i + 1
    return 0


def _compute_recovery_days(
    rows: list[_entities.BanisterRow],
    activity_idx: int,
) -> int:
    """Scan forward in historical rows for days until performance > 0.

    Returns days until recovery, or 0 if already fresh at activity time.
    """
    if rows[activity_idx].performance > 0:
        return 0
    for offset in range(1, len(rows) - activity_idx):
        if rows[activity_idx + offset].performance > 0:
            return offset
    return 0


def _find_activity_index(
    rows: list[_entities.BanisterRow], activity_date: datetime.date
) -> int | None:
    """Return the index of a row matching the given date, or None."""
    for i, row in enumerate(rows):
        if row.date == activity_date:
            return i
    return None


def _build_impact_benefits(
    post_row: _entities.BanisterRow, delta_fitness: float
) -> list[str]:
    """Build benefits list for activity impact."""
    benefits: list[str] = []
    if delta_fitness > 0:
        pct = delta_fitness / max(post_row.fitness, 1.0) * 100
        benefits.append(
            f"Estimated +{delta_fitness:.0f} fitness over next 42 days "
            f"({pct:.1f}% of current)."
        )
    if post_row.trimp > 0:
        benefits.append(f"Training stimulus delivered: TRIMP {post_row.trimp:.0f}.")
    return benefits


def _build_impact_risks(
    post_row: _entities.BanisterRow,
    pre_row: _entities.BanisterRow | None,
    delta_fatigue: float,
) -> list[str]:
    """Build risks list for activity impact."""
    risks: list[str] = []
    if delta_fatigue > 0 and pre_row:
        risks.append(
            f"Adds {delta_fatigue:.0f} fatigue on a day you already had "
            f"fatigue {pre_row.fatigue:.0f}."
        )
    if post_row.performance < -20.0:
        risks.append("Pushes you into OVERREACHED zone — highest injury-risk window.")
    elif post_row.performance < 0.0:
        risks.append("Pushes you into TIRED zone.")
    return risks


def _build_impact_context(
    rows: list[_entities.BanisterRow], activity_date: datetime.date
) -> list[str]:
    """Build context list for activity impact (hard-session density)."""
    context: list[str] = []
    window_start = activity_date - datetime.timedelta(days=commons.HARD_DENSITY_DAYS)
    hard_count = sum(
        1
        for r in rows
        if r.date >= window_start
        and r.date <= activity_date
        and r.trimp > commons.HARD_TRIMP_THRESHOLD
    )
    if hard_count >= commons.HARD_DENSITY_COUNT:
        context.append(
            f"This is your {hard_count}th hard session in "
            f"{commons.HARD_DENSITY_DAYS} days — at the upper end of "
            f"sustainable density."
        )
    return context


def _build_impact_recommendation(
    post_row: _entities.BanisterRow,
    context: list[str],
    eta_fresh_days: int,
) -> str:
    """Build recommendation string for activity impact."""
    parts: list[str] = []
    if post_row.performance < 0:
        parts.append("Tomorrow: easy Z1-Z2 only, TRIMP target ≤ 40.")
    if context:
        parts.append("Next hard session: ≥ 48h gap recommended.")
    if eta_fresh_days > 0:
        parts.append(f"Recovery ETA to fresh (TSB > 0): {eta_fresh_days} days.")
    if not parts:
        parts.append("Load is within sustainable range.")
    return " ".join(parts)


def _find_pre_post_rows(
    rows: list[_entities.BanisterRow], activity_date: datetime.date
) -> tuple[_entities.BanisterRow | None, _entities.BanisterRow | None]:
    """Find the pre- and post-activity Banister rows."""
    for i, row in enumerate(rows):
        if row.date == activity_date:
            pre_row = rows[i - 1] if i > 0 else None
            return pre_row, row
    return None, None


def _empty_impact(message: str = "") -> _entities.ActivityImpact:
    """Return an empty _entities.ActivityImpact with an optional message."""
    return _entities.ActivityImpact(
        benefits=[],
        risks=[],
        context=[],
        recommendation=message or "No Banister data available.",
        pre_row=None,
        post_row=None,
        eta_fresh_days=0,
        delta_fitness=0.0,
        delta_fatigue=0.0,
        delta_performance=0.0,
    )


def analyze_activity(
    activity: entities_mod.ActivityEntity,
    rows: list[_entities.BanisterRow],
    projection: list[_entities.BanisterRow],
    pre_window_days: int = 7,
    post_window_days: int = 7,
) -> _entities.ActivityImpact:
    """Build the per-activity benefits/risks/recommendation view."""
    activity_date = datetime.date(
        activity.when_year, activity.when_month, activity.when_day
    )
    pre_row, post_row = _find_pre_post_rows(rows, activity_date)
    if post_row is None:
        return _empty_impact("No Banister data available for this activity date.")

    d_fit, d_fat, d_perf = _compute_impact_deltas(post_row, pre_row)
    activity_idx = _find_activity_index(rows, activity_date)
    eta = _compute_recovery_days(rows, activity_idx) if activity_idx is not None else 0
    ctx = _build_impact_context(rows, activity_date)
    return _entities.ActivityImpact(
        benefits=_build_impact_benefits(post_row, d_fit),
        risks=_build_impact_risks(post_row, pre_row, d_fat),
        context=ctx,
        recommendation=_build_impact_recommendation(post_row, ctx, eta),
        pre_row=pre_row,
        post_row=post_row,
        eta_fresh_days=eta,
        delta_fitness=d_fit,
        delta_fatigue=d_fat,
        delta_performance=d_perf,
    )
