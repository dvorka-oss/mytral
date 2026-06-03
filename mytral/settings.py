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
import dataclasses
import functools
import json
import time
import uuid
from datetime import datetime
from typing import Self

from mytral import cals
from mytral import commons
from mytral import loggers
from mytral import muscle_groups as mg
from mytral import persistences
from mytral.ai import settings as ai_settings
from mytral.integrations import icommons
from mytral.ml.icl import settings as icl_settings

#
# Bootstrap detection
#

# namespace UUID for MyTraL bootstrap data - deterministic UUID generation
MYTRAL_BOOTSTRAP_NAMESPACE = uuid.UUID("d0e7f5a3-4b2c-4a1e-8f9d-3c5b6a7e8d9f")


def generate_bootstrap_uuid(item_name: str) -> str:
    """Generate deterministic UUID for bootstrap items.

    Parameters
    ----------
    item_name : str
        name of the bootstrap item

    Returns
    -------
    str
        deterministic UUID as string

    """
    return str(uuid.uuid5(MYTRAL_BOOTSTRAP_NAMESPACE, item_name.lower().strip()))


def is_bootstrap_data_only(items_by_key: dict, bootstrap_names: list[str]) -> bool:
    """Check if collection contains only unmodified bootstrap data.

    Parameters
    ----------
    items_by_key : dict
        collection of items keyed by UUID
    bootstrap_names : list[str]
        list of expected bootstrap item names

    Returns
    -------
    bool
        True if collection contains exactly the bootstrap items with bootstrap UUIDs

    """
    if not items_by_key:
        return True

    # get expected bootstrap UUIDs
    expected_uuids = {generate_bootstrap_uuid(name) for name in bootstrap_names}

    # check if actual UUIDs exactly match bootstrap UUIDs
    actual_uuids = set(items_by_key.keys())

    # must be exact match - any addition or deletion means user has modified
    return actual_uuids == expected_uuids


#
# Activity types
#


class ActivityType:
    """Activity types."""

    KEY_NAME = "name"
    KEY_IS_DISTANCE = "is_distance"
    KEY_IS_EXERCISE = "is_exercise"
    KEY_IS_REGEN = "is_regen"
    KEY_IS_META = "is_meta"
    KEY_IS_BUILT_IN = "is_built_in"
    KEY_EMOJI = "emoji"
    KEY_COLOR = "color"
    KEY_META_ACTIVITY_TYPE = "meta_activity_type"
    KEY_COUNT = "count"
    KEY_KEY = "key"

    KEY_MUSCLE_GROUPS = "muscle_groups"
    KEY_MUSCLE_GROUPS_SECONDARY = "muscle_groups_secondary"

    def __init__(
        self,
        name: str,
        is_distance: bool,
        is_exercise: bool,
        is_regen: bool,
        is_meta: bool = False,
        is_built_in: bool = False,
        emoji="",
        color="",
        meta_activity_type="",
        count: int = 0,
        key: str = "",
        muscle_groups: list[str] | None = None,
        muscle_groups_secondary: list[str] | None = None,
    ) -> None:
        """Activity type:

        Parameters
        ----------
        name: str
            Activity type name.
        is_distance: bool
            Activity type is distance based.
        is_exercise: bool
            Activity type is exercise.
        is_regen: bool
            Activity type is regeneration.
        is_meta: bool
            Activity type is metadata.
        is_built_in: bool
            Activity type is built-in.
        emoji: str
            Activity type emoji character.
        color: str
            Activity type color - class name (class=),
            # prefix means hexa color (style=)
        count: int
            Activity type count.
        key: str
            Activity type key.
        muscle_groups: list[str] | None
            Canonical muscle group keys primarily activated by this activity type
            (e.g. ``["quads", "glutes", "hamstrings"]``).
        muscle_groups_secondary: list[str] | None
            Canonical muscle group keys used as stabilizers / synergists
            (e.g. ``["calves", "lower_back"]``).

        """

        self.name = name
        self.is_distance = is_distance
        self.is_exercise = is_exercise
        self.is_regen = is_regen
        self.is_meta = is_meta
        self.is_built_in = is_built_in
        self.emoji = emoji
        self.color = color
        self.meta_activity_type = meta_activity_type
        self.count = count
        self.muscle_groups = muscle_groups or []
        self.muscle_groups_secondary = muscle_groups_secondary or []

        self.key = key or str(uuid.uuid4())

    def to_dict(self) -> dict:
        return {
            ActivityType.KEY_NAME: self.name,
            ActivityType.KEY_IS_DISTANCE: self.is_distance,
            ActivityType.KEY_IS_EXERCISE: self.is_exercise,
            ActivityType.KEY_IS_REGEN: self.is_regen,
            ActivityType.KEY_IS_META: self.is_meta,
            ActivityType.KEY_IS_BUILT_IN: self.is_built_in,
            ActivityType.KEY_EMOJI: self.emoji,
            ActivityType.KEY_COLOR: self.color,
            ActivityType.KEY_META_ACTIVITY_TYPE: self.meta_activity_type,
            ActivityType.KEY_COUNT: self.count,
            ActivityType.KEY_KEY: self.key,
            ActivityType.KEY_MUSCLE_GROUPS: self.muscle_groups,
            ActivityType.KEY_MUSCLE_GROUPS_SECONDARY: self.muscle_groups_secondary,
        }

    @staticmethod
    def from_dict(activity_types_dict: dict) -> "ActivityType":
        return ActivityType(
            name=activity_types_dict[ActivityType.KEY_NAME],
            is_distance=activity_types_dict[ActivityType.KEY_IS_DISTANCE],
            is_exercise=activity_types_dict[ActivityType.KEY_IS_EXERCISE],
            is_regen=activity_types_dict[ActivityType.KEY_IS_REGEN],
            is_meta=activity_types_dict.get(ActivityType.KEY_IS_META, False),
            is_built_in=activity_types_dict.get(ActivityType.KEY_IS_BUILT_IN, False),
            emoji=activity_types_dict.get(ActivityType.KEY_EMOJI, ""),
            color=activity_types_dict.get(ActivityType.KEY_COLOR, ""),
            meta_activity_type=activity_types_dict.get(
                ActivityType.KEY_META_ACTIVITY_TYPE, ""
            ),
            count=activity_types_dict.get(ActivityType.KEY_COUNT, 0),
            key=activity_types_dict.get(ActivityType.KEY_KEY, ""),
            muscle_groups=mg.validate_muscle_keys(
                activity_types_dict.get(ActivityType.KEY_MUSCLE_GROUPS, [])
            ),
            muscle_groups_secondary=mg.validate_muscle_keys(
                activity_types_dict.get(ActivityType.KEY_MUSCLE_GROUPS_SECONDARY, [])
            ),
        )


_BOOTSTRAP_META_ACTIVITY_TYPES_BY_ACTIVITY_KEY: dict[str, str] = {
    activity_type_key: meta_activity_type
    for meta_activity_type, activity_types in commons.AT_TAXONOMY.items()
    for activity_type_key in activity_types
}

_BOOTSTRAP_MUSCLE_GROUPS_BY_META_ACTIVITY_TYPE: dict[
    str, tuple[list[str], list[str]]
] = {
    commons.M_AT_RUN: (
        ["quads", "hamstrings", "glutes", "calves", "hip_flexors"],
        ["abs", "obliques", "lower_back"],
    ),
    commons.M_AT_SKI: (
        ["quads", "glutes", "hamstrings", "calves"],
        ["lats", "triceps", "abs", "obliques", "lower_back", "shoulders"],
    ),
    commons.M_AT_RIDE: (
        ["quads", "glutes", "hamstrings", "calves", "hip_flexors"],
        ["abs", "obliques", "lower_back"],
    ),
    commons.M_AT_ROW: (
        ["lats", "traps", "shoulders", "biceps", "forearms", "glutes", "hamstrings"],
        ["abs", "obliques", "lower_back", "quads"],
    ),
    commons.M_AT_CANOEING: (
        ["lats", "shoulders", "triceps", "forearms"],
        ["abs", "obliques", "lower_back", "biceps"],
    ),
    commons.M_AT_SWIM: (
        ["shoulders", "lats", "triceps", "abs", "obliques"],
        ["biceps", "glutes", "quads", "hamstrings"],
    ),
    commons.M_AT_GYM: (
        ["quads", "glutes", "hamstrings", "pecs", "lats", "shoulders"],
        ["biceps", "triceps", "abs", "obliques", "lower_back"],
    ),
    commons.M_AT_HIKE: (
        ["quads", "glutes", "hamstrings", "calves", "hip_flexors"],
        ["abs", "obliques", "lower_back"],
    ),
    commons.M_AT_ALPINE_SKI: (
        ["quads", "glutes", "hamstrings", "calves"],
        ["abs", "obliques", "lower_back"],
    ),
    commons.M_AT_PHYSIO: (
        ["glutes", "abs", "obliques", "lower_back"],
        ["hip_flexors", "hamstrings", "shoulders"],
    ),
    commons.M_AT_MULTISPORT: (
        ["quads", "hamstrings", "glutes", "calves", "shoulders", "lats"],
        ["abs", "obliques", "lower_back", "triceps"],
    ),
    commons.M_AT_GAMES: (
        ["quads", "hamstrings", "glutes", "calves", "abs", "obliques"],
        ["shoulders", "lats", "triceps", "biceps"],
    ),
    commons.M_AT_RELAX: ([], []),
}

_BOOTSTRAP_MUSCLE_GROUPS_BY_ACTIVITY_TYPE_KEY: dict[
    str, tuple[list[str], list[str]]
] = {
    commons.AT_WORKOUT: (
        ["quads", "hamstrings", "glutes", "pecs", "lats", "shoulders"],
        ["biceps", "triceps", "abs", "obliques", "lower_back", "calves", "forearms"],
    ),
    commons.AT_SAIL: (
        ["forearms", "shoulders", "abs", "obliques"],
        ["lats", "traps", "lower_back"],
    ),
    commons.AT_SKATE_ICE: (
        ["quads", "glutes", "hamstrings", "calves"],
        ["abs", "obliques", "lower_back", "hip_flexors"],
    ),
    commons.AT_SKATE_INLINE: (
        ["quads", "glutes", "hamstrings", "calves"],
        ["abs", "obliques", "lower_back", "hip_flexors"],
    ),
    commons.AT_SURF: (
        ["shoulders", "lats", "triceps", "abs", "obliques"],
        ["glutes", "hamstrings", "lower_back"],
    ),
    commons.AT_SURF_KITE: (
        ["forearms", "shoulders", "lats", "abs", "obliques"],
        ["glutes", "hamstrings", "lower_back"],
    ),
    commons.AT_SURF_WIND: (
        ["forearms", "shoulders", "lats", "abs", "obliques"],
        ["glutes", "hamstrings", "lower_back"],
    ),
    commons.AT_SURF_WAKEBOARD: (
        ["glutes", "quads", "hamstrings", "shoulders", "abs"],
        ["obliques", "forearms", "lower_back", "calves"],
    ),
    commons.AT_SURF_WAKE: (
        ["glutes", "quads", "hamstrings", "shoulders", "abs"],
        ["obliques", "forearms", "lower_back", "calves"],
    ),
    commons.AT_DIVE: (
        ["shoulders", "lats", "abs", "obliques"],
        ["forearms", "lower_back"],
    ),
    commons.AT_ARCHERY: (
        ["shoulders", "lats", "forearms", "biceps"],
        ["traps", "abs", "obliques"],
    ),
    commons.AT_DANCE: (
        ["quads", "glutes", "hamstrings", "calves", "abs", "obliques"],
        ["hip_flexors", "lower_back"],
    ),
    commons.AT_CLIMB_ROCK: (
        ["lats", "forearms", "biceps", "shoulders", "abs", "obliques"],
        ["triceps", "glutes", "hamstrings", "lower_back"],
    ),
    commons.AT_FLYING: (
        ["forearms", "shoulders", "neck"],
        ["abs", "obliques", "lower_back"],
    ),
    commons.AT_SKYDIVE: (
        ["shoulders", "abs", "obliques", "lower_back"],
        ["glutes", "hamstrings", "neck"],
    ),
    commons.AT_HAND_GLIDING: (
        ["shoulders", "forearms", "abs", "obliques"],
        ["lats", "lower_back", "neck"],
    ),
    commons.AT_SKATEBOARD: (
        ["quads", "glutes", "hamstrings", "calves"],
        ["abs", "obliques", "lower_back"],
    ),
    commons.AT_HORSE_RIDING: (
        ["glutes", "quads", "hamstrings", "hip_flexors"],
        ["abs", "obliques", "lower_back"],
    ),
    commons.AT_BOX: (
        ["shoulders", "triceps", "pecs", "abs", "obliques", "quads"],
        ["lats", "biceps", "glutes", "calves"],
    ),
    commons.AT_MMA: (
        ["shoulders", "triceps", "pecs", "abs", "obliques", "quads"],
        ["lats", "biceps", "glutes", "hamstrings", "calves"],
    ),
}


def _bootstrap_activity_types_with_defaults(
    activity_types: list[ActivityType],
) -> list[ActivityType]:
    for activity_type in activity_types:
        activity_type.meta_activity_type = (
            _BOOTSTRAP_META_ACTIVITY_TYPES_BY_ACTIVITY_KEY.get(activity_type.key, "")
        )
        primary_muscles, secondary_muscles = (
            _BOOTSTRAP_MUSCLE_GROUPS_BY_ACTIVITY_TYPE_KEY.get(
                activity_type.key,
                _BOOTSTRAP_MUSCLE_GROUPS_BY_META_ACTIVITY_TYPE.get(
                    activity_type.meta_activity_type, ([], [])
                ),
            )
        )
        activity_type.muscle_groups = mg.validate_muscle_keys(primary_muscles)
        activity_type.muscle_groups_secondary = mg.validate_muscle_keys(
            secondary_muscles
        )

    return activity_types


