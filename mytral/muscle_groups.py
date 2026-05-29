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
"""Canonical muscle group definitions and SVG mannequin ID mapping.

This module defines the 14 standard strength-training muscle groups used
throughout MyTraL for exercise annotation, activity type classification,
and the daily muscle heat-map visualization.
"""

from __future__ import annotations

import dataclasses


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
