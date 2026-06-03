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
from mytral import commons

#
# integration commons: constants for Strava, FIT files, GPX extensions, GDocs, ...
#

#
# Strava
#

# Strava API:
#   - https://developers.strava.com/docs/reference/
#   - https://developers.strava.com/docs/reference/#api-models-ActivityType
STRAVA_ACTIVITY_TYPE = [
    "AlpineSki",
    "BackcountrySki",
    "Canoeing",
    "Crossfit",
    "EBikeRide",
    "Elliptical",
    "Golf",
    "Handcycle",
    "Hike",
    "IceSkate",
    "InlineSkate",
    "Kayaking",
    "Kitesurf",
    "NordicSki",
    "Ride",
    "RockClimbing",
    "RollerSki",
    "Rowing",
    "Run",
    "Sail",
    "Skateboard",
    "Snowboard",
    "Snowshoe",
    "Soccer",
    "StairStepper",
    "StandUpPaddling",
    "Surfing",
    "Swim",
    "Velomobile",
    "VirtualRide",
    "VirtualRun",
    "Walk",
    "WaterSport",
    "WeightTraining",
    "Wheelchair",
    "Windsurf",
    "Workout",
    "Yoga",
]

# Strava API:
#   - https://developers.strava.com/docs/reference/
#   - https://developers.strava.com/docs/reference/#api-models-SportType
STRAVA_SPORT_TYPE = [
    "AlpineSki",
    "BackcountrySki",
    "Badminton",
    "Basketball",
    "Canoeing",
    "Cricket",
    "Crossfit",
    "Dance",
    "EBikeRide",
    "EMountainBikeRide",
    "Elliptical",
    "Golf",
    "GravelRide",
    "Handcycle",
    "HighIntensityIntervalTraining",
    "Hike",
    "IceSkate",
    "InlineSkate",
    "Kayaking",
    "Kitesurf",
    "MountainBikeRide",
    "NordicSki",
    "Padel",
    "PhysicalTherapy",
    "Pickleball",
    "Pilates",
    "Racquetball",
    "Ride",
    "RockClimbing",
    "RollerSki",
    "Rowing",
    "Run",
    "Sail",
    "Skateboard",
    "Snowboard",
    "Snowshoe",
    "Soccer",
    "Squash",
    "StairStepper",
    "StandUpPaddling",
    "Surfing",
    "Swim",
    "TableTennis",
    "Tennis",
    "TrailRun",
    "Velomobile",
    "VirtualRide",
    "VirtualRow",
    "VirtualRun",
    "Volleyball",
    "Walk",
    "WeightTraining",
    "Wheelchair",
    "Windsurf",
    "Workout",
    "Yoga",
]

STRAVA_SPORT = set(STRAVA_ACTIVITY_TYPE).union(set(STRAVA_SPORT_TYPE))

STRAVA_TO_MYTRAL_AT = {
    "alpineski": commons.AT_SKI_DOWNHILL,
    "backcountryski": commons.AT_SKI_BACKCOUNTRY,
    "badminton": commons.AT_BADMINTON,
    "basketball": commons.AT_BASKETBALL,
    "canoeing": commons.AT_CANOEING,
    "cricket": commons.AT_CRICKET,
    "crossfit": commons.AT_CROSSFIT,
    "dance": commons.AT_DANCE,
    "ebikeride": commons.AT_RIDE_E,
    "elliptical": commons.AT_ELLIPTICAL,
    "emountainbikeride": commons.AT_RIDE_E,
    "golf": commons.AT_GOLF,
    "gravelride": commons.AT_RIDE_GRAVEL,
    "handcycle": commons.AT_RIDE_HAND,
    "highintensityintervaltraining": commons.AT_HIIT,
    "hike": commons.AT_HIKE,
    "iceskate": commons.AT_SKATE_ICE,
    "inlineskate": commons.AT_SKATE_INLINE,
    "kayaking": commons.AT_KAYAK,
    "kitesurf": commons.AT_SURF_KITE,
    "mountainbikeride": commons.AT_RIDE_MOUNTAIN,
    "nordicski": commons.AT_SKI_F,
    "padel": commons.AT_PADDLE,
    "physicaltherapy": commons.AT_PHYSIO,
    "pickleball": commons.AT_PICKLEBALL,
    "pilates": commons.AT_PILATES,
    "racquetball": commons.AT_RACQUETBALL,
    "ride": commons.AT_RIDE,
    "rockclimbing": commons.AT_CLIMB_ROCK,
    "rollerski": commons.AT_RS_F,
    "rowing": commons.AT_ROW,
    "run": commons.AT_RUN,
    "sail": commons.AT_SAIL,
    "skateboard": commons.AT_SKATEBOARD,
    "snowboard": commons.AT_SNOWBOARD,
    "snowshoe": commons.AT_SNOWSHOE,
    "soccer": commons.AT_SOCCER,
    "squash": commons.AT_SQUASH,
    "stairstepper": commons.AT_STAIR_STEPPER,
    "standuppaddling": commons.AT_PADDLE,
    "surfing": commons.AT_SURF,
    "swim": commons.AT_SWIM,
    "tabletennis": commons.AT_TABLETENNIS,
    "tennis": commons.AT_TENNIS,
    "trailrun": commons.AT_RUN_TRAIL,
    "velomobile": commons.AT_VELOMOBILE,
    "virtualride": commons.AT_RIDE_VIRTUAL,
    "virtualrow": commons.AT_ROW_ERG,
    "virtualrun": commons.AT_RUN_VIRTUAL,
    "volleyball": commons.AT_VOLLEYBALL,
    "walk": commons.AT_WALK,
    "watersport": commons.AT_CANOEING,
    "weighttraining": commons.AT_GYM,
    "wheelchair": commons.AT_WHEELCHAIR,
    "windsurf": commons.AT_SURF_WIND,
    "workout": commons.AT_WORKOUT,  # anything and everything
    "yoga": commons.AT_YOGA,
}

