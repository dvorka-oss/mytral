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
import enum

#
# MyTraL APP CONSTANTS
#

PRJ_DISPLAY_NAME = "MyTraL"
PRJ_NAME = "mytral"

# main applications dataset name
DATASET_NAME_MAIN = "lifelong"

# default user name (desktop app installation)
DEFAULT_USER_NAME = "dvorka"

#
# DATASETS & PERSISTENCE
#

DS_LIFELONG = "lifelong"

#
# BOOTSTRAP
#
# - used during user registration and onboarding detection
# - these values indicate that user has not yet personalized their profile
#

# bootstrap birthday: 2000-01-01 (Y2K, obviously fake)
BOOTSTRAP_BORN_YEAR = 2000
BOOTSTRAP_BORN_MONTH = 1
BOOTSTRAP_BORN_DAY = 1
# bootstrap height: 180cm (average adult height)
BOOTSTRAP_HEIGHT_CM = 1.8

# note: when ALL four values match these defaults exactly,
# the profile is considered incomplete and user should be prompted to update it

#
# URI SPACE
#

URL_ARG_ASPECT = "aspect"

#
# OOTB
#
# - intensities
# - weathers
# - activity types
# - ... for imports w/o user customizations
#

# IMPROVE make it dynamic - user_weather.json
WEATHERS = [
    ("", ""),
    ("sunny", "sunny"),
    ("cloudy", "cloudy"),
    ("fog", "fog"),
    ("hail", "hail"),
    ("lightning", "lightning"),
    ("rain", "rain"),
    ("snow", "snow"),
    ("storm", "storm"),
    ("windy", "windy"),
]

INTENSITY_NONE = ""
INTENSITY_EASY = "easy"
INTENSITY_HARD = "hard"
INTENSITY_LONG = "long"
INTENSITY_LSD = "lsd"
INTENSITY_FARTLEK = "fartlek"
INTENSITY_TEMPO = "tempo"
INTENSITY_RACE = "race"
INTENSITY_HILLS = "hills"

INTENSITIES = [
    (i, i)
    for i in [
        INTENSITY_NONE,
        INTENSITY_EASY,
        INTENSITY_HARD,
        INTENSITY_LONG,
        INTENSITY_LSD,
        INTENSITY_FARTLEK,
        INTENSITY_TEMPO,
        INTENSITY_RACE,
        INTENSITY_HILLS,
    ]
]

#
# ACTIVITY TYPES
#
# - activity types are organized to a TAXONOMY
# - taxonomy defines META activity types (like ski) and ACTIVITY TYPES (like
#   cross country ski, roller ski, ...) which are organized under META activity types
# - MyTraL aims to define as many OOTB sports as possible so that when users import
#   activities from various 3rd party services;
#   activity types are correlated/normalized and share the same ID across different
#   installations (users don't have to define custom activity types)
# - constants below can be EXTENDED / CUSTOMIZED in ActivityTypes by users
#

