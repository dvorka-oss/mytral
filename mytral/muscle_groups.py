# MyTraL: my training log
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
"""Canonical muscle group definitions and daily heat-map calibration.

This module defines the 14 canonical muscle groups (+ 2 supplementary) used
throughout MyTraL for exercise annotation, activity type classification,
and the daily muscle heat-map visualization. It also computes the heat-map
itself: how often each muscle group is targeted on a given day, and how that
count is bucketed into one of 5 intensity colors.
"""

from __future__ import annotations

import collections
import dataclasses
import datetime
import math
import typing

if typing.TYPE_CHECKING:
    from mytral import settings
    from mytral.backends import entities


@dataclasses.dataclass(frozen=True)
class MuscleGroupDef:
    """Definition of a single muscle group.

    Parameters
    ----------
    key : str
        Canonical snake_case key stored in JSON (e.g. ``"pecs"``).
    label : str
        Human-readable display name (e.g. ``"Pectorals"``).
    svg_ids : tuple[str, ...]
        ID suffixes of the SVG ``<g>`` elements in the mannequin macro that
        represent this muscle group. The full DOM ID is ``{picker_id}-{svg_id}``
        where ``picker_id`` is the macro call argument. JS interaction uses
        ``data-muscle-key`` attributes rather than these IDs directly.
    description : str
        Short anatomical description shown in tooltips.
    """

    key: str
    label: str
    svg_ids: tuple[str, ...]
    description: str = ""


#
# 14 canonical muscle groups (+ 2 supplementary) used across MyTraL
#

MUSCLE_GROUPS: list[MuscleGroupDef] = [
    MuscleGroupDef(
        key="pecs",
        label="Pectorals",
        svg_ids=("mg-front-pecs",),
        description="Chest muscles – pectoralis major and minor.",
    ),
    MuscleGroupDef(
        key="shoulders",
        label="Shoulders",
        svg_ids=(
            "mg-front-shoulders-l",
            "mg-front-shoulders-r",
            "mg-back-shoulders-l",
            "mg-back-shoulders-r",
        ),
        description="Deltoid muscles – anterior, lateral, and posterior heads.",
    ),
    MuscleGroupDef(
        key="biceps",
        label="Biceps",
        svg_ids=("mg-front-biceps-l", "mg-front-biceps-r"),
        description="Biceps brachii – upper arm flexors.",
    ),
    MuscleGroupDef(
        key="triceps",
        label="Triceps",
        svg_ids=("mg-back-triceps-l", "mg-back-triceps-r"),
        description="Triceps brachii – upper arm extensors.",
    ),
    MuscleGroupDef(
        key="forearms",
        label="Forearms",
        svg_ids=(
            "mg-front-forearms-l",
            "mg-front-forearms-r",
            "mg-back-forearms-l",
            "mg-back-forearms-r",
        ),
        description="Forearm flexors and extensors – grip and wrist control.",
    ),
    MuscleGroupDef(
        key="abs",
        label="Abs",
        svg_ids=("mg-front-abs",),
        description="Rectus abdominis and transversus abdominis – core centre.",
    ),
    MuscleGroupDef(
        key="obliques",
        label="Obliques",
        svg_ids=("mg-front-obliques-l", "mg-front-obliques-r"),
        description="External and internal obliques – lateral core stability.",
    ),
    MuscleGroupDef(
        key="traps",
        label="Trapezius",
        svg_ids=("mg-back-traps",),
        description="Trapezius – upper back posture and shoulder-blade control.",
    ),
    MuscleGroupDef(
        key="lats",
        label="Lats",
        svg_ids=("mg-back-lats-l", "mg-back-lats-r"),
        description="Latissimus dorsi – broad back muscles for pulling movements.",
    ),
    MuscleGroupDef(
        key="lower_back",
        label="Lower Back",
        svg_ids=("mg-back-lower-back",),
        description="Erector spinae and multifidus – lumbar spine support.",
    ),
    MuscleGroupDef(
        key="glutes",
        label="Glutes",
        svg_ids=("mg-back-glutes-l", "mg-back-glutes-r"),
        description="Gluteus maximus, medius, minimus – hip extension and power.",
    ),
    MuscleGroupDef(
        key="quads",
        label="Quadriceps",
        svg_ids=("mg-front-quads-l", "mg-front-quads-r"),
        description="Quadriceps femoris – front thigh, knee extension.",
    ),
    MuscleGroupDef(
        key="hamstrings",
        label="Hamstrings",
        svg_ids=("mg-back-hamstrings-l", "mg-back-hamstrings-r"),
        description="Biceps femoris, semitendinosus, semimembranosus – rear thigh.",
    ),
    MuscleGroupDef(
        key="calves",
        label="Calves",
        svg_ids=(
            "mg-front-calves-l",
            "mg-front-calves-r",
            "mg-back-calves-l",
            "mg-back-calves-r",
        ),
        description="Gastrocnemius and soleus – lower leg and ankle drive.",
    ),
    # supplementary groups (useful for injury context and endurance activity_types)
    MuscleGroupDef(
        key="neck",
        label="Neck",
        svg_ids=("mg-front-neck", "mg-back-neck"),
        description="Cervical muscles – head and neck stabilizers.",
    ),
    MuscleGroupDef(
        key="hip_flexors",
        label="Hip Flexors",
        svg_ids=("mg-front-hip-flexors-l", "mg-front-hip-flexors-r"),
        description="Iliopsoas and rectus femoris – hip flexion, running stride.",
    ),
]