class UserActivityTypes:
    """Custom activity types defined by the user + OOTB activity types."""

    # default activity types for new users
    BOOTSTRAP = _bootstrap_activity_types_with_defaults(
        [
            #
            # activity_type_key: distance
            #
            ActivityType(
                name="Run",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏃",
                color="brown",
                key=commons.AT_RUN,
            ),
            ActivityType(
                name="Row",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🚣",
                color="black",
                key=commons.AT_ROW,
            ),
            ActivityType(
                name="Ride",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🚴",
                color="green",
                key=commons.AT_RIDE,
            ),
            ActivityType(
                name="Hike",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🥾",
                color="orange",
                key=commons.AT_HIKE,
            ),
            ActivityType(
                name="Concept2",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🚣",
                color="black",
                key=commons.AT_ROW_ERG,
            ),
            ActivityType(
                name="Paddleboard",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏄",
                color="azure",
                key=commons.AT_PADDLE,
            ),
            ActivityType(
                name="Kayak",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🛶",
                key=commons.AT_KAYAK,
            ),
            ActivityType(
                name="Ski classic",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🎿",
                color="blue",
                key=commons.AT_SKI_DP,
            ),
            ActivityType(
                name="Ski skate",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🎿",
                color="blue",
                key=commons.AT_SKI_F,
            ),
            ActivityType(
                name="Roller ski classic",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🎿",
                color="blue",
                key=commons.AT_RS_DP,
            ),
            ActivityType(
                name="Roller ski skate",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🎿",
                color="blue",
                key=commons.AT_RS_F,
            ),
            ActivityType(
                name="Swim",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏊",
                color="indigo",
                key=commons.AT_SWIM,
            ),
            ActivityType(
                name="Trail run",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏃",
                color="brown",
                key=commons.AT_RUN_TRAIL,
            ),
            ActivityType(
                name="Gravel bike",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🚴",
                color="green",
                key=commons.AT_RIDE_GRAVEL,
            ),
            #
            # activity_type_key: exercise
            #
            ActivityType(
                name="Exercise",
                is_distance=False,
                is_exercise=True,
                is_regen=False,
                is_built_in=True,
                emoji="🏋️",
                color="purple",
                key=commons.AT_GYM,
            ),
            ActivityType(
                name="Physiotherapy",
                is_distance=False,
                is_exercise=True,
                is_regen=False,
                is_built_in=True,
                emoji="🤸",
                color="cyan",
                key=commons.AT_PHYSIO,
            ),
            #
            # activity_type_key: ignore
            #
            ActivityType(
                name="Ski downhill",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="⛷️",
                key=commons.AT_SKI_DOWNHILL,
            ),
            #
            # regeneration
            #
            ActivityType(
                name="Sleep",
                is_distance=False,
                is_exercise=False,
                is_regen=True,
                is_built_in=True,
                emoji="💤",
                key=commons.AT_SLEEP,
            ),
            ActivityType(
                name="Sauna",
                is_distance=False,
                is_exercise=False,
                is_regen=True,
                is_built_in=True,
                emoji="💦",
                color="white",
                key=commons.AT_SAUNA,
            ),
            ActivityType(
                name="Steam",
                is_distance=False,
                is_exercise=False,
                is_regen=True,
                is_built_in=True,
                emoji="🚿",
                color="teal",
                key=commons.AT_STEAM,
            ),
            ActivityType(
                name="Meditation",
                is_distance=False,
                is_exercise=False,
                is_regen=True,
                is_built_in=True,
                emoji="🧘",
                color="cyan",
                key=commons.AT_MEDITATION,
            ),
            #
            # unable to train
            #
            ActivityType(
                # the problem is unrelated to activity_type_key like flu or depression
                name="Sick",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_meta=True,
                is_built_in=True,
                emoji="💊",
                color="red",
                key=commons.AT_SICK,
            ),
            ActivityType(
                # the problem is unrelated to activity_type_key like flu or depression
                name="Injured",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_meta=True,
                is_built_in=True,
                emoji="🤕",
                color="pink",
                key=commons.AT_INJURED,
            ),
            #
            # metadata
            #
            ActivityType(
                name="Plan",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_meta=True,
                is_built_in=True,
                emoji="📌",
                color="yellow",
                key=commons.AT_PLAN,
            ),
            ActivityType(
                # the problem is unrelated to activity_type_key like flu or depression
                name="Comment",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_meta=True,
                is_built_in=True,
                emoji="💬",
                color="gray",
                key=commons.AT_COMMENT,
            ),
            #
            # missing bootstrap activity types from commons.py
            #
            ActivityType(
                name="Workout",
                is_distance=False,
                is_exercise=True,
                is_regen=False,
                is_built_in=True,
                emoji="💪",
                color="purple",
                key=commons.AT_WORKOUT,
            ),
            ActivityType(
                name="Multisport",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏅",
                color="yellow",
                key=commons.AT_MULTISPORT,
            ),
            ActivityType(
                name="Triathlon",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏅",
                color="yellow",
                key=commons.AT_TRIATHLON,
            ),
            ActivityType(
                name="Duathlon",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏅",
                color="yellow",
                key=commons.AT_DUATHLON,
            ),
            ActivityType(
                name="Transition",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_meta=True,
                is_built_in=True,
                emoji="🔁",
                color="gray",
                key=commons.AT_TRANSITION,
            ),
            ActivityType(
                name="Canoe",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🛶",
                color="azure",
                key=commons.AT_CANOE,
            ),
            ActivityType(
                name="Canoeing",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🛶",
                color="azure",
                key=commons.AT_CANOEING,
            ),
            ActivityType(
                name="Ride erg",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🚴",
                color="black",
                key=commons.AT_RIDE_ERG,
            ),
            ActivityType(
                name="Handcycle",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="♿",
                color="blue",
                key=commons.AT_RIDE_HAND,
            ),
            ActivityType(
                name="Mountain bike",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🚵",
                color="green",
                key=commons.AT_RIDE_MOUNTAIN,
            ),
            ActivityType(
                name="E-bike",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🚴",
                color="green",
                key=commons.AT_RIDE_E,
            ),
            ActivityType(
                name="Virtual ride",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🚴",
                color="gray",
                key=commons.AT_RIDE_VIRTUAL,
            ),
            ActivityType(
                name="Virtual run",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏃",
                color="brown",
                key=commons.AT_RUN_VIRTUAL,
            ),
            ActivityType(
                name="Sail",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="⛵",
                color="blue",
                key=commons.AT_SAIL,
            ),
            ActivityType(
                name="Ice skate",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="⛸️",
                color="cyan",
                key=commons.AT_SKATE_ICE,
            ),
            ActivityType(
                name="Inline skate",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🛼",
                color="purple",
                key=commons.AT_SKATE_INLINE,
            ),
            ActivityType(
                name="Backcountry ski",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🎿",
                color="blue",
                key=commons.AT_SKI_BACKCOUNTRY,
            ),
            ActivityType(
                name="Water ski",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="⛷️",
                color="blue",
                key=commons.AT_SKI_WATER,
            ),
            ActivityType(
                name="Raft",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🛟",
                color="azure",
                key=commons.AT_RAFT,
            ),
            ActivityType(
                name="Snowshoe",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🥾",
                color="orange",
                key=commons.AT_SNOWSHOE,
            ),
            ActivityType(
                name="Surfing",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏄",
                color="azure",
                key=commons.AT_SURF,
            ),
            ActivityType(
                name="Kitesurf",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🪁",
                color="azure",
                key=commons.AT_SURF_KITE,
            ),
            ActivityType(
                name="Windsurf",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🌬️",
                color="azure",
                key=commons.AT_SURF_WIND,
            ),
            ActivityType(
                name="Wakeboard",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏄",
                color="azure",
                key=commons.AT_SURF_WAKEBOARD,
            ),
            ActivityType(
                name="Wakesurf",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏄",
                color="azure",
                key=commons.AT_SURF_WAKE,
            ),
            ActivityType(
                name="Dive",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🤿",
                color="azure",
                key=commons.AT_DIVE,
            ),
            ActivityType(
                name="Velomobile",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🚲",
                color="green",
                key=commons.AT_VELOMOBILE,
            ),
            ActivityType(
                name="Walk",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🚶",
                color="orange",
                key=commons.AT_WALK,
            ),
            ActivityType(
                name="Wheelchair",
                is_distance=True,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="♿",
                color="gray",
                key=commons.AT_WHEELCHAIR,
            ),
            ActivityType(
                name="Archery",
                is_distance=False,
                is_exercise=True,
                is_regen=False,
                is_built_in=True,
                emoji="🏹",
                color="brown",
                key=commons.AT_ARCHERY,
            ),
            ActivityType(
                name="Calisthenics",
                is_distance=False,
                is_exercise=True,
                is_regen=False,
                is_built_in=True,
                emoji="🤸",
                color="purple",
                key=commons.AT_CALISTHENICS,
            ),
            ActivityType(
                name="Crossfit",
                is_distance=False,
                is_exercise=True,
                is_regen=False,
                is_built_in=True,
                emoji="🏋️",
                color="purple",
                key=commons.AT_CROSSFIT,
            ),
            ActivityType(
                name="Dance",
                is_distance=False,
                is_exercise=True,
                is_regen=False,
                is_built_in=True,
                emoji="💃",
                color="pink",
                key=commons.AT_DANCE,
            ),
            ActivityType(
                name="Elliptical",
                is_distance=False,
                is_exercise=True,
                is_regen=False,
                is_built_in=True,
                emoji="🚴",
                color="purple",
                key=commons.AT_ELLIPTICAL,
            ),
            ActivityType(
                name="Hiit",
                is_distance=False,
                is_exercise=True,
                is_regen=False,
                is_built_in=True,
                emoji="⚡",
                color="red",
                key=commons.AT_HIIT,
            ),
            ActivityType(
                name="Mobility",
                is_distance=False,
                is_exercise=True,
                is_regen=False,
                is_built_in=True,
                emoji="🤸",
                color="cyan",
                key=commons.AT_MOBILITY,
            ),
            ActivityType(
                name="Stair stepper",
                is_distance=False,
                is_exercise=True,
                is_regen=False,
                is_built_in=True,
                emoji="🪜",
                color="orange",
                key=commons.AT_STAIR_STEPPER,
            ),
            ActivityType(
                name="Stretching",
                is_distance=False,
                is_exercise=True,
                is_regen=False,
                is_built_in=True,
                emoji="🤸",
                color="cyan",
                key=commons.AT_STRETCHING,
            ),
            ActivityType(
                name="Yoga",
                is_distance=False,
                is_exercise=True,
                is_regen=False,
                is_built_in=True,
                emoji="🧘",
                color="cyan",
                key=commons.AT_YOGA,
            ),
            ActivityType(
                name="Pilates",
                is_distance=False,
                is_exercise=True,
                is_regen=False,
                is_built_in=True,
                emoji="🤸",
                color="purple",
                key=commons.AT_PILATES,
            ),
            ActivityType(
                name="Baseball",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="⚾",
                color="red",
                key=commons.AT_BASEBALL,
            ),
            ActivityType(
                name="Basketball",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏀",
                color="orange",
                key=commons.AT_BASKETBALL,
            ),
            ActivityType(
                name="Cricket",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏏",
                color="green",
                key=commons.AT_CRICKET,
            ),
            ActivityType(
                name="Disc golf",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🥏",
                color="green",
                key=commons.AT_DISC_GOLF,
            ),
            ActivityType(
                name="American football",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏈",
                color="brown",
                key=commons.AT_FOOTBAL,
            ),
            ActivityType(
                name="Golf",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="⛳",
                color="green",
                key=commons.AT_GOLF,
            ),
            ActivityType(
                name="Hockey",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏒",
                color="blue",
                key=commons.AT_HOCKEY,
            ),
            ActivityType(
                name="Lacrosse",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🥍",
                color="blue",
                key=commons.AT_LACROSSE,
            ),
            ActivityType(
                name="Rugby",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏉",
                color="brown",
                key=commons.AT_RUGBY,
            ),
            ActivityType(
                name="Soccer",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="⚽",
                color="green",
                key=commons.AT_SOCCER,
            ),
            ActivityType(
                name="Tennis",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🎾",
                color="green",
                key=commons.AT_TENNIS,
            ),
            ActivityType(
                name="Volleyball",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏐",
                color="yellow",
                key=commons.AT_VOLLEYBALL,
            ),
            ActivityType(
                name="Badminton",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏸",
                color="green",
                key=commons.AT_BADMINTON,
            ),
            ActivityType(
                name="Pickleball",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🎾",
                color="yellow",
                key=commons.AT_PICKLEBALL,
            ),
            ActivityType(
                name="Racquetball",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🎾",
                color="blue",
                key=commons.AT_RACQUETBALL,
            ),
            ActivityType(
                name="Squash",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🎾",
                color="green",
                key=commons.AT_SQUASH,
            ),
            ActivityType(
                name="Table tennis",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏓",
                color="red",
                key=commons.AT_TABLETENNIS,
            ),
            ActivityType(
                name="Rock climb",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🧗",
                color="brown",
                key=commons.AT_CLIMB_ROCK,
            ),
            ActivityType(
                name="Flying",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🛩️",
                color="blue",
                key=commons.AT_FLYING,
            ),
            ActivityType(
                name="Skydive",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🪂",
                color="blue",
                key=commons.AT_SKYDIVE,
            ),
            ActivityType(
                name="Hand gliding",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🪂",
                color="blue",
                key=commons.AT_HAND_GLIDING,
            ),
            ActivityType(
                name="Skateboard",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🛹",
                color="gray",
                key=commons.AT_SKATEBOARD,
            ),
            ActivityType(
                name="Ski slalom",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🎿",
                color="blue",
                key=commons.AT_SKI_SLALOM,
            ),
            ActivityType(
                name="Snowboard",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏂",
                color="blue",
                key=commons.AT_SNOWBOARD,
            ),
            ActivityType(
                name="Horse riding",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🏇",
                color="brown",
                key=commons.AT_HORSE_RIDING,
            ),
            ActivityType(
                name="Box",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🥊",
                color="red",
                key=commons.AT_BOX,
            ),
            ActivityType(
                name="MMA",
                is_distance=False,
                is_exercise=False,
                is_regen=False,
                is_built_in=True,
                emoji="🥋",
                color="red",
                key=commons.AT_MMA,
            ),
        ]
    )

    @staticmethod
    def bootstrap() -> list[ActivityType]:
        activity_types = []
        for n in UserActivityTypes.BOOTSTRAP:
            activity_types.append(n)

        return activity_types

    @staticmethod
    def from_dict_dict(activity_type_data: dict | list) -> "UserActivityTypes":
        """Load from dict (old) or list (new) format."""
        activity_type_dict = persistences.normalize_dict_or_list_to_dict(
            activity_type_data
        )
        activity_types = []
        if not activity_type_dict:
            activity_types = UserActivityTypes.bootstrap()
        else:
            for mytral_key in activity_type_dict:
                activity_types.append(
                    ActivityType.from_dict(activity_type_dict[mytral_key])
                )

        activity_types.sort(key=lambda x: x.name)
        return UserActivityTypes(activity_types=activity_types)

    @property
    def activity_types_by_name(self) -> dict[str, ActivityType]:
        """Avoid having authoritative data twice."""
        if self.activity_types_by_key:
            # map: name -> activity type
            return {g.name: g for g in self.activity_types_by_key.values()}
        return {}

    def __init__(self, activity_types: list[ActivityType]) -> None:
        # map: key -> activity type
        self.activity_types_by_key: dict[str, ActivityType] = {}
        for g in activity_types:
            if not g.key:
                g.key = str(uuid.uuid4())
            self.activity_types_by_key[g.key] = g

        # cached
        self._is_meta: list[str] = []
        self._is_regen: list[str] = []
        self._is_distance: list[str] = []
        self._is_exercise: list[str] = []

    def evict(self) -> None:
        self._is_meta = []
        self._is_regen = []
        self._is_distance = []
        self._is_exercise = []

    def empty(self) -> bool:
        return len(self.activity_types_by_key) == 0

    def is_bootstrap_only(self) -> bool:
        """Check if collection contains only unmodified bootstrap data.

        Returns
        -------
        bool
            True if only bootstrap activity types are present

        """
        # activity types use predefined keys from commons.AT_*
        bootstrap_keys = {at.key for at in UserActivityTypes.BOOTSTRAP}
        actual_keys = set(self.activity_types_by_key.keys())
        return actual_keys == bootstrap_keys

    def default_activity_type(self) -> ActivityType | None:
        if self.empty():
            return None
        return list(self.activity_types_by_key.values())[0]

    def exists(self, key: str) -> bool:
        return key in self.activity_types_by_key

    def name(self, key: str) -> str:
        return self.activity_types_by_key[key].name if self.exists(key) else ""

    def emoji(self, key: str) -> str:
        return self.activity_types_by_key[key].emoji if self.exists(key) else ""

    def color(self, key: str) -> str:
        return self.activity_types_by_key[key].color if self.exists(key) else ""

    def delete(self, key: str):
        del self.activity_types_by_key[key]
        self.evict()

    def add_activity_type(self, activity_type: ActivityType):
        if not activity_type.key:
            activity_type.key = str(uuid.uuid4())

        self.activity_types_by_key[activity_type.key] = activity_type
        self.evict()

    def is_sport(self, key: str) -> bool:
        """Is activity a activity_type_key? Not regen or meta?"""
        return not self.is_regen(key) and not self.is_meta(key)

    def is_regen(self, key: str) -> bool:
        """Is activity a regeneration activity - like meditation or sauna?"""
        self._is_regen = self._is_regen or [
            at.key for at in self.activity_types_by_key.values() if at.is_regen
        ]
        return key in self._is_regen

    @staticmethod
    def is_health_issue(key: str) -> bool:
        return key in [commons.AT_SICK, commons.AT_INJURED]

    def is_distance(self, key: str) -> bool:
        """Does activity have distance?"""
        self._is_distance = self._is_distance or [
            at.key for at in self.activity_types_by_key.values() if at.is_distance
        ]
        return key in self._is_distance

    def is_meta(self, key: str) -> bool:
        """Is activity a meta activity - like comment?"""
        self._is_meta = self._is_meta or [
            at.key for at in self.activity_types_by_key.values() if at.is_meta
        ]
        return key in self._is_meta

    def is_exercise(self, key: str) -> bool:
        self._is_exercise = self._is_exercise or [
            at.key for at in self.activity_types_by_key.values() if at.is_exercise
        ]
        return key in self._is_exercise

    def update(self, activity_type: ActivityType):
        if not activity_type.key:
            raise ValueError("Activity type key must be set.")
        if activity_type.key not in self.activity_types_by_key:
            raise ValueError(
                f"Activity type cannot be updated - key '{activity_type.key}' not "
                f"found."
            )

        self.activity_types_by_key[activity_type.key] = activity_type

    def names(self) -> list[str]:
        activity_type_names = [""] + list(self.activity_types_by_name.keys())
        return activity_type_names

    def reset_counts(self):
        for s in self.activity_types_by_key.values():
            s.count = 0

    def choices(self) -> list[tuple[str, str]]:
        """list of activity types for select choices to be used with forms."""
        return [(g.key, g.name) for g in self.activity_types_by_key.values()]

    def to_list(self) -> list:
        return [g.to_dict() for g in self.activity_types_by_key.values()]

    def to_dict(self) -> dict[str, ActivityType]:
        return self.to_dict_by_key()

    def to_dict_dict(self) -> list:
        """Save as list format (new efficient format)."""
        return [g.to_dict() for g in self.activity_types_by_key.values()]

    def to_dict_by_name(self) -> dict[str, ActivityType]:
        return self.activity_types_by_name

    def to_dict_by_key(self) -> dict[str, ActivityType]:
        return self.activity_types_by_key


#
# Gear
#