AT_WORKOUT = "workout"  # anything, any sport, any activity
AT_MULTISPORT = "multisport"  # quadriathlon, duathlon
AT_TRIATHLON = "triathlon"
AT_DUATHLON = "duathlon"
AT_TRANSITION = "transition"  # tri/dua/quadriathlon transitions
# AT: endurance
AT_CANOE = "canoe"
AT_CANOEING = "canoeing"  # kayak or canoe
AT_HIKE = "hike"
AT_KAYAK = "kayak"
AT_PADDLE = "paddleboard"
AT_RIDE = "ride"  # road bike
AT_RIDE_ERG = "ride_erg"
AT_RIDE_HAND = "handcycle"
AT_RIDE_MOUNTAIN = "mountain_bike"
AT_RIDE_E = "ebike"
AT_RIDE_VIRTUAL = "virtualride"
AT_ROW = "row"
AT_ROW_ERG = "erg_row"  # Concept 2
AT_RS_DP = "roller_ski_dp"  # roller ski double poling ~ soupaž/classic
AT_RS_F = "roller_ski_f"  # roller ski free style ~ skate
AT_RUN = "run"
AT_RUN_VIRTUAL = "virtualrun"
AT_SAIL = "sail"
AT_SKATE_ICE = "skate_ice"
AT_SKATE_INLINE = "skate_inline"
AT_SKI_BACKCOUNTRY = "ski_backcountry"
AT_SKI_DP = "ski_dp"  # double poling ~ soupaž/classic
AT_SKI_F = "ski_f"  # free style ~ skate
AT_SKI_WATER = "water_ski"
AT_RAFT = "raft"
AT_SNOWSHOE = "snowshoe"
AT_SURF = "surfing"
AT_SURF_KITE = "kitesurf"
AT_SURF_WIND = "windsurf"
AT_SURF_WAKEBOARD = "wakeboard"
AT_SURF_WAKE = "wakesurf"
AT_SWIM = "swim"
AT_DIVE = "dive"
AT_VELOMOBILE = "velomobile"
AT_WALK = "walk"
AT_WHEELCHAIR = "wheelchair"
# AT: activity w/o distance: exercise
AT_ARCHERY = "archery"
AT_CALISTHENICS = "calisthenics"
AT_CROSSFIT = "crossfit"
AT_DANCE = "dance"
AT_ELLIPTICAL = "elliptical"
AT_GYM = "exercise"  # calisthenics, gym, fitness, , ...
AT_HIIT = "hiit"
AT_MOBILITY = "mobility"
AT_PHYSIO = "physio"  # physiotherapy, rehabilitation, ...
AT_STAIR_STEPPER = "stair_stepper"
AT_STRETCHING = "stretching"
AT_YOGA = "yoga"
# AT: games
AT_BASEBALL = "baseball"
AT_BASKETBALL = "basketball"
AT_CRICKET = "cricket"
AT_DISC_GOLF = "disc_golf"
AT_FOOTBAL = "american_football"
AT_GOLF = "golf"
AT_HOCKEY = "hockey"
AT_LACROSSE = "lacrosse"
AT_RUGBY = "rugby"
AT_SOCCER = "soccer"
AT_TENNIS = "tennis"
AT_VOLLEYBALL = "volleyball"
# AT: other activities: ignore
AT_CLIMB_ROCK = "rock_climb"
AT_FLYING = "flying"
AT_SKYDIVE = "sky_dive"
AT_HAND_GLIDING = "hand_gliding"  # rogalo
AT_SKATEBOARD = "skateboard"
AT_SKI_DOWNHILL = "ski_downhill"
AT_SKI_SLALOM = "ski_slalom"
AT_SNOWBOARD = "snowboard"
AT_HORSE_RIDING = "horse_riding"
AT_BOX = "box"
AT_MMA = "mma"
# AT: regeneration
AT_SLEEP = "sleep"  # sleep from previous day + afternoon naps :-)
AT_SAUNA = "sauna"
AT_STEAM = "steam"
AT_MEDITATION = "meditation"
# AT: injuries / sicknesses
AT_SICK = "sick"  # a sickness or injury stopping from training (injury @ activity)
AT_INJURED = (
    "injured"  # the problem is related to the activity_type_key e.g. muscle strain
)
# AT: day metadata
AT_COMMENT = "comment"
AT_PLAN = "plan"  # TODO deprecated

#
# META ACTIVITY TYPES
#


def guess_activity_type_from_pace(avg_speed_kmh: float) -> str:
    """Guess activity type from average speed in km/h.

    Parameters
    ----------
    avg_speed_kmh : float
        Average speed in km/h.

    Returns
    -------
    str
        Guessed activity type key (one of ``AT_WALK``, ``AT_RUN``, ``AT_RIDE``,
        or ``AT_WORKOUT``).
    """
    if avg_speed_kmh < 7.0:
        return AT_WALK
    if avg_speed_kmh < 15.0:
        return AT_RUN
    return AT_RIDE


M_AT_ALPINE_SKI = "alpine_ski"
M_AT_CANOEING = "canoeing"  # kayak, canoe, paddleboard
M_AT_GAMES = "games"
M_AT_GYM = "gym"  # crossfit, calisthenics, ...
M_AT_HIKE = "hike"  # hiking, walking, snowshoeing, ...
M_AT_MULTISPORT = "multisport"
M_AT_PHYSIO = "physiotherapy"
M_AT_RIDE = "ride"  # road bike + MTB
M_AT_ROW = "row"  # rowing + erg
M_AT_RUN = "run"  # running
M_AT_SKI = "ski"  # nordic ski: ski DP/F + rollerski DP/F + backcountry
M_AT_SWIM = "swim"  # swimming
M_AT_RELAX = "relax"  # wellness