#
# Convenience look-ups
#

MUSCLE_GROUP_BY_KEY: dict[str, MuscleGroupDef] = {mg.key: mg for mg in MUSCLE_GROUPS}

MUSCLE_GROUP_KEYS: list[str] = [mg.key for mg in MUSCLE_GROUPS]


def validate_muscle_keys(keys: list[str]) -> list[str]:
    """Return only the valid canonical muscle group keys from *keys*.

    Parameters
    ----------
    keys : list[str]
        Raw list of keys to validate (e.g. from a form field).

    Returns
    -------
    list[str]
        Filtered list containing only keys present in
        :data:`MUSCLE_GROUP_BY_KEY`.
    """
    return [k for k in keys if k in MUSCLE_GROUP_BY_KEY]


def parse_muscle_groups_csv(value: str) -> list[str]:
    """Parse a comma-separated string of muscle group keys.

    Parameters
    ----------
    value : str
        Comma-separated muscle group keys, e.g.
        ``"pecs,triceps,shoulders"``.

    Returns
    -------
    list[str]
        Validated, deduplicated list of canonical muscle group keys,
        preserving order of first occurrence.
    """
    if not value:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for raw in value.split(","):
        key = raw.strip()
        if key and key in MUSCLE_GROUP_BY_KEY and key not in seen:
            seen.add(key)
            result.append(key)
    return result


#
# daily muscle heat-map: how often each muscle group is targeted on a given
# day, and how that count is bucketed into one of 5 intensity colors
#

# trailing window used to calibrate a user's own intensity thresholds
HEATMAP_HISTORY_WINDOW_DAYS = 180

# a muscle group needs at least this many nonzero-count days in the window
# before its thresholds are calibrated from history; below that, the sample
# is too small to trust and DEFAULT_INTENSITY_THRESHOLDS is used instead
HEATMAP_MIN_HISTORY_SAMPLES = 8

# fallback thresholds (count -> intensity-2..5) for muscle groups without
# enough history yet, e.g. new users or rarely-trained muscles
DEFAULT_INTENSITY_THRESHOLDS: tuple[int, int, int, int] = (2, 4, 7, 10)

# percentiles of a muscle group's own nonzero daily counts used to derive its
# intensity-2..5 thresholds, so "hot" means unusually high for that user
_INTENSITY_PERCENTILES: tuple[int, int, int, int] = (40, 65, 85, 97)


@dataclasses.dataclass(frozen=True)
class DailyMuscleStats:
    """Per-muscle-group training signal for a single day.

    Parameters
    ----------
    counts : dict[str, int]
        Muscle group key -> number of activity-types and logged exercises
        that day which targeted it as a primary muscle.
    secondary_keys : set[str]
        Muscle groups targeted only as a stabilizer/synergist that day.
    """

    counts: dict[str, int]
    secondary_keys: set[str]


def compute_daily_muscle_stats(
    activities: typing.Iterable["entities.ActivityEntity"],
    activity_types_registry: "settings.UserActivityTypes",
    exercises_registry: "settings.UserExercises",
) -> DailyMuscleStats:
    """Aggregate muscle group hits across a single day's activities.

    Parameters
    ----------
    activities : Iterable[ActivityEntity]
        Activities logged on one day.
    activity_types_registry : settings.UserActivityTypes
        User's activity type definitions (source of ``muscle_groups``).
    exercises_registry : settings.UserExercises
        User's exercise definitions (source of ``muscle_groups``).

    Returns
    -------
    DailyMuscleStats
        Primary hit counts and secondary-only muscle groups for the day.
    """
    counts: dict[str, int] = {}
    secondary_keys: set[str] = set()
    for activity in activities:
        at = activity_types_registry.activity_types_by_key.get(
            activity.activity_type_key
        )
        if at:
            for key in at.muscle_groups or []:
                counts[key] = counts.get(key, 0) + 1
            for key in at.muscle_groups_secondary or []:
                secondary_keys.add(key)
        for ex_entity in activity.exercises or []:
            ex = exercises_registry.exercise_by_key.get(
                ex_entity.name
            ) or exercises_registry.exercise_by_name.get(ex_entity.name)
            if ex:
                for key in ex.muscle_groups or []:
                    counts[key] = counts.get(key, 0) + 1
                for key in ex.muscle_groups_secondary or []:
                    secondary_keys.add(key)
    return DailyMuscleStats(counts=counts, secondary_keys=secondary_keys)