class Gear:
    KEY_ACTIVITY_TYPE_KEY = "activity_type_key"
    KEY_NAME = "name"
    KEY_VENDOR = "vendor"
    KEY_MODEL = "model"
    KEY_SIZE = "size"
    KEY_COMMENT = "comment"
    KEY_URL = "url"
    KEY_RETIRED = "retired"
    KEY_IS_DEFAULT = "is_default"
    # NOTE: tcoo_base = initial purchase price of the gear
    KEY_TCOO_BASE = "tcoo_base"
    # NOTE: tcoo_cost = sum of all component costs + all service costs
    KEY_TCOO_COST = "tcoo_cost"
    KEY_TCOO_ADDITIONAL = "tcoo_additional"
    KEY_EXTERNAL_ID_MAP = "external_id_map"
    KEY_PURCHASED = "purchased"
    KEY_COMPONENTS = "components"
    KEY_COMPONENT_HISTORY = "component_history"
    KEY_LAST_ACTIVITY_PROCESSED = "last_activity_processed"
    KEY_KEY = "key"
    KEY_PHOTO_BLOB_KEYS = "photo_blob_keys"
    KEY_HIGHLIGHT_PHOTO_BLOB_KEY = "highlight_photo_blob_key"

    def __init__(
        self,
        activity_type_key: str,
        name: str,
        vendor: str = "",
        model: str = "",
        size: str = "",
        comment: str = "",
        url: str = "",
        is_default: bool = False,
        retired: bool = False,
        tcoo_base: float = 0.0,
        tcoo_cost: float = 0.0,
        tcoo_additional: float = 0.0,
        external_id_map: dict[str, str] | None = None,
        purchased: str = "",
        components: list | None = None,
        component_history: dict | None = None,
        last_activity_processed: str = "",
        key: str = "",
        photo_blob_keys: list | None = None,
        highlight_photo_blob_key: str = "",
    ) -> None:
        self.activity_type_key = activity_type_key
        self.name = name
        self.vendor = vendor
        self.model = model
        self.size = size
        self.comment = comment
        self.url = url
        self.retired = retired
        self.is_default = is_default  # is default gear for the activity_type_key

        self.tcoo_base = tcoo_base
        self.tcoo_cost = tcoo_cost
        self.tcoo_additional = tcoo_additional

        self.external_id_map = external_id_map or {}
        self.purchased = purchased  # ISO date string YYYY-MM-DD

        self.components = components or []
        self.component_history = component_history or {}
        self.last_activity_processed = last_activity_processed

        self.key = key or str(uuid.uuid4())
        self.photo_blob_keys = photo_blob_keys or []
        self.highlight_photo_blob_key = highlight_photo_blob_key

    def get_components(self, include_retired: bool = False):
        """Get components as objects.

        Parameters
        ----------
        include_retired : bool
            If True, include retired components. Default False (active only).

        Returns
        -------
        list
            List of gear components.
        """
        components = [GearComponent.from_dict(c) for c in self.components]
        if not include_retired:
            components = [c for c in components if c.status == "active"]
        return components

    def get_component(self, component_key: str):
        """Get a specific component by key.

        Parameters
        ----------
        component_key : str
            Component key.

        Returns
        -------
        GearComponent or None
            Component object or None if not found.
        """
        for c in self.components:
            if c.get("key") == component_key:
                return GearComponent.from_dict(c)
        return None

    def get_component_total_tcoo(self, component_key: str) -> float:
        """Calculate total TCoO for a component (base + all service costs).

        Parameters
        ----------
        component_key : str
            Component key.

        Returns
        -------
        float
            Total TCoO.
        """
        component = self.get_component(component_key)
        if not component:
            return 0.0

        total = component.cost  # base cost
        if component_key in self.component_history:
            for entry_dict in self.component_history[component_key]:
                total += entry_dict.get("cost", 0.0)
        return total

    def requires_attention(self) -> bool:
        """Check if any active component requires service.

        Returns
        -------
        bool
            True if any component requires service.
        """
        return any(c.requires_service for c in self.get_components())

    def get_external_id(self, service: str) -> str:
        """Get external ID for the given service."""
        service_name = (service or "").strip().lower()
        if not service_name:
            return ""
        return self.external_id_map.get(service_name, "")

    def set_external_id(self, service: str, external_id: str) -> None:
        """Set external ID for the given service."""
        service_name = (service or "").strip().lower()
        external_id_str = (external_id or "").strip()
        if not service_name:
            raise ValueError("Service name must not be empty.")
        if external_id_str:
            self.external_id_map[service_name] = external_id_str
        elif service_name in self.external_id_map:
            del self.external_id_map[service_name]

    def has_external_id(self, service: str) -> bool:
        """Check whether an external ID is available for the given service."""
        return bool(self.get_external_id(service))

    def components_requiring_service(self):
        """Get list of active components requiring service.

        Returns
        -------
        list
            List of GearComponent objects requiring service.
        """
        return [c for c in self.get_components() if c.requires_service]

    @functools.cached_property
    def _comp_by_key(self) -> dict:
        return {c.get("key"): c for c in self.components}

    def get_predecessor_chain(self, component_key: str) -> list:
        """Get the predecessor chain for a component (newest retired first).

        Follows the replaces_key links backwards from the given component key
        to build the full chain of replaced components.

        Parameters
        ----------
        component_key : str
            Key of the component to get predecessors for.

        Returns
        -------
        list
            List of gear components from most recently retired to oldest.
        """
        chain = []
        current = self._comp_by_key.get(component_key)
        if current is None:
            return chain

        replaces_key = current.get("replaces_key", "")
        visited = set()
        while replaces_key and replaces_key not in visited:
            visited.add(replaces_key)
            predecessor = self._comp_by_key.get(replaces_key)
            if predecessor is None:
                break
            chain.append(GearComponent.from_dict(predecessor))
            replaces_key = predecessor.get("replaces_key", "")

        return chain

    @property
    def tcoo_total(self) -> float:
        """Calculate total cost of ownership.

        Returns
        -------
        float
            Total cost of ownership (base + maintenance + additional).
        """
        return self.tcoo_base + self.tcoo_cost + self.tcoo_additional

    def recalculate_tcoo(self) -> None:
        """Recalculate maintenance cost from all components and service history."""
        total_cost = 0.0

        # add all component base costs
        for component in self.get_components(include_retired=True):
            total_cost += component.cost

        # add all service costs from history
        for component_key, history_list in self.component_history.items():
            for entry_dict in history_list:
                total_cost += entry_dict.get("cost", 0.0)

        self.tcoo_cost = total_cost

    def recalculate_component_usage_from_gear_stats(self, gear_stats) -> None:
        """
        Recalculate component usage from gear statistics.

        This should be called when:
        - A new component is added (to initialize its usage from current gear usage)
        - User wants to backfill component data

        Parameters
        ----------
        gear_stats : GearStats
            Statistics object containing total distance and time for this gear
        """
        if not self.components or not gear_stats:
            return

        total_distance_m = gear_stats.stat_meters or 0
        total_time_s = gear_stats.stat_seconds or 0

        # update all active components with current gear totals
        for comp_dict in self.components:
            if comp_dict.get("status") == "active":
                # components inherit full gear usage as baseline
                comp_dict["distance_meters"] = total_distance_m
                comp_dict["time_seconds"] = total_time_s

    def to_dict(self) -> dict:
        return {
            Gear.KEY_ACTIVITY_TYPE_KEY: self.activity_type_key,
            Gear.KEY_NAME: self.name,
            Gear.KEY_VENDOR: self.vendor,
            Gear.KEY_MODEL: self.model,
            Gear.KEY_SIZE: self.size,
            Gear.KEY_COMMENT: self.comment,
            Gear.KEY_URL: self.url,
            Gear.KEY_RETIRED: self.retired,
            Gear.KEY_IS_DEFAULT: self.is_default,
            Gear.KEY_TCOO_BASE: self.tcoo_base,
            Gear.KEY_TCOO_COST: self.tcoo_cost,
            Gear.KEY_TCOO_ADDITIONAL: self.tcoo_additional,
            Gear.KEY_EXTERNAL_ID_MAP: self.external_id_map,
            Gear.KEY_PURCHASED: self.purchased,
            Gear.KEY_COMPONENTS: self.components,
            Gear.KEY_COMPONENT_HISTORY: self.component_history,
            Gear.KEY_LAST_ACTIVITY_PROCESSED: self.last_activity_processed,
            Gear.KEY_KEY: self.key,
            Gear.KEY_PHOTO_BLOB_KEYS: self.photo_blob_keys,
            Gear.KEY_HIGHLIGHT_PHOTO_BLOB_KEY: self.highlight_photo_blob_key,
        }

    @staticmethod
    def from_dict(gear_dict: dict) -> "Gear":
        external_id_map_dict = gear_dict.get(Gear.KEY_EXTERNAL_ID_MAP, {})
        if not isinstance(external_id_map_dict, dict):
            external_id_map_dict = {}
        normalized_external_id_map = {}
        for service_name, external_id in external_id_map_dict.items():
            service_name_str = str(service_name).strip().lower()
            external_id_str = str(external_id).strip()
            if service_name_str and external_id_str:
                normalized_external_id_map[service_name_str] = external_id_str

        return Gear(
            activity_type_key=gear_dict.get(
                Gear.KEY_ACTIVITY_TYPE_KEY, commons.AT_COMMENT
            ),
            name=gear_dict[Gear.KEY_NAME],
            vendor=gear_dict.get(Gear.KEY_VENDOR, ""),
            model=gear_dict.get(Gear.KEY_MODEL, ""),
            size=gear_dict.get(Gear.KEY_SIZE, ""),
            comment=gear_dict.get(Gear.KEY_COMMENT, ""),
            url=gear_dict.get(Gear.KEY_URL, ""),
            retired=gear_dict.get(Gear.KEY_RETIRED, False),
            is_default=gear_dict.get(Gear.KEY_IS_DEFAULT, False),
            tcoo_base=gear_dict.get(Gear.KEY_TCOO_BASE, 0.0),
            tcoo_cost=gear_dict.get(Gear.KEY_TCOO_COST, 0.0),
            tcoo_additional=gear_dict.get(Gear.KEY_TCOO_ADDITIONAL, 0.0),
            external_id_map=normalized_external_id_map,
            purchased=gear_dict.get(Gear.KEY_PURCHASED, ""),
            components=gear_dict.get(Gear.KEY_COMPONENTS, []),
            component_history=gear_dict.get(Gear.KEY_COMPONENT_HISTORY, {}),
            last_activity_processed=gear_dict.get(Gear.KEY_LAST_ACTIVITY_PROCESSED, ""),
            key=gear_dict.get(Gear.KEY_KEY, ""),
            photo_blob_keys=gear_dict.get(Gear.KEY_PHOTO_BLOB_KEYS, []),
            highlight_photo_blob_key=gear_dict.get(
                Gear.KEY_HIGHLIGHT_PHOTO_BLOB_KEY, ""
            ),
        )


class UserGear:
    """Custom gear defined by the user is aggregated from multiple sources:

    - user profile: gear defined by the user in MyTraL

    3rd party gear import and mapping cross services like Strava/Garmin/*:

    - external_ids map: service > gear ID in that service
    - Strava: gear imported from Strava

    Gear is merged as follows:

    - user profile gear is used as a base
    - strava gear is added
    - user can merge strava gear to a user profile gear
      (in this case all activities in all user datasets are updated
      and new gear key is set)
    - strava gears cannot be merged to each other
    - gear can be marked as retired (rendered as inactive)

    Integrity:

    - a gear which is used by 1 or more activities in ``lifelong`` cannot be deleted

    """

    SERVICE_STRAVA = "strava"
    SERVICE_GARMIN_CONNECT = "garmin_connect"
    SERVICE_POLAR_FLOW = "polar_flow"
    SERVICE_POLAR_PPP = "polar_ppp"

    @staticmethod
    def from_dict_dict(gear_data: dict | list) -> "UserGear":
        """Load from dict (old) or list (new) format."""
        gear_dict = persistences.normalize_dict_or_list_to_dict(gear_data)
        gears = []
        for mytral_key in gear_dict:
            gears.append(Gear.from_dict(gear_dict[mytral_key]))
        gears.sort(key=lambda x: x.name)
        return UserGear(gear=gears)

    @staticmethod
    def from_dict(gear_list: list) -> "UserGear":
        gears = [Gear.from_dict(g) for g in gear_list]
        gears.sort(key=lambda x: x.name)
        return UserGear(gear=gears)

    @staticmethod
    def bootstrap() -> "UserGear":
        """This is initial set of gears which is used only if the user profile does not
        contain any gear.

        """
        gears: list[Gear] = []
        gears.sort(key=lambda x: x.name)

        return UserGear(gear=gears)

    @property
    def gear(self) -> dict[str, Gear]:
        """Avoid having authoritative data twice."""
        if self.gear_by_key:
            # map: name -> gear
            return {g.name: g for g in self.gear_by_key.values()}
        return {}

    def __init__(self, gear: list[Gear]) -> None:
        # map: key -> gear
        self.gear_by_key: dict[str, Gear] = {}
        for g in gear:
            if not g.key:
                g.key = str(uuid.uuid4())
            self.gear_by_key[g.key] = g

        self.activity_type_2_gear: dict[str, Gear] = {}
        for g in gear:
            if g.is_default and g.activity_type_key:
                self.activity_type_2_gear[g.activity_type_key] = g

    def exists(self, key: str) -> bool:
        return key in self.gear_by_key

    def delete(self, key: str):
        del self.gear_by_key[key]

    def add_gear(self, gear: Gear):
        if not gear.key:
            gear.key = str(uuid.uuid4())

        self.gear_by_key[gear.key] = gear

    def update(self, gear: Gear):
        if not gear.key:
            raise ValueError("Gear key must be set.")
        if gear.key not in self.gear_by_key:
            raise ValueError(f"Gear cannot be updated - key '{gear.key}' not found.")

        self.gear_by_key[gear.key] = gear

    def names(self, activity: str = "") -> list[str]:
        del activity
        gear_names = [""] + list(self.gear.keys())
        return gear_names

    def external_ids(self, service: str) -> list[str]:
        service_name = (service or "").strip().lower()
        if not service_name:
            return []
        service_ids = []
        for g in self.gear_by_key.values():
            external_id = g.get_external_id(service_name)
            if external_id:
                service_ids.append(external_id)
        return service_ids

    def choices(self) -> list[tuple[str, str]]:
        """list of gear types for select choices to be used with forms."""
        return [(g.key, g.name) for g in self.gear_by_key.values()]

    def to_list(self) -> list:
        return [g.to_dict() for g in self.gear_by_key.values()]

    def to_dict(self) -> dict[str, Gear]:
        return self.to_dict_by_key()

    def to_dict_dict(self) -> list:
        """Save as list format (new efficient format)."""
        return [g.to_dict() for g in self.gear_by_key.values()]

    def to_dict_by_name(self) -> dict[str, Gear]:
        return self.gear

    def to_dict_by_key(self) -> dict[str, Gear]:
        return self.gear_by_key

    def to_dict_by_external_id(self, service: str) -> dict[str, Gear]:
        service_name = (service or "").strip().lower()
        if not service_name:
            return {}
        result = {}
        for g in self.gear.values():
            external_id = g.get_external_id(service_name)
            if not external_id:
                continue
            result[external_id] = g
            if service_name == "strava":
                if external_id.startswith(icommons.STRAVA_GEAR_PREFIX_ID):
                    result[external_id.replace(icommons.STRAVA_GEAR_PREFIX_ID, "")] = g
                else:
                    result[f"{icommons.STRAVA_GEAR_PREFIX_ID}{external_id}"] = g

        return result


class ComponentServiceHistoryEntry:
    """Represents a service event for a component.

    Notes on data types:
    - km_at_service and hours_at_service are stored as float for cleaner display
    - These represent usage since the last service (or install) at the time of service
    - i.e. km_since_service and hours_since_service snapshots at service time
    """

    def __init__(
        self,
        date: str,
        km_at_service: float,
        hours_at_service: float,
        service_type: str,
        cost: float = 0.0,
        notes: str = "",
        key: str = "",
    ) -> None:
        self.date = date
        self.km_at_service = km_at_service
        self.hours_at_service = hours_at_service
        self.service_type = service_type
        self.cost = cost
        self.notes = notes
        self.key = key or str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "key": self.key,
            "date": self.date,
            "km_at_service": self.km_at_service,
            "hours_at_service": self.hours_at_service,
            "service_type": self.service_type,
            "cost": self.cost,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create from dictionary."""
        return cls(
            key=data.get("key", ""),
            date=data.get("date", ""),
            km_at_service=data.get("km_at_service", 0.0),
            hours_at_service=data.get("hours_at_service", 0.0),
            service_type=data.get("service_type", ""),
            cost=data.get("cost", 0.0),
            notes=data.get("notes", ""),
        )


class ComponentTemplate:
    """User-defined or built-in component template."""

    def __init__(
        self,
        name: str,
        category: str,
        default_service_km: int | None = None,
        default_service_hours: int | None = None,
        default_service_months: int | None = None,
        notes: str = "",
        key: str = "",
    ) -> None:
        self.name = name
        self.category = category
        self.default_service_km = default_service_km
        self.default_service_hours = default_service_hours
        self.default_service_months = default_service_months
        self.notes = notes
        self.key = key or str(uuid.uuid4())

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "key": self.key,
            "name": self.name,
            "category": self.category,
            "default_service_km": self.default_service_km,
            "default_service_hours": self.default_service_hours,
            "default_service_months": self.default_service_months,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create from dictionary."""
        return cls(
            key=data.get("key", ""),
            name=data.get("name", ""),
            category=data.get("category", ""),
            default_service_km=data.get("default_service_km"),
            default_service_hours=data.get("default_service_hours"),
            default_service_months=data.get("default_service_months"),
            notes=data.get("notes", ""),
        )