#
# ACTIVITY TYPE TAXONOMY
#
# - NOT all ATs are in the taxonomy
#
AT_TAXONOMY = {
    M_AT_RUN: [
        AT_RUN,
        AT_RUN_VIRTUAL,
    ],
    M_AT_SKI: [
        AT_RS_DP,
        AT_RS_F,
        AT_SKI_BACKCOUNTRY,
        AT_SKI_DP,
        AT_SKI_F,
    ],
    M_AT_RIDE: [
        AT_RIDE,
        AT_RIDE_E,
        AT_RIDE_ERG,
        AT_RIDE_HAND,
        AT_RIDE_MOUNTAIN,
        AT_VELOMOBILE,
        AT_RIDE_VIRTUAL,
    ],
    M_AT_ROW: [
        AT_ROW,
        AT_ROW_ERG,
    ],
    M_AT_CANOEING: [
        AT_CANOEING,
        AT_CANOE,
        AT_KAYAK,
        AT_PADDLE,
        AT_RAFT,
    ],
    M_AT_SWIM: [
        AT_SWIM,
    ],
    M_AT_GYM: [
        AT_CALISTHENICS,
        AT_CROSSFIT,
        AT_ELLIPTICAL,
        AT_GYM,
        AT_STAIR_STEPPER,
        AT_HIIT,
    ],
    M_AT_HIKE: [
        AT_HIKE,
        AT_WALK,
        AT_SNOWSHOE,
        AT_WHEELCHAIR,
    ],
    M_AT_ALPINE_SKI: [
        AT_SKI_DOWNHILL,
        AT_SNOWBOARD,
        AT_SKI_SLALOM,
        AT_SKI_WATER,
    ],
    M_AT_PHYSIO: [
        AT_MOBILITY,
        AT_PHYSIO,
        AT_STRETCHING,
        AT_YOGA,
    ],
    M_AT_MULTISPORT: [
        AT_DUATHLON,
        AT_MULTISPORT,
        AT_TRANSITION,
        AT_TRIATHLON,
    ],
    M_AT_GAMES: [
        AT_BASEBALL,
        AT_BASKETBALL,
        AT_CRICKET,
        AT_DISC_GOLF,
        AT_FOOTBAL,
        AT_GOLF,
        AT_HOCKEY,
        AT_LACROSSE,
        AT_RUGBY,
        AT_SOCCER,
        AT_TENNIS,
        AT_VOLLEYBALL,
    ],
    M_AT_RELAX: [
        AT_MEDITATION,
        AT_SAUNA,
        AT_SLEEP,
        AT_STEAM,
    ],
}

#
# UNIVERSAL KM COEFFICIENTS
#
# - activity km to universal km conversion
#  - activity_types which don't have a coefficient are NOT counted to universal km
#

# coefficients used in my legacy paper and digital training logs
_LEGACY_UKM_COEFFICIENTS = {
    AT_RUN: 1.0,
    AT_RIDE: 0.5,
    AT_ROW: 1.0,
    AT_SKI_DP: 0.5,
    AT_SKI_F: 0.5,
    AT_RS_DP: 0.5,
    AT_RS_F: 0.5,
    AT_SWIM: 5.0,
}

_MYTRAL_UKM_COEFFICIENTS = {
    AT_RUN: 1.0,
    AT_RIDE: 0.4,
    AT_ROW: 1.0,
    AT_SKI_DP: 0.6,
    AT_SKI_F: 0.5,
    AT_RS_DP: 0.6,
    AT_RS_F: 0.5,
    AT_SWIM: 5.0,
}

UKM_COEFFICIENTS = _LEGACY_UKM_COEFFICIENTS

#
# theoretical constants used in calculations
#

# map: activity_type_key -> kcal
# https://6000kroku.cz/clanek/spotreba-energie-pri-fyzicke-aktivite
KCAL_PER_HOUR = {
    AT_RUN: 841,
    AT_HIKE: 255,
    AT_RIDE: 802,
    AT_ROW: 631,
    AT_ROW_ERG: 631,
    AT_SKI_DP: 1000,
    AT_SKI_F: 722,
    AT_SWIM: 850,
}

# map: activity_type_key -> O2/min/kg in liters
O2_PER_MIN_PER_KG = {
    AT_RUN: 0.048,
    AT_RIDE: 0.033,
    AT_SKI_DP: 0.036,
    AT_SKI_F: 0.036,
    AT_SWIM: 0.023,
}


#
# aspects
#


class StatsAspect(enum.Enum):
    """Stats aspect: distance, time, ..."""

    ACTIVITIES = enum.auto()
    DISTANCE = enum.auto()
    DURATION = enum.auto()
    KGS = enum.auto()


class StatsPeriod(enum.Enum):
    """Time period aspect: year, month, ..."""

    YEAR = enum.auto()
    MONTH = enum.auto()
    WEEK = enum.auto()