def group_activities_by_date(
    activities: typing.Iterable["entities.ActivityEntity"],
) -> dict[datetime.date, list["entities.ActivityEntity"]]:
    """Bucket activities by their calendar day.

    Parameters
    ----------
    activities : Iterable[ActivityEntity]
        Activities to bucket, in any order.

    Returns
    -------
    dict[datetime.date, list[ActivityEntity]]
        Activities grouped by ``(when_year, when_month, when_day)``.
    """
    by_date: dict[datetime.date, list["entities.ActivityEntity"]] = (
        collections.defaultdict(list)
    )
    for activity in activities:
        when = datetime.date(activity.when_year, activity.when_month, activity.when_day)
        by_date[when].append(activity)
    return by_date


def _percentile(sorted_samples: list[int], pct: float) -> int:
    """Nearest-rank percentile of an already-sorted, nonempty sample list."""
    rank = max(0, math.ceil(pct / 100 * len(sorted_samples)) - 1)
    return sorted_samples[min(rank, len(sorted_samples) - 1)]


def calibrate_intensity_thresholds(
    historical_counts_by_day: list[dict[str, int]],
) -> dict[str, tuple[int, int, int, int]]:
    """Derive per-muscle-group intensity thresholds from the user's history.

    Parameters
    ----------
    historical_counts_by_day : list[dict[str, int]]
        One ``muscle_key -> count`` dict per day in the trailing history
        window (see :func:`compute_daily_muscle_stats`).

    Returns
    -------
    dict[str, tuple[int, int, int, int]]
        Muscle group key -> (intensity-2, intensity-3, intensity-4,
        intensity-5) count thresholds. Muscle groups with fewer than
        HEATMAP_MIN_HISTORY_SAMPLES nonzero days are omitted; callers should
        fall back to DEFAULT_INTENSITY_THRESHOLDS for those.
    """
    samples_by_muscle: dict[str, list[int]] = collections.defaultdict(list)
    for day_counts in historical_counts_by_day:
        for key, count in day_counts.items():
            if count > 0:
                samples_by_muscle[key].append(count)

    thresholds: dict[str, tuple[int, int, int, int]] = {}
    for key, samples in samples_by_muscle.items():
        if len(samples) < HEATMAP_MIN_HISTORY_SAMPLES:
            continue
        samples.sort()
        t2, t3, t4, t5 = (_percentile(samples, p) for p in _INTENSITY_PERCENTILES)
        # keep buckets strictly increasing even when percentiles collide
        t3 = max(t3, t2 + 1)
        t4 = max(t4, t3 + 1)
        t5 = max(t5, t4 + 1)
        thresholds[key] = (t2, t3, t4, t5)
    return thresholds


def intensity_class_for_count(count: int, thresholds: tuple[int, int, int, int]) -> str:
    """Map a muscle group's daily hit count to a mannequin CSS class.

    Parameters
    ----------
    count : int
        Number of hits for the muscle group on the day being rendered.
    thresholds : tuple[int, int, int, int]
        (intensity-2, intensity-3, intensity-4, intensity-5) count cutoffs,
        as returned per-muscle by :func:`calibrate_intensity_thresholds`.

    Returns
    -------
    str
        ``"state-active intensity-N"`` CSS class, N from 1 (coolest) to 5.
    """
    t2, t3, t4, t5 = thresholds
    if count >= t5:
        return "state-active intensity-5"
    if count >= t4:
        return "state-active intensity-4"
    if count >= t3:
        return "state-active intensity-3"
    if count >= t2:
        return "state-active intensity-2"
    return "state-active intensity-1"


def build_day_muscle_highlights(
    day_stats: DailyMuscleStats,
    historical_counts_by_day: list[dict[str, int]],
) -> dict[str, str]:
    """Build the ``{muscle_key: css_class}`` map for the day heat-map.

    Intensity thresholds are calibrated per muscle group from the user's own
    trailing HEATMAP_HISTORY_WINDOW_DAYS days of training, so "hot" means
    unusually high for that user rather than an arbitrary absolute count.
    Muscle groups without enough history fall back to
    DEFAULT_INTENSITY_THRESHOLDS. Secondary-only muscles render at the
    coolest step so the whole figure reads as one ramp; a muscle that is
    both primary and secondary keeps its primary count.

    Parameters
    ----------
    day_stats : DailyMuscleStats
        Hit counts and secondary-only muscle groups for the rendered day.
    historical_counts_by_day : list[dict[str, int]]
        One ``muscle_key -> count`` dict per day in the trailing history
        window, used to calibrate thresholds.

    Returns
    -------
    dict[str, str]
        Muscle group key -> ``"state-active intensity-N"`` CSS class.
    """
    calibrated = calibrate_intensity_thresholds(historical_counts_by_day)
    highlights: dict[str, str] = {}
    for key, count in day_stats.counts.items():
        thresholds = calibrated.get(key, DEFAULT_INTENSITY_THRESHOLDS)
        highlights[key] = intensity_class_for_count(count, thresholds)
    for key in day_stats.secondary_keys:
        highlights.setdefault(key, "state-active intensity-1")
    return highlights