class UserComponentTemplates:
    """Container for user-defined component templates."""

    def __init__(self) -> None:
        self.templates_by_key: dict[str, ComponentTemplate] = {}

    @property
    def templates(self) -> list[ComponentTemplate]:
        """Templates as a list, sorted by category then name."""
        return sorted(
            self.templates_by_key.values(), key=lambda t: (t.category, t.name)
        )

    def add(self, template: ComponentTemplate) -> None:
        """Add template to the collection."""
        self.templates_by_key[template.key] = template

    def update(self, template: ComponentTemplate) -> None:
        """Update an existing template."""
        if template.key not in self.templates_by_key:
            raise ValueError(
                f"Template cannot be updated - key '{template.key}' not found."
            )
        self.templates_by_key[template.key] = template

    def delete(self, key: str) -> None:
        """Remove template by key."""
        if key in self.templates_by_key:
            del self.templates_by_key[key]

    def get_by_key(self, key: str) -> ComponentTemplate | None:
        """Get template by key."""
        return self.templates_by_key.get(key)

    def for_category(self, category: str) -> list[ComponentTemplate]:
        """Return templates matching the given activity_type_key category."""
        return [t for t in self.templates if t.category == category]

    def to_dict(self) -> list:
        """Serialize all templates to list for JSON storage."""
        return [t.to_dict() for t in self.templates_by_key.values()]

    @classmethod
    def from_dict(cls, data: list | dict) -> Self:
        """Create from a JSON list (or legacy dict)."""
        container = cls()
        if isinstance(data, dict):
            items = data.values()
        else:
            items = data
        for item in items:
            container.add(ComponentTemplate.from_dict(item))
        return container


# pre-defined component templates
COMPONENT_TEMPLATES = [
    # cycling components
    ComponentTemplate("Chain", "cycling", default_service_km=500),
    ComponentTemplate("Cassette", "cycling", default_service_km=2000),
    ComponentTemplate("Brake Pads (Front)", "cycling", default_service_km=1000),
    ComponentTemplate("Brake Pads (Rear)", "cycling", default_service_km=1000),
    ComponentTemplate("Tire (Front)", "cycling", default_service_km=3000),
    ComponentTemplate("Tire (Rear)", "cycling", default_service_km=2500),
    ComponentTemplate(
        "Fork Service",
        "cycling",
        default_service_hours=50,
        default_service_months=12,
    ),
    ComponentTemplate(
        "Shock Service",
        "cycling",
        default_service_hours=50,
        default_service_months=12,
    ),
    ComponentTemplate("Bottom Bracket", "cycling", default_service_km=5000),
    ComponentTemplate("Headset", "cycling", default_service_km=10000),
    ComponentTemplate("Cables", "cycling", default_service_km=2000),
    # running components
    ComponentTemplate("Running Shoes", "running", default_service_km=800),
    ComponentTemplate("Insoles", "running", default_service_km=800),
    ComponentTemplate("Laces", "running", default_service_km=1500),
    # swimming components
    ComponentTemplate("Goggles", "swimming", default_service_months=12),
    ComponentTemplate("Swim Cap", "swimming", default_service_months=6),
    ComponentTemplate("Wetsuit", "swimming", default_service_months=24),
    # skiing components
    ComponentTemplate("Ski Wax", "skiing", default_service_km=100),
    ComponentTemplate("Ski Edges", "skiing", default_service_km=500),
    ComponentTemplate("Ski Bindings", "skiing", default_service_months=12),
]