STRAVA_GEAR_PREFIX_ID = "strava-gear-id:"

#
# FIT
#
# - https://github.com/garmin/fit-python-sdk/blob/main/garmin_fit_sdk/profile.py
#

# FIT sports taken from the profile.py - apart to "sport", there are also "sport_bit_*"
FIT_INT_SPORT_TO_STR = {
    0: "generic",
    1: "running",
    2: "cycling",
    3: "transition",  # Multisport transition
    4: "fitness_equipment",
    5: "swimming",
    6: "basketball",
    7: "soccer",
    8: "tennis",
    9: "american_football",
    10: "training",
    11: "walking",
    12: "cross_country_skiing",
    13: "alpine_skiing",
    14: "snowboarding",
    15: "rowing",
    16: "mountaineering",
    17: "hiking",
    18: "multisport",
    19: "paddling",
    20: "flying",
    21: "e_biking",
    22: "motorcycling",
    23: "boating",
    24: "driving",
    25: "golf",
    26: "hang_gliding",
    27: "horseback_riding",
    28: "hunting",
    29: "fishing",
    30: "inline_skating",
    31: "rock_climbing",
    32: "sailing",
    33: "ice_skating",
    34: "sky_diving",
    35: "snowshoeing",
    36: "snowmobiling",
    37: "stand_up_paddleboarding",
    38: "surfing",
    39: "wakeboarding",
    40: "water_skiing",
    41: "kayaking",
    42: "rafting",
    43: "windsurfing",
    44: "kitesurfing",
    45: "tactical",
    46: "jumpmaster",
    47: "boxing",
    48: "floor_climbing",
    49: "baseball",
    53: "diving",
    56: "shooting",  # Sport Shooting bits, set here for sport_bits alignment
    58: "winter_sport",
    59: "grinding",  # Sailing position, operating manual winches to power boat controls
    62: "hiit",
    63: "video_gaming",
    64: "racket",
    65: "wheelchair_push_walk",
    66: "wheelchair_push_run",
    67: "meditation",
    68: "para_sport",
    69: "disc_golf",
    70: "team_sport",
    71: "cricket",
    72: "rugby",
    73: "hockey",
    74: "lacrosse",
    75: "volleyball",
    76: "water_tubing",
    77: "wakesurfing",
    78: "water_sport",
    79: "archery",
    80: "mixed_martial_arts",
    81: "motor_sports",
    82: "snorkeling",
    83: "dance",
    84: "jump_rope",
    85: "pool_apnea",
    86: "mobility",
    87: "geocaching",
    88: "canoeing",
    254: "all",  # "all" is for goals only to include all sports.
}

