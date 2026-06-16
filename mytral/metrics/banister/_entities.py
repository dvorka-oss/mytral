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
"""Shared dataclass entities for the Banister fitness-fatigue-performance model.

This module is separate from ``__init__.py`` to avoid circular imports:
``_impact.py`` and ``_insights.py`` need these classes, and ``__init__.py``
imports both submodules for re-export.
"""

import dataclasses
import datetime


def _classify_performance(performance: float) -> str:
    """Classify performance value into a one-word label."""
    if performance > 20.0:
        return "fresh"
    if performance >= 0.0:
        return "optimal"
    if performance >= -20.0:
        return "tired"
    return "overreached"


@dataclasses.dataclass(frozen=True)
class BanisterParams:
    """Banister model parameters.

    Parameters
    ----------
    tau1_days : float
        Fitness decay time constant (days). Default 42.0 (long-term
        adaptation window). The Morton et al. 1990 paper illustration
        used 45 days; these are individual-specific parameters
        (v2 will fit from race history).
    tau2_days : float
        Fatigue decay time constant (days). Default 7.0 (short-term
        fatigue window). The Morton et al. 1990 illustration used
        15 days.
    tau1r_days : float
        Recovery fitness time constant (days). Default 14.0 (Busso 2002).
    tau2r_days : float
        Recovery fatigue time constant (days). Default 3.0 (Busso 2002).
    k1 : float
        Fitness gain coefficient. Default 1.0.
    k2 : float
        Fatigue gain coefficient. Default 2.0 (Banister k1/k2 ≈ 1/2).
    gamma : float
        Recovery credit coefficient. Default 0.5 (Busso 2002).
    w_recovery_threshold : float
        TRIMP threshold below which a day counts as recovery. Default 25.0.
    """

    tau1_days: float = 42.0
    tau2_days: float = 7.0
    tau1r_days: float = 14.0
    tau2r_days: float = 3.0
    k1: float = 1.0
    k2: float = 2.0
    gamma: float = 0.5
    w_recovery_threshold: float = 25.0


@dataclasses.dataclass(frozen=True)
class BanisterRow:
    """One day's Banister model state.

    Parameters
    ----------
    date : datetime.date
        Calendar date.
    trimp : float
        Raw daily TRIMP (sum of all activities on this day).
    fitness : float
        Fitness(t) — 42-day EMA with positive/negative impulse.
    fatigue : float
        Fatigue(t) — 7-day EMA with positive/negative impulse.
    performance : float
        p(t) = k1·fitness(t) − k2·fatigue(t).
    """

    date: datetime.date
    trimp: float
    fitness: float
    fatigue: float
    performance: float

    @property
    def atrimp(self) -> float:
        """Legacy 7-day EMA — fatigue from the symmetric form."""
        return self.fatigue

    @property
    def ctrimp(self) -> float:
        """Legacy 42-day EMA — fitness from the symmetric form."""
        return self.fitness

    @property
    def btrimp(self) -> float:
        """Legacy balance = CTRIMP − ATRIMP."""
        return self.fitness - self.fatigue

    @property
    def diagnosis(self) -> str:
        """One-word athlete-friendly label of today's state."""
        return _classify_performance(self.performance)


@dataclasses.dataclass(frozen=True)
class Annotation:
    """A marked event on the Banister timeline."""

    id: str
    date: datetime.date
    kind: str  # "peak", "overreach", "fitness_pb"
    label: str
    value: float


@dataclasses.dataclass(frozen=True)
class InsightCard:
    """A programmatic insight card for the UI.

    ``body_lines`` supports simple markup:
      ``## Section Title`` — section header (bold, colored)
      ``@@label|value|min|max|color`` — inline gauge bar
      ``""`` (empty) — visual spacer
      anything else — body paragraph
    """

    kind: str
    title: str
    body_lines: list[str]
    annotation_id: str | None = None
    zone_badge: str = ""
    zone_color: str = ""


@dataclasses.dataclass(frozen=True)
class ActivityImpact:
    """Per-activity impact analysis result."""

    benefits: list[str]
    risks: list[str]
    context: list[str]
    recommendation: str
    pre_row: BanisterRow | None
    post_row: BanisterRow | None
    eta_fresh_days: int
    delta_fitness: float
    delta_fatigue: float
    delta_performance: float