class GearComponent:
    """Represents a single component of gear."""

    def __init__(
        self,
        name: str,
        cost: float = 0.0,
        installed_date: str = "",
        last_service_date: str = "",
        last_service_km: float = 0.0,
        last_service_hours: float = 0.0,
        next_service_km: int | None = None,
        next_service_hours: int | None = None,
        next_service_months: int | None = None,
        distance_meters: int = 0,
        time_seconds: int = 0,
        status: str = "active",
        replaced_by_key: str = "",
        replaces_key: str = "",
        notes: str = "",
        key: str = "",
    ) -> None:
        self.name = name
        self.cost = cost
        self.installed_date = installed_date
        self.last_service_date = last_service_date
        self.last_service_km = last_service_km
        self.last_service_hours = last_service_hours
        self.next_service_km = next_service_km
        self.next_service_hours = next_service_hours
        self.next_service_months = next_service_months
        self.distance_meters = distance_meters
        self.time_seconds = time_seconds
        self.status = status
        self.replaced_by_key = replaced_by_key
        self.replaces_key = replaces_key
        self.notes = notes
        self.key = key or str(uuid.uuid4())

    @property
    def distance_km(self) -> float:
        """Distance in kilometers."""
        return self.distance_meters / 1000.0

    @property
    def time_hours(self) -> float:
        """Time in hours."""
        return self.time_seconds / 3600.0

    @property
    def km_since_service(self) -> float:
        """Kilometers since last service."""
        return self.distance_km - self.last_service_km

    @property
    def hours_since_service(self) -> float:
        """Hours since last service."""
        return self.time_hours - self.last_service_hours

    @property
    def requires_service_km(self) -> bool:
        """Check if service is due based on kilometers."""
        if self.next_service_km is None:
            return False
        return self.km_since_service >= self.next_service_km

    @property
    def requires_service_hours(self) -> bool:
        """Check if service is due based on hours."""
        if self.next_service_hours is None:
            return False
        return self.hours_since_service >= self.next_service_hours

    @property
    def requires_service_time(self) -> bool:
        """Check if service is due based on time (months)."""
        if self.next_service_months is None:
            return False
        return self.service_progress_time >= 1.0

    @property
    def requires_service(self) -> bool:
        """Check if service is due (km, hours, or time)."""
        if self.status == "retired":
            return False
        return (
            self.requires_service_km
            or self.requires_service_hours
            or self.requires_service_time
        )

    @property
    def service_progress_km(self) -> float:
        """Progress towards next service by km (0.0 to 1.0+)."""
        if self.next_service_km is None or self.next_service_km == 0:
            return 0.0
        return self.km_since_service / self.next_service_km

    @property
    def service_progress_hours(self) -> float:
        """Progress towards next service by hours (0.0 to 1.0+)."""
        if self.next_service_hours is None or self.next_service_hours == 0:
            return 0.0
        return self.hours_since_service / self.next_service_hours

    @property
    def service_progress_time(self) -> float:
        """Progress towards next service by time (0.0 to 1.0+)."""
        if self.next_service_months is None:
            return 0.0

        try:
            from dateutil.relativedelta import relativedelta
        except ImportError:
            return 0.0

        service_date = (
            self.last_service_date if self.last_service_date else self.installed_date
        )
        if not service_date:
            return 0.0

        try:
            service_dt = datetime.fromisoformat(service_date)
            next_service_dt = service_dt + relativedelta(
                months=self.next_service_months
            )
            total_seconds = (next_service_dt - service_dt).total_seconds()
            elapsed_seconds = (datetime.now() - service_dt).total_seconds()

            if total_seconds == 0:
                return 0.0
            return elapsed_seconds / total_seconds
        except (ValueError, TypeError):
            return 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "key": self.key,
            "name": self.name,
            "cost": self.cost,
            "installed_date": self.installed_date,
            "last_service_date": self.last_service_date,
            "last_service_km": self.last_service_km,
            "last_service_hours": self.last_service_hours,
            "next_service_km": self.next_service_km,
            "next_service_hours": self.next_service_hours,
            "next_service_months": self.next_service_months,
            "distance_meters": self.distance_meters,
            "time_seconds": self.time_seconds,
            "status": self.status,
            "replaced_by_key": self.replaced_by_key,
            "replaces_key": self.replaces_key,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create from dictionary."""
        return cls(
            key=data.get("key", ""),
            name=data.get("name", ""),
            cost=data.get("cost", 0.0),
            installed_date=data.get("installed_date", ""),
            last_service_date=data.get("last_service_date", ""),
            last_service_km=data.get("last_service_km", 0.0),
            last_service_hours=data.get("last_service_hours", 0.0),
            next_service_km=data.get("next_service_km"),
            next_service_hours=data.get("next_service_hours"),
            next_service_months=data.get("next_service_months"),
            distance_meters=data.get("distance_meters", 0),
            time_seconds=data.get("time_seconds", 0),
            status=data.get("status", "active"),
            replaced_by_key=data.get("replaced_by_key", ""),
            replaces_key=data.get("replaces_key", ""),
            notes=data.get("notes", ""),
        )


#
# Symptoms
#


class Symptom:
    """Sickness and/or injury symptom."""

    S_TENDON_PAIN = "tendon pain"
    S_PAIN = "pain"
    S_COLD = "cold"
    S_CAUGHT = "caught"
    S_THROMBOSIS = "thrombosis"

    KEY_NAME = "name"
    KEY_COUNT = "count"
    KEY_KEY = "key"
    KEY_BODY_PARTS = "body_parts"
    KEY_DESCRIPTION = "description"

    def __init__(
        self,
        name: str,
        key: str = "",
        body_parts: list[str] | None = None,
        description: str = "",
    ) -> None:
        self.name = name
        self.key = key or str(uuid.uuid4())
        self.body_parts: list[str] = body_parts or []
        self.description = description

    def to_dict(self) -> dict:
        return {
            Symptom.KEY_NAME: self.name,
            Symptom.KEY_KEY: self.key,
            Symptom.KEY_BODY_PARTS: self.body_parts,
            Symptom.KEY_DESCRIPTION: self.description,
        }

    @staticmethod
    def from_dict(symptom_dict: dict) -> "Symptom":
        return Symptom(
            name=symptom_dict[Symptom.KEY_NAME],
            key=symptom_dict.get(Symptom.KEY_KEY, ""),
            body_parts=symptom_dict.get(Symptom.KEY_BODY_PARTS, []),
            description=symptom_dict.get(Symptom.KEY_DESCRIPTION, ""),
        )


_BODY_PARTS_BY_REGION: dict[str, list[str]] = {
    "head": ["front-head", "back-head"],
    "neck": ["front-neck", "back-neck"],
    "shoulder_left": ["front-shoulder-l", "back-shoulder-l"],
    "shoulder_right": ["front-shoulder-r", "back-shoulder-r"],
    "chest": ["front-chest"],
    "upper_back": ["back-upper", "back-lats-r", "back-lats-l"],
    "lower_back": ["back-lower"],
    "arm_left": ["front-arm-l", "back-arm-l"],
    "arm_right": ["front-arm-r", "back-arm-r"],
    "elbow_left": ["front-elbow-l", "back-elbow-l"],
    "elbow_right": ["front-elbow-r", "back-elbow-r"],
    "forearm_left": ["front-forearm-l", "back-forearm-l"],
    "forearm_right": ["front-forearm-r", "back-forearm-r"],
    "wrist_left": ["front-wrist-l", "back-wrist-l"],
    "wrist_right": ["front-wrist-r", "back-wrist-r"],
    "hand_left": ["front-hand-l", "back-hand-l"],
    "hand_right": ["front-hand-r", "back-hand-r"],
    "hip_left": ["front-hip-l", "back-hip-l"],
    "hip_right": ["front-hip-r", "back-hip-r"],
    "thigh_left": ["front-thigh-l", "back-thigh-l"],
    "thigh_right": ["front-thigh-r", "back-thigh-r"],
    "knee_left": ["front-knee-l", "back-knee-l"],
    "knee_right": ["front-knee-r", "back-knee-r"],
    "calf_left": ["front-calf-l", "back-calf-l"],
    "calf_right": ["front-calf-r", "back-calf-r"],
    "ankle_left": ["front-ankle-l", "back-ankle-l"],
    "ankle_right": ["front-ankle-r", "back-ankle-r"],
    "foot_left": ["front-foot-l", "back-foot-l"],
    "foot_right": ["front-foot-r", "back-foot-r"],
}

_ALL_BODY_PART_IDS: set[str] = {
    body_part_id
    for region_body_parts in _BODY_PARTS_BY_REGION.values()
    for body_part_id in region_body_parts
}

_BOOTSTRAP_SYMPTOM_BODY_PARTS_BY_NAME: dict[str, list[str]] = {
    "allergy": _BODY_PARTS_BY_REGION["head"] + _BODY_PARTS_BY_REGION["neck"],
    "asthma": _BODY_PARTS_BY_REGION["chest"] + _BODY_PARTS_BY_REGION["upper_back"],
    "bronchitis": _BODY_PARTS_BY_REGION["chest"] + _BODY_PARTS_BY_REGION["upper_back"],
    Symptom.S_CAUGHT: _BODY_PARTS_BY_REGION["head"] + _BODY_PARTS_BY_REGION["neck"],
    Symptom.S_COLD: _BODY_PARTS_BY_REGION["head"] + _BODY_PARTS_BY_REGION["neck"],
    "covid": (
        _BODY_PARTS_BY_REGION["chest"]
        + _BODY_PARTS_BY_REGION["upper_back"]
        + _BODY_PARTS_BY_REGION["head"]
    ),
    "diarrhea": _BODY_PARTS_BY_REGION["chest"] + _BODY_PARTS_BY_REGION["lower_back"],
    "fever": _BODY_PARTS_BY_REGION["head"] + _BODY_PARTS_BY_REGION["chest"],
    "flu": (
        _BODY_PARTS_BY_REGION["head"]
        + _BODY_PARTS_BY_REGION["neck"]
        + _BODY_PARTS_BY_REGION["chest"]
    ),
    "food poisoning": (
        _BODY_PARTS_BY_REGION["chest"] + _BODY_PARTS_BY_REGION["lower_back"]
    ),
    "gastroenteritis": (
        _BODY_PARTS_BY_REGION["chest"] + _BODY_PARTS_BY_REGION["lower_back"]
    ),
    "headache": _BODY_PARTS_BY_REGION["head"] + _BODY_PARTS_BY_REGION["neck"],
    "heartburn": _BODY_PARTS_BY_REGION["chest"],
    "influenza": (
        _BODY_PARTS_BY_REGION["head"]
        + _BODY_PARTS_BY_REGION["neck"]
        + _BODY_PARTS_BY_REGION["chest"]
    ),
    "migraine": _BODY_PARTS_BY_REGION["head"] + _BODY_PARTS_BY_REGION["neck"],
    "muscle pain": (
        _BODY_PARTS_BY_REGION["upper_back"]
        + _BODY_PARTS_BY_REGION["lower_back"]
        + _BODY_PARTS_BY_REGION["thigh_left"]
        + _BODY_PARTS_BY_REGION["thigh_right"]
    ),
    "nausea": _BODY_PARTS_BY_REGION["chest"],
    Symptom.S_PAIN: (
        _BODY_PARTS_BY_REGION["lower_back"]
        + _BODY_PARTS_BY_REGION["shoulder_left"]
        + _BODY_PARTS_BY_REGION["shoulder_right"]
    ),
    "pneumonia": _BODY_PARTS_BY_REGION["chest"] + _BODY_PARTS_BY_REGION["upper_back"],
    "pressure": _BODY_PARTS_BY_REGION["head"] + _BODY_PARTS_BY_REGION["chest"],
    "rash": (
        _BODY_PARTS_BY_REGION["chest"]
        + _BODY_PARTS_BY_REGION["arm_left"]
        + _BODY_PARTS_BY_REGION["arm_right"]
    ),
    "reflux": _BODY_PARTS_BY_REGION["chest"],
    "sinusitis": _BODY_PARTS_BY_REGION["head"] + _BODY_PARTS_BY_REGION["neck"],
    "sore throat": _BODY_PARTS_BY_REGION["neck"],
    "stomach ache": _BODY_PARTS_BY_REGION["chest"]
    + _BODY_PARTS_BY_REGION["lower_back"],
    Symptom.S_TENDON_PAIN: (
        _BODY_PARTS_BY_REGION["elbow_left"]
        + _BODY_PARTS_BY_REGION["elbow_right"]
        + _BODY_PARTS_BY_REGION["knee_left"]
        + _BODY_PARTS_BY_REGION["knee_right"]
    ),
    Symptom.S_THROMBOSIS: (
        _BODY_PARTS_BY_REGION["calf_left"]
        + _BODY_PARTS_BY_REGION["calf_right"]
        + _BODY_PARTS_BY_REGION["thigh_left"]
        + _BODY_PARTS_BY_REGION["thigh_right"]
    ),
    "toothache": _BODY_PARTS_BY_REGION["head"],
    "torn muscle": (
        _BODY_PARTS_BY_REGION["thigh_left"]
        + _BODY_PARTS_BY_REGION["thigh_right"]
        + _BODY_PARTS_BY_REGION["calf_left"]
        + _BODY_PARTS_BY_REGION["calf_right"]
    ),
    "vomiting": _BODY_PARTS_BY_REGION["chest"],
}


def _validate_body_part_ids(body_parts: list[str]) -> list[str]:
    return [body_part for body_part in body_parts if body_part in _ALL_BODY_PART_IDS]


class UserSymptoms:
    """Custom sickness and/or injury symptom types defined by the user."""

    # default symptoms for new users
    BOOTSTRAP = [
        "allergy",
        "asthma",
        "bronchitis",
        Symptom.S_CAUGHT,
        Symptom.S_COLD,
        "covid",
        "diarrhea",
        "fever",
        "flu",
        "food poisoning",
        "gastroenteritis",
        "headache",
        "heartburn",
        "influenza",
        "migraine",
        "muscle pain",
        "nausea",
        Symptom.S_PAIN,
        "pneumonia",
        "pressure",
        "rash",
        "reflux",
        "sinusitis",
        "sore throat",
        "stomach ache",
        Symptom.S_TENDON_PAIN,
        Symptom.S_THROMBOSIS,
        "toothache",
        "torn muscle",
        "vomiting",
    ]

    @staticmethod
    def bootstrap() -> list[Symptom]:
        missing_defaults = sorted(
            set(UserSymptoms.BOOTSTRAP)
            - set(_BOOTSTRAP_SYMPTOM_BODY_PARTS_BY_NAME.keys())
        )
        if missing_defaults:
            raise ValueError(
                "Missing bootstrap symptom body parts for: "
                + ", ".join(missing_defaults)
            )

        symptoms = []
        for symptom_name in UserSymptoms.BOOTSTRAP:
            symptoms.append(
                Symptom(
                    name=symptom_name,
                    key=generate_bootstrap_uuid(symptom_name),
                    body_parts=_validate_body_part_ids(
                        _BOOTSTRAP_SYMPTOM_BODY_PARTS_BY_NAME[symptom_name]
                    ),
                )
            )

        return symptoms

    @staticmethod
    def from_dict_dict(symptom_data: dict | list) -> "UserSymptoms":
        """Load from dict (old) or list (new) format."""
        symptom_dict = persistences.normalize_dict_or_list_to_dict(symptom_data)
        symptoms = []
        if not symptom_dict:
            symptoms = UserSymptoms.bootstrap()
        else:
            for mytral_key in symptom_dict:
                symptoms.append(Symptom.from_dict(symptom_dict[mytral_key]))

        symptoms.sort(key=lambda x: x.name)
        return UserSymptoms(symptoms=symptoms)

    @property
    def symptoms_by_name(self) -> dict[str, Symptom]:
        """Avoid having authoritative data twice."""
        if self.symptoms_by_key:
            # map: name -> symptom
            return {g.name: g for g in self.symptoms_by_key.values()}
        return {}

    def __init__(self, symptoms: list[Symptom]) -> None:
        # map: name -> key
        self.symptoms_by_key: dict[str, Symptom] = {}
        for g in symptoms:
            if not g.key:
                g.key = str(uuid.uuid4())
            self.symptoms_by_key[g.key] = g

    def empty(self) -> bool:
        return len(self.symptoms_by_key) == 0

    def is_bootstrap_only(self) -> bool:
        """Check if collection contains only unmodified bootstrap data.

        Returns
        -------
        bool
            True if only bootstrap symptoms are present

        """
        return is_bootstrap_data_only(self.symptoms_by_key, UserSymptoms.BOOTSTRAP)

    def name(self, key: str, fallback: str = "") -> str:
        return self.symptoms_by_key[key].name if self.exists(key) else fallback

    def default_symptom(self) -> Symptom | None:
        if self.empty():
            return None
        return list(self.symptoms_by_key.values())[0]

    def exists(self, key: str) -> bool:
        return key in self.symptoms_by_key

    def update(self, symptom: Symptom):
        if not symptom.key:
            raise ValueError("Symptom key must be set.")
        if symptom.key not in self.symptoms_by_key:
            raise ValueError(
                f"Symptom cannot be updated - key '{symptom.key}' not found."
            )

        self.symptoms_by_key[symptom.key] = symptom

    def delete(self, key: str):
        if not key:
            raise ValueError("Cannot delete symptom -  key must be non-empty.")
        if key not in self.symptoms_by_key:
            raise ValueError(f"Symptom cannot be deleted - key '{key}' not found.")

        del self.symptoms_by_key[key]

    def add_symptom(self, symptom: Symptom):
        if not symptom.key:
            symptom.key = str(uuid.uuid4())

        self.symptoms_by_key[symptom.key] = symptom

    def names(self) -> list[str]:
        symptom_names = [""] + list(self.symptoms_by_name.keys())
        return symptom_names

    def reset_counts(self):
        for s in self.symptoms_by_key.values():
            s.count = 0

    def to_list(self) -> list:
        return [g.to_dict() for g in self.symptoms_by_key.values()]

    def to_dict(self) -> dict[str, Symptom]:
        return self.to_dict_by_key()

    def to_dict_dict(self) -> list:
        """Save as list format (new efficient format)."""
        return [g.to_dict() for g in self.symptoms_by_key.values()]

    def to_dict_by_name(self) -> dict[str, Symptom]:
        return self.symptoms_by_name

    def to_dict_by_key(self) -> dict[str, Symptom]:
        return self.symptoms_by_key


#
# Exercises
#


class Exercise:
    KEY_NAME = "name"
    KEY_DESCRIPTION = "description"
    KEY_WEIGHT = "weight"
    KEY_COUNT = "count"
    KEY_KEY = "key"
    KEY_TAGS = "tags"
    KEY_MUSCLE_GROUPS = "muscle_groups"
    KEY_MUSCLE_GROUPS_SECONDARY = "muscle_groups_secondary"
    KEY_PHOTO_BLOB_KEYS = "photo_blob_keys"
    KEY_HIGHLIGHT_PHOTO_BLOB_KEY = "highlight_photo_blob_key"

    def __init__(
        self,
        name: str,
        description: str = "",
        weight: float = 0.0,
        tags: list[str] | None = None,
        muscle_groups: list[str] | None = None,
        muscle_groups_secondary: list[str] | None = None,
        key: str = "",
        photo_blob_keys: list | None = None,
        highlight_photo_blob_key: str = "",
    ) -> None:
        self.name = name
        self.description = description
        self.weight = weight
        self.tags = tags or []
        self.muscle_groups = muscle_groups or []
        self.muscle_groups_secondary = muscle_groups_secondary or []

        self.key = key or str(uuid.uuid4())
        self.photo_blob_keys = photo_blob_keys or []
        self.highlight_photo_blob_key = highlight_photo_blob_key

    def to_dict(self) -> dict:
        return {
            Exercise.KEY_NAME: self.name,
            Exercise.KEY_DESCRIPTION: self.description,
            Exercise.KEY_WEIGHT: self.weight,
            Exercise.KEY_TAGS: self.tags,
            Exercise.KEY_MUSCLE_GROUPS: self.muscle_groups,
            Exercise.KEY_MUSCLE_GROUPS_SECONDARY: self.muscle_groups_secondary,
            Exercise.KEY_KEY: self.key,
            Exercise.KEY_PHOTO_BLOB_KEYS: self.photo_blob_keys,
            Exercise.KEY_HIGHLIGHT_PHOTO_BLOB_KEY: self.highlight_photo_blob_key,
        }

    @staticmethod
    def from_dict(exercise_dict: dict) -> "Exercise":
        return Exercise(
            name=exercise_dict[Exercise.KEY_NAME],
            description=exercise_dict.get(Exercise.KEY_DESCRIPTION, ""),
            weight=exercise_dict.get(Exercise.KEY_WEIGHT, 0.0),
            tags=exercise_dict.get(Exercise.KEY_TAGS, []),
            muscle_groups=mg.validate_muscle_keys(
                exercise_dict.get(Exercise.KEY_MUSCLE_GROUPS, [])
            ),
            muscle_groups_secondary=mg.validate_muscle_keys(
                exercise_dict.get(Exercise.KEY_MUSCLE_GROUPS_SECONDARY, [])
            ),
            key=exercise_dict.get(Exercise.KEY_KEY, ""),
            photo_blob_keys=exercise_dict.get(Exercise.KEY_PHOTO_BLOB_KEYS, []),
            highlight_photo_blob_key=exercise_dict.get(
                Exercise.KEY_HIGHLIGHT_PHOTO_BLOB_KEY, ""
            ),
        )


@dataclasses.dataclass(frozen=True)
class _BootstrapExerciseDefaults:
    description: str
    weight: float
    tags: tuple[str, ...]
    muscle_groups: tuple[str, ...]
    muscle_groups_secondary: tuple[str, ...]


def _exercise_howto(
    *,
    setup: str,
    execution: str,
    breathing: str,
    form_cue: str,
) -> str:
    return (
        f"- **Setup:**\n"
        f"  - {setup}\n"
        f"- **Execution:**\n"
        f"  - {execution}\n"
        f"- **Breathing:**\n"
        f"  - {breathing}\n"
        f"- **Form cue:**\n"
        f"  - {form_cue}"
    )


_BOOTSTRAP_EXERCISE_PURPOSE_BY_NAME: dict[str, str] = {
    "barbell row": (
        "Use this exercise to build a stronger upper back and better pulling power."
    ),
    "bench press": (
        "Use this exercise to improve chest pressing strength for upper-body power."
    ),
    "bicep curl": (
        "Use this exercise to strengthen your biceps for arm pulling and grip support."
    ),
    "calf-lift": (
        "Use this exercise to build calf strength for running and ankle stability."
    ),
    "clean hands": (
        "Use this exercise to train explosive full-body power and coordination."
    ),
    "crunch": (
        "Use this exercise to strengthen abdominal muscles and improve trunk control."
    ),
    "deadlift": (
        "Use this exercise to build full-body strength, especially the posterior chain."
    ),
    "dumbbell curl": (
        "Use this exercise to improve single-arm biceps strength and arm symmetry."
    ),
    "dumbbell fly": (
        "Use this exercise to isolate your chest and improve stretch-based activation."
    ),
    "dumbbell press": (
        "Use this exercise to build chest and shoulder strength with stabilizer work."
    ),
    "dumbbell row": (
        "Use this exercise to strengthen lats and improve left-right pulling balance."
    ),
    "front raise": (
        "Use this exercise to target front delts for stronger shoulder stability."
    ),
    "lateral raise": (
        "Use this exercise to strengthen side delts and improve shoulder control."
    ),
    "leg abduction": (
        "Use this exercise to strengthen glute medius for hip and knee stability."
    ),
    "leg adduction": (
        "Use this exercise to strengthen inner thighs for lower-body control."
    ),
    "leg curl": (
        "Use this exercise to isolate hamstrings and support safer sprint mechanics."
    ),
    "leg extension": (
        "Use this exercise to target quadriceps for stronger knee extension."
    ),
    "leg press": (
        "Use this exercise to build heavy lower-body strength in a stable setup."
    ),
    "leg raise": (
        "Use this exercise to strengthen lower abs and hip flexors for core control."
    ),
    "plank": (
        "Use this exercise to build core endurance and anti-extension stability."
    ),
    "pull-up": (
        "Use this exercise to improve vertical pulling strength and upper-back size."
    ),
    "push-up": (
        "Use this exercise to build practical chest, triceps, and core strength."
    ),
    "reverse fly": (
        "Use this exercise to strengthen rear delts and improve shoulder posture."
    ),
    "shoulder press": (
        "Use this exercise to build overhead shoulder and triceps pressing strength."
    ),
    "sit-up": (
        "Use this exercise to improve dynamic core strength and trunk flexion control."
    ),
    "squat": (
        "Use this exercise to build foundational leg strength and force production."
    ),
    "tricep extension": (
        "Use this exercise to strengthen triceps for better pressing lockout."
    ),
    "upright row": (
        "Use this exercise to develop upper traps and delts for shoulder strength."
    ),
}


_BOOTSTRAP_EXERCISE_DEFAULTS_BY_NAME: dict[str, _BootstrapExerciseDefaults] = {
    "barbell row": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup=(
                "Stand hip-width, hinge at the hips, and keep torso about 45° "
                "with a neutral spine."
            ),
            execution=(
                "Pull the bar to your lower ribs, squeeze your back, then lower "
                "it under control."
            ),
            breathing="Exhale as you pull, inhale as you lower.",
            form_cue="Keep elbows close and avoid jerking with your lower back.",
        ),
        weight=60.0,
        tags=("upper body", "pull", "compound", "back day", "barbell"),
        muscle_groups=("lats", "traps", "biceps"),
        muscle_groups_secondary=("forearms", "lower_back", "abs"),
    ),
    "bench press": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup=(
                "Lie on the bench with eyes under the bar, feet planted, and "
                "shoulder blades tucked back."
            ),
            execution=(
                "Lower the bar to mid-chest, then press straight up until arms "
                "are extended."
            ),
            breathing="Inhale on the way down, exhale while pressing up.",
            form_cue="Keep wrists straight and hips on the bench throughout.",
        ),
        weight=70.0,
        tags=("upper body", "push", "compound", "chest day", "barbell"),
        muscle_groups=("pecs", "triceps", "shoulders"),
        muscle_groups_secondary=("abs", "obliques"),
    ),
    "bicep curl": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Stand tall with dumbbells at your sides and elbows near your torso.",
            execution=(
                "Curl the weights up without swinging, then lower slowly to full "
                "arm extension."
            ),
            breathing="Exhale as you curl, inhale as you lower.",
            form_cue="Keep shoulders down and move only at the elbow.",
        ),
        weight=12.0,
        tags=("upper body", "pull", "isolation", "arm day", "dumbbell"),
        muscle_groups=("biceps", "forearms"),
        muscle_groups_secondary=("shoulders",),
    ),
    "calf-lift": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup=(
                "Stand on a step or plate with heels free and hold support for balance."
            ),
            execution=(
                "Rise onto your toes as high as possible, pause, then lower heels "
                "below step level."
            ),
            breathing="Exhale on the lift, inhale on the way down.",
            form_cue="Use full range and avoid bouncing.",
        ),
        weight=80.0,
        tags=("lower body", "isolation", "leg day", "calves", "strength"),
        muscle_groups=("calves",),
        muscle_groups_secondary=("quads", "hamstrings"),
    ),
    "clean hands": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup=(
                "Start with bar over mid-foot, chest up, and hands just outside "
                "your legs."
            ),
            execution=(
                "Drive through the legs, extend hips fast, and pull the bar up "
                "close to the body."
            ),
            breathing=(
                "Take a big breath before the pull, exhale after the rep is secured."
            ),
            form_cue="Keep the bar close and do not curl it with your arms.",
        ),
        weight=50.0,
        tags=("full body", "power", "compound", "barbell", "athletic"),
        muscle_groups=("quads", "glutes", "hamstrings", "traps", "shoulders"),
        muscle_groups_secondary=("abs", "obliques", "lower_back", "calves"),
    ),
    "crunch": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Lie on your back, knees bent, and feet flat on the floor.",
            execution=(
                "Lift shoulders slightly off the floor by tightening your abs, "
                "then return slowly."
            ),
            breathing="Exhale as you curl up, inhale as you lower.",
            form_cue="Keep neck relaxed and avoid pulling on your head.",
        ),
        weight=20.0,
        tags=("core", "isolation", "abs", "bodyweight", "conditioning"),
        muscle_groups=("abs",),
        muscle_groups_secondary=("obliques", "hip_flexors"),
    ),
    "deadlift": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup=(
                "Place bar over mid-foot, grip just outside knees, and flatten "
                "your back before lifting."
            ),
            execution=(
                "Push the floor away, stand tall with bar close to legs, then "
                "lower with a hip hinge."
            ),
            breathing="Brace with a deep breath before lifting, exhale near the top.",
            form_cue="Keep spine neutral and avoid rounding your lower back.",
        ),
        weight=90.0,
        tags=("full body", "compound", "posterior chain", "strength", "barbell"),
        muscle_groups=("glutes", "hamstrings", "lower_back", "traps"),
        muscle_groups_secondary=("quads", "lats", "forearms", "abs"),
    ),
    "dumbbell curl": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Stand upright with dumbbells and palms facing forward.",
            execution=(
                "Curl both dumbbells up to shoulder level, then lower under control."
            ),
            breathing="Exhale on the curl, inhale on the way down.",
            form_cue="Keep elbows fixed and avoid swinging your torso.",
        ),
        weight=12.0,
        tags=("upper body", "pull", "isolation", "arm day", "dumbbell"),
        muscle_groups=("biceps", "forearms"),
        muscle_groups_secondary=("shoulders",),
    ),
    "dumbbell fly": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Lie on a bench with dumbbells above chest and elbows slightly bent.",
            execution=(
                "Open arms in a wide arc until chest stretch, then bring "
                "dumbbells back together."
            ),
            breathing="Inhale as arms open, exhale as you bring them up.",
            form_cue="Keep a soft elbow bend and move slowly.",
        ),
        weight=14.0,
        tags=("upper body", "push", "isolation", "chest day", "dumbbell"),
        muscle_groups=("pecs", "shoulders"),
        muscle_groups_secondary=("triceps",),
    ),
    "dumbbell press": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Lie on bench with dumbbells at chest level and feet firmly planted.",
            execution=(
                "Press dumbbells up until arms are straight, then lower to chest level."
            ),
            breathing="Inhale while lowering, exhale while pressing.",
            form_cue="Keep wrists stacked over elbows and shoulder blades tight.",
        ),
        weight=24.0,
        tags=("upper body", "push", "compound", "chest day", "dumbbell"),
        muscle_groups=("pecs", "shoulders", "triceps"),
        muscle_groups_secondary=("abs",),
    ),
    "dumbbell row": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Place one knee and hand on a bench, other foot on floor, back flat.",
            execution="Pull dumbbell toward your hip, pause, then lower fully.",
            breathing="Exhale as you pull, inhale as you lower.",
            form_cue="Do not twist your torso; keep chest square to the floor.",
        ),
        weight=26.0,
        tags=("upper body", "pull", "compound", "back day", "dumbbell"),
        muscle_groups=("lats", "biceps", "forearms"),
        muscle_groups_secondary=("traps", "lower_back"),
    ),
    "front raise": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Stand tall with dumbbells in front of thighs and soft elbows.",
            execution=(
                "Raise weights to shoulder height in front of you, then lower slowly."
            ),
            breathing="Exhale up, inhale down.",
            form_cue="Lift with shoulders, not with momentum from your back.",
        ),
        weight=8.0,
        tags=("upper body", "push", "isolation", "shoulder day", "dumbbell"),
        muscle_groups=("shoulders",),
        muscle_groups_secondary=("traps", "abs"),
    ),
    "lateral raise": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Stand with dumbbells at sides and slight bend in elbows.",
            execution=(
                "Raise arms out to the side up to shoulder height, then lower "
                "with control."
            ),
            breathing="Exhale while lifting, inhale while lowering.",
            form_cue="Keep shoulders down and avoid shrugging.",
        ),
        weight=8.0,
        tags=("upper body", "push", "isolation", "shoulder day", "dumbbell"),
        muscle_groups=("shoulders",),
        muscle_groups_secondary=("traps",),
    ),
    "leg abduction": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Sit or stand in the machine with core braced and neutral posture.",
            execution=(
                "Push legs outward in a controlled arc, pause, then return slowly."
            ),
            breathing="Exhale as legs move out, inhale on return.",
            form_cue="Move from the hips and do not rock your torso.",
        ),
        weight=35.0,
        tags=("lower body", "isolation", "leg day", "glutes", "stability"),
        muscle_groups=("glutes", "hip_flexors"),
        muscle_groups_secondary=("obliques",),
    ),
    "leg adduction": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Set the adduction machine so your legs start comfortably wide.",
            execution="Squeeze legs inward until pads meet, then return slowly.",
            breathing="Exhale as you squeeze in, inhale as you return.",
            form_cue="Keep hips stable and avoid bouncing at the end range.",
        ),
        weight=40.0,
        tags=("lower body", "isolation", "leg day", "stability", "machine"),
        muscle_groups=("quads",),
        muscle_groups_secondary=("glutes", "hamstrings"),
    ),
    "leg curl": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Adjust the machine so the pad rests just above your heels.",
            execution=(
                "Curl heels toward glutes, squeeze hamstrings, then lower slowly."
            ),
            breathing="Exhale while curling, inhale while lowering.",
            form_cue="Keep hips pressed into the bench and avoid arching.",
        ),
        weight=40.0,
        tags=("lower body", "isolation", "leg day", "posterior chain", "machine"),
        muscle_groups=("hamstrings",),
        muscle_groups_secondary=("glutes", "calves"),
    ),
    "leg extension": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup=(
                "Sit upright with knees aligned to machine pivot and pad on "
                "lower shins."
            ),
            execution="Extend knees until legs are nearly straight, then lower slowly.",
            breathing="Exhale on extension, inhale on return.",
            form_cue="Do not lock knees hard at the top.",
        ),
        weight=45.0,
        tags=("lower body", "isolation", "leg day", "quads", "machine"),
        muscle_groups=("quads",),
        muscle_groups_secondary=("hip_flexors",),
    ),
    "leg press": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup=(
                "Place feet shoulder-width on platform and keep lower back against pad."
            ),
            execution="Lower sled until knees are around 90°, then press back up.",
            breathing="Inhale on the way down, exhale as you press.",
            form_cue="Keep knees tracking over toes and avoid locking out hard.",
        ),
        weight=140.0,
        tags=("lower body", "compound", "leg day", "strength", "machine"),
        muscle_groups=("quads", "glutes", "hamstrings"),
        muscle_groups_secondary=("calves", "lower_back"),
    ),
    "leg raise": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Lie on your back or hang from a bar with core braced.",
            execution="Raise legs to about hip level or higher, then lower slowly.",
            breathing="Exhale while lifting, inhale while lowering.",
            form_cue="Keep lower back controlled and avoid swinging.",
        ),
        weight=15.0,
        tags=("core", "isolation", "abs", "bodyweight", "control"),
        muscle_groups=("abs", "hip_flexors"),
        muscle_groups_secondary=("obliques",),
    ),
    "plank": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Place forearms under shoulders and extend legs behind you.",
            execution="Hold a straight line from head to heels for the target time.",
            breathing="Take slow, controlled breaths while staying braced.",
            form_cue="Do not let hips sag or lift too high.",
        ),
        weight=80.0,
        tags=("core", "isometric", "bodyweight", "stability", "conditioning"),
        muscle_groups=("abs", "obliques", "lower_back"),
        muscle_groups_secondary=("shoulders", "glutes"),
    ),
    "pull-up": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Hang from the bar with hands slightly wider than shoulders.",
            execution="Pull chest up toward bar, then lower to a full controlled hang.",
            breathing="Exhale as you pull up, inhale as you lower.",
            form_cue="Keep core tight and avoid kipping unless intentional.",
        ),
        weight=80.0,
        tags=("upper body", "pull", "compound", "back day", "bodyweight"),
        muscle_groups=("lats", "biceps", "forearms"),
        muscle_groups_secondary=("shoulders", "traps", "abs"),
    ),
    "push-up": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Hands just outside shoulder width, body in a straight plank.",
            execution="Lower chest toward floor, then press back to start.",
            breathing="Inhale down, exhale up.",
            form_cue="Keep elbows around 45° and avoid dropping your hips.",
        ),
        weight=60.0,
        tags=("upper body", "push", "compound", "bodyweight", "conditioning"),
        muscle_groups=("pecs", "triceps", "shoulders"),
        muscle_groups_secondary=("abs", "obliques"),
    ),
    "reverse fly": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Hinge at hips with neutral spine and dumbbells under your chest.",
            execution=(
                "Open arms out and back, squeeze shoulder blades, then lower slowly."
            ),
            breathing="Exhale while lifting, inhale while lowering.",
            form_cue="Keep neck neutral and use light weights with control.",
        ),
        weight=8.0,
        tags=("upper body", "pull", "isolation", "shoulder day", "dumbbell"),
        muscle_groups=("shoulders", "traps"),
        muscle_groups_secondary=("lats",),
    ),
    "shoulder press": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Start seated or standing with weights at shoulder height.",
            execution=(
                "Press overhead until arms are straight, then lower to shoulders."
            ),
            breathing="Exhale on the press, inhale on the way down.",
            form_cue="Keep ribs down and avoid over-arching your lower back.",
        ),
        weight=40.0,
        tags=("upper body", "push", "compound", "shoulder day", "barbell"),
        muscle_groups=("shoulders", "triceps"),
        muscle_groups_secondary=("traps", "abs"),
    ),
    "sit-up": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Lie on your back with knees bent and feet anchored if needed.",
            execution="Curl up until torso is upright, then lower under control.",
            breathing="Exhale while sitting up, inhale while lowering.",
            form_cue="Move smoothly and do not yank with your neck.",
        ),
        weight=25.0,
        tags=("core", "bodyweight", "abs", "conditioning", "control"),
        muscle_groups=("abs", "hip_flexors"),
        muscle_groups_secondary=("obliques",),
    ),
    "squat": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup="Stand shoulder-width with chest up and core braced.",
            execution=(
                "Sit hips down and back until thighs are near parallel, then stand up."
            ),
            breathing="Inhale on descent, exhale as you drive up.",
            form_cue="Keep knees tracking over toes and heels on the floor.",
        ),
        weight=80.0,
        tags=("lower body", "compound", "leg day", "strength", "barbell"),
        muscle_groups=("quads", "glutes", "hamstrings"),
        muscle_groups_secondary=("calves", "lower_back", "abs"),
    ),
    "tricep extension": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup=(
                "Hold a dumbbell or cable with elbows pointed forward and upper "
                "arms fixed."
            ),
            execution="Extend elbows fully, then lower weight back with control.",
            breathing="Exhale on extension, inhale on return.",
            form_cue="Keep elbows close and avoid flaring them out.",
        ),
        weight=22.0,
        tags=("upper body", "push", "isolation", "arm day", "dumbbell"),
        muscle_groups=("triceps",),
        muscle_groups_secondary=("shoulders", "forearms"),
    ),
    "upright row": _BootstrapExerciseDefaults(
        description=_exercise_howto(
            setup=(
                "Stand tall with bar close to thighs and hands slightly narrower "
                "than shoulders."
            ),
            execution="Pull bar up along your body to mid-chest, then lower slowly.",
            breathing="Exhale as you pull, inhale as you lower.",
            form_cue="Keep wrists neutral and stop if shoulder pinch appears.",
        ),
        weight=30.0,
        tags=("upper body", "pull", "compound", "shoulder day", "barbell"),
        muscle_groups=("shoulders", "traps"),
        muscle_groups_secondary=("biceps", "forearms"),
    ),
}


_BOOTSTRAP_EXERCISE_WEIGHT_SCALE = 50.0 / 70.0


def _bootstrap_exercises_with_defaults(exercise_names: list[str]) -> list[Exercise]:
    missing_defaults = sorted(
        set(exercise_names) - set(_BOOTSTRAP_EXERCISE_DEFAULTS_BY_NAME.keys())
    )
    if missing_defaults:
        raise ValueError(
            "Missing bootstrap exercise defaults for: " + ", ".join(missing_defaults)
        )

    missing_purposes = sorted(
        set(exercise_names) - set(_BOOTSTRAP_EXERCISE_PURPOSE_BY_NAME.keys())
    )
    if missing_purposes:
        raise ValueError(
            "Missing bootstrap exercise purposes for: " + ", ".join(missing_purposes)
        )

    exercises = []
    for exercise_name in exercise_names:
        defaults = _BOOTSTRAP_EXERCISE_DEFAULTS_BY_NAME[exercise_name]
        exercises.append(
            Exercise(
                name=exercise_name,
                description=(
                    f"{_BOOTSTRAP_EXERCISE_PURPOSE_BY_NAME[exercise_name]}\n\n"
                    f"{defaults.description}"
                ),
                weight=round(defaults.weight * _BOOTSTRAP_EXERCISE_WEIGHT_SCALE, 1),
                tags=list(defaults.tags),
                muscle_groups=mg.validate_muscle_keys(list(defaults.muscle_groups)),
                muscle_groups_secondary=mg.validate_muscle_keys(
                    list(defaults.muscle_groups_secondary)
                ),
                key=generate_bootstrap_uuid(exercise_name),
            )
        )

    return exercises


class UserExercises:
    """Custom exercise types defined by the user."""

    # default exercises for new users
    BOOTSTRAP = [
        "barbell row",
        "bench press",
        "bicep curl",  # bicepsy s jednoručkami
        "calf-lift",  # vypony lytek
        "clean hands",
        "crunch",
        "deadlift",
        "dumbbell curl",
        "dumbbell fly",
        "dumbbell press",
        "dumbbell row",
        "front raise",
        "lateral raise",
        "leg abduction",
        "leg adduction",
        "leg curl",
        "leg extension",
        "leg press",
        "leg raise",
        "plank",
        "pull-up",
        "push-up",
        "reverse fly",
        "shoulder press",
        "sit-up",  # leh sed
        "squat",  # drep
        "tricep extension",
        "upright row",
    ]

    @staticmethod
    def bootstrap() -> list[Exercise]:
        return _bootstrap_exercises_with_defaults(UserExercises.BOOTSTRAP)

    @staticmethod
    def from_dict_dict(exercise_data: dict | list) -> "UserExercises":
        """Load from dict (old) or list (new) format."""
        exercise_dict = persistences.normalize_dict_or_list_to_dict(exercise_data)
        exercises = []
        if not exercise_dict:
            exercises = UserExercises.bootstrap()
        else:
            for mytral_key in exercise_dict:
                exercises.append(Exercise.from_dict(exercise_dict[mytral_key]))

        exercises.sort(key=lambda x: x.name)
        return UserExercises(exercises=exercises)

    @property
    def exercise_by_name(self) -> dict[str, Exercise]:
        """Avoid having authoritative data twice."""
        if self.exercise_by_key:
            # map: name -> exercise
            return {g.name: g for g in self.exercise_by_key.values()}
        return {}

    def __init__(self, exercises: list[Exercise]) -> None:
        # map: key -> exercise
        self.exercise_by_key: dict[str, Exercise] = {}
        for g in exercises:
            if not g.key:
                g.key = str(uuid.uuid4())
            self.exercise_by_key[g.key] = g

    def empty(self) -> bool:
        return len(self.exercise_by_key) == 0

    def is_bootstrap_only(self) -> bool:
        """Check if collection contains only unmodified bootstrap data.

        Returns
        -------
        bool
            True if only bootstrap exercises are present

        """
        return is_bootstrap_data_only(self.exercise_by_key, UserExercises.BOOTSTRAP)

    def default_exercise(self) -> Exercise | None:
        if self.empty():
            return None
        return list(self.exercise_by_key.values())[0]

    def exists(self, key: str) -> bool:
        return key in self.exercise_by_key

    def update(self, exercise: Exercise):
        if not exercise.key:
            raise ValueError("Exercise key must be set.")
        if exercise.key not in self.exercise_by_key:
            raise ValueError(
                f"Exercise cannot be updated - key '{exercise.key}' not found."
            )

        self.exercise_by_key[exercise.key] = exercise

    def delete(self, key: str):
        del self.exercise_by_key[key]

    def add_exercise(self, exercise: Exercise):
        if not exercise.key:
            exercise.key = str(uuid.uuid4())

        self.exercise_by_key[exercise.key] = exercise

    def names(self) -> list[str]:
        exercise_names = [""] + list(self.exercise_by_name.keys())
        return exercise_names

    def reset_counts(self):
        for e in self.exercise_by_key.values():
            e.count = 0

    def to_list(self) -> list:
        return [g.to_dict() for g in self.exercise_by_key.values()]

    def to_dict(self) -> dict[str, Exercise]:
        return self.to_dict_by_key()

    def to_dict_dict(self) -> list:
        """Save as list format (new efficient format)."""
        return [g.to_dict() for g in self.exercise_by_key.values()]

    def to_dict_by_name(self) -> dict[str, Exercise]:
        return self.exercise_by_name

    def to_dict_by_key(self) -> dict[str, Exercise]:
        return self.exercise_by_key


#
# Laps
#


class Lap:
    """Lap type - represents a reusable lap/interval template."""

    KEY_NAME = "name"
    KEY_DESCRIPTION = "description"
    KEY_DEFAULT_DISTANCE = "default_distance"
    KEY_DEFAULT_DURATION = "default_duration"
    KEY_COUNT = "count"
    KEY_KEY = "key"

    def __init__(
        self,
        name: str,
        description: str = "",
        default_distance: int = 0,  # meters
        default_duration: int = 0,  # seconds
        key: str = "",
    ) -> None:
        self.name = name
        self.description = description
        self.default_distance = default_distance
        self.default_duration = default_duration

        self.key = key or str(uuid.uuid4())

    def to_dict(self) -> dict:
        return {
            Lap.KEY_NAME: self.name,
            Lap.KEY_DESCRIPTION: self.description,
            Lap.KEY_DEFAULT_DISTANCE: self.default_distance,
            Lap.KEY_DEFAULT_DURATION: self.default_duration,
            Lap.KEY_KEY: self.key,
        }

    @staticmethod
    def from_dict(lap_dict: dict) -> "Lap":
        return Lap(
            name=lap_dict[Lap.KEY_NAME],
            description=lap_dict.get(Lap.KEY_DESCRIPTION, ""),
            default_distance=lap_dict.get(Lap.KEY_DEFAULT_DISTANCE, 0),
            default_duration=lap_dict.get(Lap.KEY_DEFAULT_DURATION, 0),
            key=lap_dict.get(Lap.KEY_KEY, ""),
        )


class UserLaps:
    """Custom lap types defined by the user."""

    # default laps for new users
    BOOTSTRAP = [
        {"name": "400m", "default_distance": 400},
        {"name": "800m", "default_distance": 800},
        {"name": "1000m", "default_distance": 1000},
        {"name": "1500m", "default_distance": 1500},
        {"name": "1 mile", "default_distance": 1609},
        {"name": "2k", "default_distance": 2000},
        {"name": "5k", "default_distance": 5000},
        {"name": "10k", "default_distance": 10000},
        {"name": "30s", "default_duration": 30},
        {"name": "1'", "default_duration": 60},
        {"name": "2'", "default_duration": 120},
        {"name": "3'", "default_duration": 180},
        {"name": "5'", "default_duration": 300},
        {"name": "10'", "default_duration": 600},
    ]

    @staticmethod
    def bootstrap() -> list[Lap]:
        laps = []
        for lap_data in UserLaps.BOOTSTRAP:
            laps.append(
                Lap(
                    name=lap_data["name"],
                    default_distance=lap_data.get("default_distance", 0),
                    default_duration=lap_data.get("default_duration", 0),
                    key=generate_bootstrap_uuid(lap_data["name"]),
                )
            )
        return laps

    @staticmethod
    def from_dict_dict(lap_data: dict | list) -> "UserLaps":
        """Load from dict (old) or list (new) format."""
        lap_dict = persistences.normalize_dict_or_list_to_dict(lap_data)
        laps = []
        if not lap_dict:
            laps = UserLaps.bootstrap()
        else:
            for mytral_key in lap_dict:
                laps.append(Lap.from_dict(lap_dict[mytral_key]))

        laps.sort(key=lambda x: x.name)
        return UserLaps(laps=laps)

    @property
    def lap_by_name(self) -> dict[str, Lap]:
        """Avoid having authoritative data twice."""
        if self.lap_by_key:
            return {lap.name: lap for lap in self.lap_by_key.values()}
        return {}

    def __init__(self, laps: list[Lap]) -> None:
        self.lap_by_key: dict[str, Lap] = {}
        for lap in laps:
            if not lap.key:
                lap.key = str(uuid.uuid4())
            self.lap_by_key[lap.key] = lap

    def empty(self) -> bool:
        return len(self.lap_by_key) == 0

    def default_lap(self) -> Lap | None:
        if self.empty():
            return None
        return list(self.lap_by_key.values())[0]

    def exists(self, key: str) -> bool:
        return key in self.lap_by_key

    def update(self, lap: Lap):
        if not lap.key:
            raise ValueError("Lap key must be set.")
        if lap.key not in self.lap_by_key:
            raise ValueError(f"Lap cannot be updated - key '{lap.key}' not found.")
        self.lap_by_key[lap.key] = lap

    def delete(self, key: str):
        del self.lap_by_key[key]

    def add_lap(self, lap: Lap):
        if not lap.key:
            lap.key = str(uuid.uuid4())
        self.lap_by_key[lap.key] = lap

    def names(self) -> list[str]:
        lap_names = [""] + list(self.lap_by_name.keys())
        return lap_names

    def reset_counts(self):
        for lap in self.lap_by_key.values():
            lap.count = 0

    def to_list(self) -> list:
        return [lap.to_dict() for lap in self.lap_by_key.values()]

    def to_dict(self) -> dict[str, Lap]:
        return self.to_dict_by_key()

    def to_dict_dict(self) -> list:
        """Save as list format (new efficient format)."""
        return [lap.to_dict() for lap in self.lap_by_key.values()]

    def to_dict_by_name(self) -> dict[str, Lap]:
        return self.lap_by_name

    def to_dict_by_key(self) -> dict[str, Lap]:
        return self.lap_by_key


#
# User outfit
#


@dataclasses.dataclass
class Outfit:
    """Represents a single outfit configuration."""

    KEY_NAME = "name"
    KEY_ACTIVITY_TYPE = "activity_type"
    KEY_DESCRIPTION = "description"
    KEY_COUNT = "count"
    KEY_KEY = "key"

    def __init__(
        self,
        name: str,
        activity_type: str,
        description: str = "",
        count: int = 0,
        key: str = "",
    ) -> None:
        self.name = name
        self.activity_type = activity_type
        self.description = description
        self.count = count
        self.key = key or str(uuid.uuid4())

    @classmethod
    def from_dict(cls, outfit_dict: dict) -> Self:
        """Create Outfit instance from dictionary."""
        return cls(
            name=outfit_dict[cls.KEY_NAME],
            activity_type=outfit_dict[cls.KEY_ACTIVITY_TYPE],
            description=outfit_dict.get(cls.KEY_DESCRIPTION, ""),
            count=outfit_dict.get(cls.KEY_COUNT, 0),
            key=outfit_dict.get(cls.KEY_KEY, ""),
        )

    def to_dict(self) -> dict:
        """Convert outfit to dictionary."""
        return {
            self.KEY_NAME: self.name,
            self.KEY_ACTIVITY_TYPE: self.activity_type,
            self.KEY_DESCRIPTION: self.description,
            self.KEY_COUNT: self.count,
            self.KEY_KEY: self.key,
        }


class UserOutfits:
    """Container for user's outfits."""

    @property
    def outfits(self) -> list[Outfit]:
        """Avoid having authoritative data twice."""
        if self.outfits_by_key:
            # map: name -> outfit
            return list(self.outfits_by_key.values())
        return []

    def __init__(self) -> None:
        self.outfits_by_key: dict[str, Outfit] = {}

    def add(self, outfit: Outfit) -> None:
        """Add outfit to collection."""
        self.outfits_by_key[outfit.key] = outfit

    def update(self, outfit: Outfit):
        if not outfit.key:
            raise ValueError("Outfit key must be set.")
        if outfit.key not in self.outfits_by_key:
            raise ValueError(
                f"Outfit cannot be updated - key '{outfit.key}' not found."
            )

        self.outfits_by_key[outfit.key] = outfit

    def delete(self, key: str) -> None:
        """Remove outfit by key."""
        if key in self.outfits_by_key:
            del self.outfits_by_key[key]

    def get_by_key(self, key: str) -> Outfit | None:
        """Get outfit by key."""
        return self.outfits_by_key.get(key)

    def get_by_name(self, name: str) -> Outfit | None:
        """Get outfit by name."""
        return next((o for o in self.outfits if o.name == name), None)

    def get_by_activity_type(self, activity_type: str) -> list[Outfit]:
        """Get all outfits for specific activity type."""
        return [o for o in self.outfits if o.activity_type == activity_type]

    def get_all(self) -> list[Outfit]:
        """Get all outfits."""
        return self.outfits

    def to_dict(self) -> list:
        """Convert all outfits to list (new efficient format)."""
        return [o.to_dict() for o in self.outfits]

    @classmethod
    def from_dict(cls, outfits_data: dict | list) -> Self:
        """Create UserOutfits instance from dictionary or list."""
        outfits_dict = persistences.normalize_dict_or_list_to_dict(outfits_data)
        outfits = cls()
        for outfit_dict in outfits_dict.values():
            outfit = Outfit.from_dict(outfit_dict)
            outfits.add(outfit)
        return outfits


