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
"""Banister fitness-fatigue-performance model.

References
----------
Banister E.W., Calvert T.W., Savage N.V., Bach T. (1975) — *A systems model of
training for athletic performance*, Australian Journal of Sports Medicine.

Busso T. (2002) — refinements with negative training impulse for recovery days.
"""

import datetime
import math

from mytral import commons
from mytral.metrics.banister import _entities
from mytral.metrics.banister import _impact as _impact_mod
from mytral.metrics.banister import _insights as _insights_mod

# re-export public symbols from _entities
BanisterParams = _entities.BanisterParams
BanisterRow = _entities.BanisterRow
Annotation = _entities.Annotation
InsightCard = _entities.InsightCard
ActivityImpact = _entities.ActivityImpact


def _ema_step(
    previous: float,
    daily_value: float,
    time_constant_days: float,
) -> float:
    """Single exponential moving average step."""
    decay = math.exp(-1.0 / time_constant_days)
    return previous * decay + daily_value * (1.0 - decay)


def _banister_step(
    prev_fitness: float | None,
    prev_fatigue: float | None,
    trimp_val: float,
    params: _entities.BanisterParams,
) -> tuple[float, float, float]:
    """Compute one day's Banister state from previous state and today's TRIMP.

    Returns (fitness, fatigue, performance).
    """
    w_pos = max(0.0, trimp_val - params.w_recovery_threshold)
    w_neg = max(0.0, params.w_recovery_threshold - trimp_val)

    if prev_fitness is None:
        fitness = trimp_val
        fatigue = trimp_val
    else:
        fitness_pos = _ema_step(prev_fitness, w_pos, params.tau1_days)
        fitness_neg = params.gamma * w_neg * (1.0 - math.exp(-1.0 / params.tau1r_days))
        fitness = fitness_pos - fitness_neg

        fatigue_pos = _ema_step(prev_fatigue, w_pos, params.tau2_days)
        fatigue_neg = params.gamma * w_neg * (1.0 - math.exp(-1.0 / params.tau2r_days))
        fatigue = fatigue_pos - fatigue_neg

    performance = params.k1 * fitness - params.k2 * fatigue
    return fitness, fatigue, performance


def run(
    daily_trimp: list[tuple[datetime.date, float]],
    params: _entities.BanisterParams | None = None,
) -> list[_entities.BanisterRow]:
    """Forward-run the Banister filter over the input series."""
    if params is None:
        params = _entities.BanisterParams()

    if not daily_trimp:
        return []

    rows: list[_entities.BanisterRow] = []
    prev_fitness: float | None = None
    prev_fatigue: float | None = None

    for date_val, trimp_val in daily_trimp:
        fitness, fatigue, performance = _banister_step(
            prev_fitness, prev_fatigue, trimp_val, params
        )
        rows.append(
            _entities.BanisterRow(
                date=date_val,
                trimp=trimp_val,
                fitness=fitness,
                fatigue=fatigue,
                performance=performance,
            )
        )
        prev_fitness = fitness
        prev_fatigue = fatigue

    return rows


def project(
    rows: list[_entities.BanisterRow],
    days: int,
    params: _entities.BanisterParams | None = None,
) -> list[_entities.BanisterRow]:
    """Continue the EMAs forward assuming the last-28-day mean daily load repeats."""
    if params is None:
        params = _entities.BanisterParams()

    if not rows:
        return []

    lookback = min(28, len(rows))
    mean_load = sum(r.trimp for r in rows[-lookback:]) / lookback

    last = rows[-1]
    projection: list[_entities.BanisterRow] = []
    prev_fitness = last.fitness
    prev_fatigue = last.fatigue
    current_date = last.date

    for _ in range(days):
        current_date += datetime.timedelta(days=1)
        fitness, fatigue, performance = _banister_step(
            prev_fitness, prev_fatigue, mean_load, params
        )
        projection.append(
            _entities.BanisterRow(
                date=current_date,
                trimp=mean_load,
                fitness=fitness,
                fatigue=fatigue,
                performance=performance,
            )
        )
        prev_fitness = fitness
        prev_fatigue = fatigue

    return projection


def _find_peak_annotation(
    rows: list[_entities.BanisterRow],
) -> _entities.Annotation | None:
    """Find the best performance day annotation."""
    best_perf = -float("inf")
    best_date: datetime.date | None = None
    for row in rows:
        if row.performance > best_perf:
            best_perf = row.performance
            best_date = row.date
    if best_date is not None and best_perf > 0:
        return _entities.Annotation(
            id="peak-form",
            date=best_date,
            kind="peak",
            label=(
                f"Peak Race Form {best_date.isoformat()} "
                f"(performance = {best_perf:+.0f})"
            ),
            value=best_perf,
        )
    return None


def _find_fitness_pb_annotation(
    rows: list[_entities.BanisterRow],
) -> _entities.Annotation | None:
    """Find the best fitness day annotation."""
    best_fit = -float("inf")
    best_date: datetime.date | None = None
    for row in rows:
        if row.fitness > best_fit:
            best_fit = row.fitness
            best_date = row.date
    if best_date is not None:
        return _entities.Annotation(
            id="fitness-pb",
            date=best_date,
            kind="fitness_pb",
            label=(
                f"New Fitness PB {best_date.isoformat()} (fitness = {best_fit:.0f})"
            ),
            value=best_fit,
        )
    return None


def _find_overreach_annotations(
    rows: list[_entities.BanisterRow],
) -> list[_entities.Annotation]:
    """Detect overreaching episodes: sustained performance below floor."""
    annotations: list[_entities.Annotation] = []
    i = 0
    episode_index = 0
    while i < len(rows):
        if rows[i].performance < commons.OVERREACH_PERFORMANCE_FLOOR:
            start = i
            while (
                i < len(rows)
                and rows[i].performance < commons.OVERREACH_PERFORMANCE_FLOOR
            ):
                i += 1
            length = i - start
            if length >= commons.OVERREACH_MIN_DAYS:
                min_perf = min(r.performance for r in rows[start:i])
                mid_date = rows[start + length // 2].date
                episode_index += 1
                annotations.append(
                    _entities.Annotation(
                        id=f"overreach-{episode_index}",
                        date=mid_date,
                        kind="overreach",
                        label=(
                            f"Overreaching {mid_date.isoformat()} "
                            f"({length}d, perf min {min_perf:+.0f})"
                        ),
                        value=min_perf,
                    )
                )
        else:
            i += 1
    return annotations


def annotate(rows: list[_entities.BanisterRow]) -> list[_entities.Annotation]:
    """Mark peaks, overreaches and personal bests on the timeline."""
    if not rows:
        return []

    annotations: list[_entities.Annotation] = []
    peak = _find_peak_annotation(rows)
    if peak:
        annotations.append(peak)
    fitness_pb = _find_fitness_pb_annotation(rows)
    if fitness_pb:
        annotations.append(fitness_pb)
    annotations.extend(_find_overreach_annotations(rows))
    return annotations


# re-export insight builders and compute_insights from _insights
_build_state_card = _insights_mod._build_state_card
_build_best_form_card = _insights_mod._build_best_form_card
_build_overreaching_card = _insights_mod._build_overreaching_card
_build_pbs_card = _insights_mod._build_pbs_card
_build_projection_card = _insights_mod._build_projection_card
_build_race_window_card = _insights_mod._build_race_window_card
compute_insights = _insights_mod.compute_insights

# re-export impact analysis from _impact
analyze_activity = _impact_mod.analyze_activity