FIT_INT_SPORT_TO_MYTRAL_AT = {
    "generic": commons.AT_WORKOUT,  # 0
    "running": commons.AT_RUN,  # 1
    "cycling": commons.AT_RIDE,  # 2
    "transition": commons.AT_TRANSITION,  # 3
    "fitness_equipment": commons.AT_WORKOUT,  # 4
    "swimming": commons.AT_SWIM,  # 5
    "basketball": commons.AT_BASKETBALL,  # 6
    "soccer": commons.AT_SOCCER,  # 7
    "tennis": commons.AT_TENNIS,  # 8
    "american_football": commons.AT_FOOTBAL,  # 9
    "training": commons.AT_WORKOUT,  # 10
    "walking": commons.AT_WALK,  # 11
    "cross_country_skiing": commons.AT_SKI_F,  # 12
    "alpine_skiing": commons.AT_SKI_DOWNHILL,  # 13
    "snowboarding": commons.AT_SNOWBOARD,  # 14
    "rowing": commons.AT_ROW,  # 15
    "mountaineering": commons.AT_CLIMB_ROCK,  # 16
    "hiking": commons.AT_HIKE,  # 17
    "multisport": commons.AT_MULTISPORT,  # 18
    "paddling": commons.AT_PADDLE,  # 19
    "flying": commons.AT_FLYING,  # 20
    "e_biking": commons.AT_RIDE_E,  # 21
    "motorcycling": commons.AT_VELOMOBILE,  # 22
    "boating": commons.AT_SAIL,  # 23
    "driving": commons.AT_WORKOUT,  # 24
    "golf": commons.AT_GOLF,  # 25
    "hang_gliding": commons.AT_HAND_GLIDING,  # 26
    "horseback_riding": commons.AT_WORKOUT,  # 27
    "hunting": commons.AT_HIKE,  # 28
    "fishing": commons.AT_WORKOUT,  # 29
    "inline_skating": commons.AT_SKATE_INLINE,  # 30
    "rock_climbing": commons.AT_CLIMB_ROCK,  # 31
    "sailing": commons.AT_SAIL,  # 32
    "ice_skating": commons.AT_SKATE_ICE,  # 33
    "sky_diving": commons.AT_SKYDIVE,  # 34
    "snowshoeing": commons.AT_SNOWSHOE,  # 35
    "snowmobiling": commons.AT_SKI_DOWNHILL,  # 36
    "stand_up_paddleboarding": commons.AT_PADDLE,  # 37
    "surfing": commons.AT_SURF,  # 38
    "wakeboarding": commons.AT_SURF_WAKEBOARD,  # 39
    "water_skiing": commons.AT_SKI_WATER,  # 40
    "kayaking": commons.AT_KAYAK,  # 41
    "rafting": commons.AT_RAFT,  # 42
    "windsurfing": commons.AT_SURF_WIND,  # 43
    "kitesurfing": commons.AT_SURF_KITE,  # 44
    "tactical": commons.AT_WORKOUT,  # 45
    "jumpmaster": commons.AT_WORKOUT,  # 46
    "boxing": commons.AT_BOX,  # 47
    "floor_climbing": commons.AT_STAIR_STEPPER,  # 48
    "baseball": commons.AT_BASEBALL,  # 49
    "diving": commons.AT_DIVE,  # 53
    "shooting": commons.AT_WORKOUT,  # 56
    "winter_sport": commons.AT_WORKOUT,  # 58
    "grinding": commons.AT_SAIL,  # 59
    "hiit": commons.AT_HIIT,  # 62
    "video_gaming": commons.AT_WORKOUT,  # 63
    "racket": commons.AT_WORKOUT,  # 64
    "wheelchair_push_walk": commons.AT_WHEELCHAIR,  # 65
    "wheelchair_push_run": commons.AT_WHEELCHAIR,  # 66
    "meditation": commons.AT_MEDITATION,  # 67
    "para_sport": commons.AT_WORKOUT,  # 68
    "disc_golf": commons.AT_DISC_GOLF,  # 69
    "team_sport": commons.AT_WORKOUT,  # 70
    "cricket": commons.AT_CRICKET,  # 71
    "rugby": commons.AT_RUGBY,  # 72
    "hockey": commons.AT_HOCKEY,  # 73
    "lacrosse": commons.AT_LACROSSE,  # 74
    "volleyball": commons.AT_VOLLEYBALL,  # 75
    "water_tubing": commons.AT_SURF,  # 76
    "wakesurfing": commons.AT_SURF_WAKE,  # 77
    "water_sport": commons.AT_WORKOUT,  # 78
    "archery": commons.AT_ARCHERY,  # 79
    "mixed_martial_arts": commons.AT_MMA,  # 80
    "motor_sports": commons.AT_VELOMOBILE,  # 81
    "snorkeling": commons.AT_SWIM,  # 82
    "dance": commons.AT_DANCE,  # 83
    "jump_rope": commons.AT_WORKOUT,  # 84
    "pool_apnea": commons.AT_SWIM,  # 85
    "mobility": commons.AT_MOBILITY,  # 86
    "geocaching": commons.AT_WALK,  # 87
    "canoeing": commons.AT_CANOEING,  # 88
    "all": commons.AT_WORKOUT,  # 254
}