#
# User goal
#


@dataclasses.dataclass
class Goal:
    """Represents a single goal configuration."""

    KEY_NAME = "name"
    KEY_ACTIVITY_TYPE = "activity_type"
    KEY_DESCRIPTION = "description"
    KEY_TAG = "tag"
    KEY_DONE = "done"
    KEY_URGENCY = "urgency"
    KEY_IMPORTANCE = "importance"
    KEY_KEY = "key"
    KEY_PHOTO_BLOB_KEYS = "photo_blob_keys"
    KEY_HIGHLIGHT_PHOTO_BLOB_KEY = "highlight_photo_blob_key"

    def __init__(
        self,
        name: str,
        activity_type: str,
        description: str = "",
        tag: str = "",
        done: bool = False,
        urgency: float = 0.5,
        importance: float = 0.5,
        key: str = "",
        photo_blob_keys: list | None = None,
        highlight_photo_blob_key: str = "",
    ) -> None:
        self.name = name
        self.activity_type = activity_type
        self.description = description
        self.tag = tag
        self.done = done
        self.urgency = max(0.0, min(1.0, urgency))
        self.importance = max(0.0, min(1.0, importance))
        self.key = key or str(uuid.uuid4())
        self.photo_blob_keys = photo_blob_keys or []
        self.highlight_photo_blob_key = highlight_photo_blob_key

    @classmethod
    def from_dict(cls, goal_dict: dict) -> Self:
        """Create goal instance from dictionary."""
        return cls(
            name=goal_dict[cls.KEY_NAME],
            activity_type=goal_dict[cls.KEY_ACTIVITY_TYPE],
            description=goal_dict.get(cls.KEY_DESCRIPTION, ""),
            tag=goal_dict.get(cls.KEY_TAG, ""),
            done=goal_dict.get(cls.KEY_DONE, False),
            urgency=goal_dict.get(cls.KEY_URGENCY, 0.5),
            importance=goal_dict.get(cls.KEY_IMPORTANCE, 0.5),
            key=goal_dict.get(cls.KEY_KEY, ""),
            photo_blob_keys=goal_dict.get(cls.KEY_PHOTO_BLOB_KEYS, []),
            highlight_photo_blob_key=goal_dict.get(
                cls.KEY_HIGHLIGHT_PHOTO_BLOB_KEY, ""
            ),
        )

    def to_dict(self) -> dict:
        """Convert goal to dictionary."""
        return {
            self.KEY_NAME: self.name,
            self.KEY_ACTIVITY_TYPE: self.activity_type,
            self.KEY_DESCRIPTION: self.description,
            self.KEY_TAG: self.tag,
            self.KEY_DONE: self.done,
            self.KEY_URGENCY: self.urgency,
            self.KEY_IMPORTANCE: self.importance,
            self.KEY_KEY: self.key,
            self.KEY_PHOTO_BLOB_KEYS: self.photo_blob_keys,
            self.KEY_HIGHLIGHT_PHOTO_BLOB_KEY: self.highlight_photo_blob_key,
        }


class UserGoals:
    """Container for user's goals."""

    @property
    def goals(self) -> list[Goal]:
        """Avoid having authoritative data twice."""
        if self.goals_by_key:
            # map: name -> goal
            return list(self.goals_by_key.values())
        return []

    def __init__(self) -> None:
        self.goals_by_key: dict[str, Goal] = {}

    def add(self, goal: Goal) -> None:
        """Add goal to collection."""
        self.goals_by_key[goal.key] = goal

    def update(self, goal: Goal):
        if not goal.key:
            raise ValueError("Goal key must be set.")
        if goal.key not in self.goals_by_key:
            raise ValueError(f"Goal cannot be updated - key '{goal.key}' not found.")

        self.goals_by_key[goal.key] = goal

    def delete(self, key: str) -> None:
        """Remove goal by key."""
        if key in self.goals_by_key:
            del self.goals_by_key[key]

    def get_by_key(self, key: str) -> Goal | None:
        """Get goal by key."""
        return self.goals_by_key.get(key)

    def get_by_name(self, name: str) -> Goal | None:
        """Get goal by name."""
        return next((o for o in self.goals if o.name == name), None)

    def get_by_activity_type(self, activity_type: str) -> list[Goal]:
        """Get all goals for specific activity type."""
        return [o for o in self.goals if o.activity_type == activity_type]

    def get_all(self) -> list[Goal]:
        """Get all goals."""
        return self.goals

    def to_dict(self) -> list:
        """Convert all goals to list (new efficient format)."""
        return [o.to_dict() for o in self.goals]

    @classmethod
    def from_dict(cls, goals_data: dict | list) -> Self:
        """Create UserGoals instance from dictionary or list."""
        goals_dict = persistences.normalize_dict_or_list_to_dict(goals_data)
        goals = cls()
        for goal_dict in goals_dict.values():
            goal = Goal.from_dict(goal_dict)
            goals.add(goal)
        return goals


#
# Athlete metrics
#


@dataclasses.dataclass
class AthleteMetrics:
    """Athlete performance metrics — set by the athlete or estimated by MyTraL.

    Convention: metric = 0 means "not set". e_metric is always populated
    with either the athlete-set value or a MyTraL estimate.

    All e_* fields are transient and never persisted — they are recomputed
    on every load by athlete_metrics.resolve().
    """

    #
    # Persisted fields (set by athlete — 0 means not set)
    #

    # maximum heart rate (BPM) — 0 = not set
    max_hr: int = 0
    # anaerobic threshold HR / LTHR (BPM) — 0 = not set
    anaerobic_threshold_hr: int = 0
    # aerobic threshold HR / LT1 (BPM) — 0 = not set
    aerobic_threshold_hr: int = 0
    # functional threshold power (Watts) — 0 = not set
    ftp: float = 0.0
    # VO2 Max (mL/kg/min) — 0 = not set
    vo2max: float = 0.0
    # HRV overnight RMSSD (ms) — 0 = not set
    hrv_rmssd: float = 0.0
    # FatMax (g/hr) — 0 = not set
    fat_max: float = 0.0
    # zone upper boundaries set by athlete (0 = not set; all seven must be > 0
    # to use athlete values — otherwise all zones estimated from FTP)
    z1_high: int = 0
    z2_high: int = 0
    z3_high: int = 0
    z4_high: int = 0
    # power zone upper boundaries set by athlete (0 = not set; all seven must be > 0
    # to use athlete values — otherwise all zones estimated from FTP)
    pz1_high: int = 0
    pz2_high: int = 0
    pz3_high: int = 0
    pz4_high: int = 0
    pz5_high: int = 0
    pz6_high: int = 0
    pz7_high: int = 0

    #
    # Transient effective values (populated by athlete_metrics.resolve())
    #

    e_max_hr: int = dataclasses.field(default=0, repr=False)
    e_anaerobic_threshold_hr: int = dataclasses.field(default=0, repr=False)
    e_aerobic_threshold_hr: int = dataclasses.field(default=0, repr=False)
    e_ftp: float = dataclasses.field(default=0.0, repr=False)
    e_vo2max: float = dataclasses.field(default=0.0, repr=False)
    e_hrv_rmssd: float = dataclasses.field(default=0.0, repr=False)
    e_fat_max: float = dataclasses.field(default=0.0, repr=False)
    # always derived from e_ftp and weight — never stored
    e_power_to_weight: float = dataclasses.field(default=0.0, repr=False)

    #
    # Transient HR zone boundaries (populated by athlete_metrics.resolve())
    #

    e_z1_low: int = dataclasses.field(default=0, repr=False)
    e_z1_high: int = dataclasses.field(default=0, repr=False)
    e_z2_low: int = dataclasses.field(default=0, repr=False)
    e_z2_high: int = dataclasses.field(default=0, repr=False)
    e_z3_low: int = dataclasses.field(default=0, repr=False)
    e_z3_high: int = dataclasses.field(default=0, repr=False)
    e_z4_low: int = dataclasses.field(default=0, repr=False)
    e_z4_high: int = dataclasses.field(default=0, repr=False)
    e_z5_low: int = dataclasses.field(default=0, repr=False)
    e_z5_high: int = dataclasses.field(default=0, repr=False)

    #
    # Transient power zone boundaries (populated by athlete_metrics.resolve())
    #

    e_pz1_low: int = dataclasses.field(default=0, repr=False)
    e_pz1_high: int = dataclasses.field(default=0, repr=False)
    e_pz2_low: int = dataclasses.field(default=0, repr=False)
    e_pz2_high: int = dataclasses.field(default=0, repr=False)
    e_pz3_low: int = dataclasses.field(default=0, repr=False)
    e_pz3_high: int = dataclasses.field(default=0, repr=False)
    e_pz4_low: int = dataclasses.field(default=0, repr=False)
    e_pz4_high: int = dataclasses.field(default=0, repr=False)
    e_pz5_low: int = dataclasses.field(default=0, repr=False)
    e_pz5_high: int = dataclasses.field(default=0, repr=False)
    e_pz6_low: int = dataclasses.field(default=0, repr=False)
    e_pz6_high: int = dataclasses.field(default=0, repr=False)
    e_pz7_low: int = dataclasses.field(default=0, repr=False)
    e_pz7_high: int = dataclasses.field(default=0, repr=False)

    # JSON keys for persisted fields only
    KEY_MAX_HR = "max_hr"
    KEY_ANAEROBIC_THRESHOLD_HR = "anaerobic_threshold_hr"
    KEY_AEROBIC_THRESHOLD_HR = "aerobic_threshold_hr"
    KEY_FTP = "ftp"
    KEY_VO2MAX = "vo2max"
    KEY_HRV_RMSSD = "hrv_rmssd"
    KEY_FAT_MAX = "fat_max"
    KEY_Z1_HIGH = "z1_high"
    KEY_Z2_HIGH = "z2_high"
    KEY_Z3_HIGH = "z3_high"
    KEY_Z4_HIGH = "z4_high"
    KEY_PZ1_HIGH = "pz1_high"
    KEY_PZ2_HIGH = "pz2_high"
    KEY_PZ3_HIGH = "pz3_high"
    KEY_PZ4_HIGH = "pz4_high"
    KEY_PZ5_HIGH = "pz5_high"
    KEY_PZ6_HIGH = "pz6_high"
    KEY_PZ7_HIGH = "pz7_high"

    def to_dict_persisted(self) -> dict:
        """Serialize only athlete-set (persisted) fields to dict.

        Returns
        -------
        dict
            Dictionary with only the persisted (non-transient) fields.

        """
        return {
            AthleteMetrics.KEY_MAX_HR: self.max_hr,
            AthleteMetrics.KEY_ANAEROBIC_THRESHOLD_HR: self.anaerobic_threshold_hr,
            AthleteMetrics.KEY_AEROBIC_THRESHOLD_HR: self.aerobic_threshold_hr,
            AthleteMetrics.KEY_FTP: self.ftp,
            AthleteMetrics.KEY_VO2MAX: self.vo2max,
            AthleteMetrics.KEY_HRV_RMSSD: self.hrv_rmssd,
            AthleteMetrics.KEY_FAT_MAX: self.fat_max,
            AthleteMetrics.KEY_Z1_HIGH: self.z1_high,
            AthleteMetrics.KEY_Z2_HIGH: self.z2_high,
            AthleteMetrics.KEY_Z3_HIGH: self.z3_high,
            AthleteMetrics.KEY_Z4_HIGH: self.z4_high,
            AthleteMetrics.KEY_PZ1_HIGH: self.pz1_high,
            AthleteMetrics.KEY_PZ2_HIGH: self.pz2_high,
            AthleteMetrics.KEY_PZ3_HIGH: self.pz3_high,
            AthleteMetrics.KEY_PZ4_HIGH: self.pz4_high,
            AthleteMetrics.KEY_PZ5_HIGH: self.pz5_high,
            AthleteMetrics.KEY_PZ6_HIGH: self.pz6_high,
            AthleteMetrics.KEY_PZ7_HIGH: self.pz7_high,
        }

    @staticmethod
    def from_dict(data: dict) -> "AthleteMetrics":
        """Deserialize persisted fields from dict.

        Parameters
        ----------
        data : dict
            Dictionary containing persisted athlete metrics fields.

        Returns
        -------
        AthleteMetrics
            New AthleteMetrics instance with persisted fields populated.

        """
        return AthleteMetrics(
            max_hr=data.get(AthleteMetrics.KEY_MAX_HR, 0),
            anaerobic_threshold_hr=data.get(
                AthleteMetrics.KEY_ANAEROBIC_THRESHOLD_HR, 0
            ),
            aerobic_threshold_hr=data.get(AthleteMetrics.KEY_AEROBIC_THRESHOLD_HR, 0),
            ftp=data.get(AthleteMetrics.KEY_FTP, 0.0),
            vo2max=data.get(AthleteMetrics.KEY_VO2MAX, 0.0),
            hrv_rmssd=data.get(AthleteMetrics.KEY_HRV_RMSSD, 0.0),
            fat_max=data.get(AthleteMetrics.KEY_FAT_MAX, 0.0),
            z1_high=data.get(AthleteMetrics.KEY_Z1_HIGH, 0),
            z2_high=data.get(AthleteMetrics.KEY_Z2_HIGH, 0),
            z3_high=data.get(AthleteMetrics.KEY_Z3_HIGH, 0),
            z4_high=data.get(AthleteMetrics.KEY_Z4_HIGH, 0),
            pz1_high=data.get(AthleteMetrics.KEY_PZ1_HIGH, 0),
            pz2_high=data.get(AthleteMetrics.KEY_PZ2_HIGH, 0),
            pz3_high=data.get(AthleteMetrics.KEY_PZ3_HIGH, 0),
            pz4_high=data.get(AthleteMetrics.KEY_PZ4_HIGH, 0),
            pz5_high=data.get(AthleteMetrics.KEY_PZ5_HIGH, 0),
            pz6_high=data.get(AthleteMetrics.KEY_PZ6_HIGH, 0),
            pz7_high=data.get(AthleteMetrics.KEY_PZ7_HIGH, 0),
        )


#
# User profile
#


class UserProfile:
    """MyTraL user profile with user's preferences."""

    KEY_USER_ID = "user_id"
    KEY_USER = "user"
    KEY_DISPLAY_NAME = "display_name"
    KEY_EMAIL = "email"
    KEY_PASSWORD_ENC = "password_enc"
    KEY_EXPERT = "expert"
    KEY_AUTO_LOGIN = "auto_login"
    KEY_ADMIN = "admin"
    KEY_HEIGHT = "height"
    KEY_AGE = "age"
    KEY_BIRTHDAY = "birthday"
    KEY_BORN_YEAR = "year"
    KEY_BORN_MONTH = "month"
    KEY_BORN_DAY = "day"
    KEY_CURRENCY = "currency"
    KEY_GENDER = "gender"
    KEY_DATASET_NAME = "dataset_name"
    KEY_DATASET_NAMES = "dataset_names"

    KEY_STRAVA = "strava"
    KEY_URL = "url"
    KEY_CLIENT_ID = "client_id"
    KEY_CLIENT_ID_ENC = "client_id_enc"
    KEY_CLIENT_SECRET = "client_secret"
    KEY_CLIENT_SECRET_ENC = "client_secret_enc"
    KEY_ACCESS_TOKEN = "access_token"
    KEY_REFRESH_TOKEN = "refresh_token"
    KEY_CODE = "code"
    KEY_AUTH_UNTIL = "auth_until"

    KEY_ONBOARDING_STATE = "onboarding_state"
    KEY_ACOACH = "acoach"
    KEY_ICL = "icl"
    KEY_AVATAR_BLOB_KEY = "avatar_blob_key"
    KEY_ATHLETE_METRICS = "athlete_metrics"

    DEFAULT_AGE = 18
    DEFAULT_EMAIL = "firstname.lastname@email"

    @staticmethod
    def from_dict(profile_dict: dict) -> "UserProfile":
        today = datetime.today()

        born_year = profile_dict.get(UserProfile.KEY_BIRTHDAY, {}).get(
            UserProfile.KEY_BORN_YEAR, 0
        )
        born_month = profile_dict.get(UserProfile.KEY_BIRTHDAY, {}).get(
            UserProfile.KEY_BORN_MONTH, 0
        )
        born_day = profile_dict.get(UserProfile.KEY_BIRTHDAY, {}).get(
            UserProfile.KEY_BORN_DAY, 0
        )
        if born_year and born_month and born_day:
            age = cals.get_age(born_year, born_month, born_day)
        else:
            age = profile_dict.get(UserProfile.KEY_AGE, UserProfile.DEFAULT_AGE)

        dataset_names = profile_dict.get(UserProfile.KEY_DATASET_NAMES, [])
        dataset_names.sort(reverse=True)

        strava = profile_dict.get(UserProfile.KEY_STRAVA, {})
        strava_url = strava.get(UserProfile.KEY_URL, "")
        strava_client_id = strava.get(UserProfile.KEY_CLIENT_ID, "")
        strava_client_secret = strava.get(UserProfile.KEY_CLIENT_SECRET, "")
        strava_access_token = strava.get(UserProfile.KEY_ACCESS_TOKEN, "")
        strava_refresh_token = strava.get(UserProfile.KEY_REFRESH_TOKEN, "")
        strava_code = strava.get(UserProfile.KEY_CODE, "")
        strava_auth_until = strava.get(UserProfile.KEY_AUTH_UNTIL, 0)

        onboarding_state = profile_dict.get(UserProfile.KEY_ONBOARDING_STATE)
        acoach_settings = ai_settings.ACoachSettings.from_dict(
            profile_dict.get(UserProfile.KEY_ACOACH, {})
        )
        user_icl_settings = icl_settings.IclSettings.from_dict(
            profile_dict.get(UserProfile.KEY_ICL, {})
        )

        athlete_metrics = AthleteMetrics.from_dict(
            profile_dict.get(UserProfile.KEY_ATHLETE_METRICS, {})
        )
        raw_gender = profile_dict.get(UserProfile.KEY_GENDER)
        gender = raw_gender if isinstance(raw_gender, bool) else None

        # fail if important keys are missing
        profile = UserProfile(
            user_id=profile_dict.get(UserProfile.KEY_USER_ID, str(uuid.uuid4())),
            user=profile_dict[UserProfile.KEY_USER],
            display_name=profile_dict.get(UserProfile.KEY_DISPLAY_NAME, ""),
            email=profile_dict.get(UserProfile.KEY_EMAIL, ""),
            password_enc=profile_dict.get(UserProfile.KEY_PASSWORD_ENC, ""),
            expert=profile_dict.get(UserProfile.KEY_EXPERT, False),
            auto_login=profile_dict.get(UserProfile.KEY_AUTO_LOGIN, False),
            admin=profile_dict.get(UserProfile.KEY_ADMIN, False),
            height=profile_dict[UserProfile.KEY_HEIGHT],
            age=age,
            born_year=born_year or today.year - UserProfile.DEFAULT_AGE,
            born_month=born_month or 1,
            born_day=born_day or 1,
            currency=profile_dict.get(UserProfile.KEY_CURRENCY, "USD"),
            gender=gender,
            dataset_name=profile_dict[UserProfile.KEY_DATASET_NAME],
            dataset_names=dataset_names,
            strava_url=strava_url,
            strava_client_id=strava_client_id,
            strava_client_secret=strava_client_secret,
            strava_access_token=strava_access_token,
            strava_refresh_token=strava_refresh_token,
            strava_code=strava_code,
            strava_auth_until=strava_auth_until,
            onboarding_state=onboarding_state,
            acoach_settings=acoach_settings,
            user_icl_settings=user_icl_settings,
            athlete_metrics=athlete_metrics,
        )
        profile.avatar_blob_key = profile_dict.get(UserProfile.KEY_AVATAR_BLOB_KEY, "")
        return profile

    def to_dict(self) -> dict:
        return {
            UserProfile.KEY_USER_ID: self.user_id,
            UserProfile.KEY_USER: self.user,
            UserProfile.KEY_DISPLAY_NAME: self.display_name,
            UserProfile.KEY_EMAIL: self.email,
            UserProfile.KEY_PASSWORD_ENC: self.password_enc,
            UserProfile.KEY_EXPERT: self.expert,
            UserProfile.KEY_AUTO_LOGIN: self.auto_login,
            UserProfile.KEY_ADMIN: self.admin,
            UserProfile.KEY_HEIGHT: self.height,
            UserProfile.KEY_AGE: self.age,
            UserProfile.KEY_BIRTHDAY: {
                UserProfile.KEY_BORN_YEAR: self.born_year,
                UserProfile.KEY_BORN_MONTH: self.born_month,
                UserProfile.KEY_BORN_DAY: self.born_day,
            },
            UserProfile.KEY_CURRENCY: self.currency,
            UserProfile.KEY_GENDER: self.gender,
            UserProfile.KEY_DATASET_NAME: self.dataset_name,
            UserProfile.KEY_DATASET_NAMES: self.dataset_names,
            UserProfile.KEY_STRAVA: {
                UserProfile.KEY_URL: self.strava_url,
                UserProfile.KEY_CLIENT_ID: self.strava_client_id,
                UserProfile.KEY_CLIENT_SECRET: self.strava_client_secret,
                UserProfile.KEY_ACCESS_TOKEN: self.strava_access_token,
                UserProfile.KEY_REFRESH_TOKEN: self.strava_refresh_token,
                UserProfile.KEY_CODE: self.strava_code,
                UserProfile.KEY_AUTH_UNTIL: self.strava_auth_until,
            },
            UserProfile.KEY_ONBOARDING_STATE: self.onboarding_state,
            UserProfile.KEY_ACOACH: self.acoach_settings.to_dict()
            if self.acoach_settings
            else {},
            UserProfile.KEY_ICL: self.icl_settings.to_dict()
            if self.icl_settings
            else {},
            UserProfile.KEY_AVATAR_BLOB_KEY: self.avatar_blob_key,
            UserProfile.KEY_ATHLETE_METRICS: self.athlete_metrics.to_dict_persisted(),
        }

    @staticmethod
    def exists(user_id: str, filesystem) -> bool:
        return filesystem.user_settings_path(user_id).exists()

    def __init__(
        self,
        user_id: str,
        user: str,
        email: str,
        password_enc: str,
        dataset_name: str,
        dataset_names: list[str],
        display_name: str = "",
        expert: bool = False,
        auto_login: bool = False,
        admin: bool = False,
        height: float = 0,
        age: float = 0,
        born_year: int = 0,
        born_month: int = 0,
        born_day: int = 0,
        currency: str = "USD",
        gender: bool | None = None,
        strava_url: str = "",
        strava_client_id: str = "",
        strava_client_secret: str = "",
        strava_access_token: str = "",
        strava_refresh_token: str = "",
        strava_code: str = "",
        strava_auth_until: int = 0,
        onboarding_state: dict | None = None,
        acoach_settings: ai_settings.ACoachSettings | None = None,
        user_icl_settings: icl_settings.IclSettings | None = None,
        athlete_metrics: "AthleteMetrics | None" = None,
    ) -> None:
        """User profile constructor.

        Parameters
        ----------
        strava_client_id : str
           Machine friendly Strava username / client name.
        strava_client_secret :  str
           The only secret which is the input to the Strava authentication process.
           Client secret can be generated and received on Strava web:
           https://www.strava.com/settings/api
           The Strava authentication process typically starts by sending
           client ID and secret to (OAuth) service to get code/access/refresh token.
        strava_code : str
           Strava code is a TEMPORAL secret - code is received from Strava callback
           URL redict to get authentication token (URL has code parameter after
           redirect) and in turn used to access token.
           The code is used to create URL for OAuth service (client ID + secret + code)
           which returns the access token. After getting the access token,
           Strava authentication code can be discarded.
        strava_auth_until : int
           Access token expiration time as the number of second since the epoch start
           (1.1.1970). Is timezone considered?
        strava_refresh_token : str
           Strava refresh token can be used to easily get Strava access token,
           client ID + secret + refresh token is POSTed to OAuth service URL,
           and it returns the access token.
        strava_access_token : str
           Strava access token which is used to access Strava API. When calling any
           Strava API, access token is set as HTTP request header (bearer token/"nosic")
           and no other Strava field is needed.

        """
        self.user_id = user_id  # UUID
        self.user = user  # unique username
        self.display_name = display_name
        self.email = email
        self.password_enc = password_enc  # encrypted password
        self.expert = expert
        self.auto_login = auto_login
        self.admin = admin
        self.dataset_name = dataset_name  # dataset to be edited by MyTraL, NCName
        self.dataset_names = dataset_names or []  # available datasets, NCNames
        self.height = height  # m
        self.born_year = born_year
        self.born_month = born_month
        self.born_day = born_day
        self.age = age or self.refresh_age()
        self.currency = currency  # 3-letter currency code like USD, EUR, CZK
        # optional bool: True=man, False=woman, None=undefined
        self.gender = gender
        self.strava_url = strava_url
        self.strava_client_id = strava_client_id
        self.strava_client_secret = strava_client_secret
        self.strava_access_token = strava_access_token
        self.strava_refresh_token = strava_refresh_token
        self.strava_code = strava_code
        self.strava_auth_until = strava_auth_until
        self.strava_auth_until_str = ""

        # onboarding state
        if onboarding_state is None:
            from mytral import onboarding as ob

            self.onboarding_state = ob.get_default_onboarding_state()
        else:
            self.onboarding_state = onboarding_state

        # acoach settings
        self.acoach_settings = (
            acoach_settings
            if acoach_settings is not None
            else ai_settings.ACoachSettings.with_ootb_coaches()
        )

        # icl settings
        self.icl_settings = (
            user_icl_settings
            if user_icl_settings is not None
            else icl_settings.IclSettings.empty()
        )

        self.avatar_blob_key: str = ""

        # athlete metrics
        self.athlete_metrics: AthleteMetrics = (
            athlete_metrics if athlete_metrics is not None else AthleteMetrics()
        )

        self.refresh()

    def refresh_age(self) -> int:
        if self.born_year and self.born_month and self.born_day:
            self.age = cals.get_age(
                year=self.born_year,
                month=self.born_month,
                day=self.born_day,
            )
        else:
            self.age = UserProfile.DEFAULT_AGE

        return self.age

    def refresh(self):
        self.strava_auth_until_str = (
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.strava_auth_until))
            if self.strava_auth_until
            else ""
        )

    def add_dataset(self, dataset_name: str):
        if dataset_name not in self.dataset_names:
            self.dataset_names.append(dataset_name)
            self.dataset_names.sort()

    def save(self, mytral_fs):
        mytral_fs.save_json(
            file_path=mytral_fs.user_settings_path(self.user),
            data_dict=self.to_dict(),
        )

    def create(self, mytral_fs):
        mytral_fs.save_json(
            file_path=mytral_fs.user_settings_path(self.user),
            data_dict=self.to_dict(),
        )


class StravaUserGear:
    KEY_ID = "id"
    KEY_PRIMARY = "primary"
    KEY_NAME = "name"
    KEY_NICKNAME = "nickname"
    KEY_RESOURCE_STATE = "resource_state"
    KEY_RETIRED = "retired"
    KEY_DISTANCE = "distance"
    KEY_CONVERTED_DISTANCE = "converted_distance"
    KEY_BRAND_NAME = "brand_name"
    KEY_MODEL_NAME = "model_name"
    KEY_DESCRIPTION = "description"
    KEY_NOTIFICATION_DISTANCE = "notification_distance"

    def __init__(
        self,
        user_profile: UserProfile | None = None,
        gears: list[dict] | None = None,
        logger: loggers.MytralLogger | None = None,
    ) -> None:
        self.user_profile = user_profile
        self.logger = logger or loggers.MytralStructLogger()

        self.gears = gears or []

    def strava_gear_ids(self) -> list[str]:
        gear_ids = []
        if self.gears:
            for g in self.gears:
                gear_id = g.get(StravaUserGear.KEY_ID)
                if gear_id:
                    gear_ids.append(gear_id)
        return gear_ids

    def to_list(self) -> list:
        return self.gears

    def to_json(self) -> str:
        return json.dumps(self.gears, indent=2)
