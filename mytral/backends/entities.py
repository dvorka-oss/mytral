# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import dataclasses
import json
from datetime import datetime

from mytral import commons
from mytral import settings

PREFIX_KEY = "seq-"

KEY_SICKNESS_SYMPTOMS = "sickness_symptoms"
KEY_EXERCISES = "exercises"
KEY_LAPS = "laps"


def _when_as_str(
    when_year: int,
    when_month: int,
    when_day: int,
    when_hour: int,
    when_minute: int,
    when_second: int,
    debug_msg: str = "",
) -> str:
    """Convert when integer fields to string with the format:

    YYYY-MM-DD HH:MM:SS

    Parameters
    ----------
    when_year: int
      Year.

    """
    when: str = (
        f"{when_year}-{when_month:02}-{when_day:02} "
        f"{when_hour:02}:{when_minute:02}:{when_second:02}"
    )
    return when


def kmh_to_pace(kmh: float) -> str:
    """Converts speed in km/h to pace in minutes per kilometer.

    Parameters
    ----------
        kmh : float
          Speed in kilometers per hour (float).

    Returns
    -------
    str :
        A string representing the pace in minutes and seconds per km,
        or None if the input is invalid (e.g., zero or negative speed).

    """
    if not kmh:
        return ""

    if not isinstance(kmh, (int, float)):
        raise TypeError("Speed must be a number (int or float).")

    if kmh <= 0:
        return ""

    seconds_per_km = 3600 / kmh  # 3600 seconds in an hour
    minutes = int(seconds_per_km // 60)  # integer division for whole minutes
    seconds = int(seconds_per_km % 60)  # modulo for remaining seconds

    return f"{minutes}:{seconds:02}"  # format to have leading zero if seconds < 10


@dataclasses.dataclass
class DbEntity:
    """Database entity."""

    key: str = ""
    name: str = ""
    description: str = ""

    when_year: int = 0
    when_month: int = 0
    when_day: int = 0
    when_hour: int = 0
    when_minute: int = 0
    when_second: int = 0
    when: str = ""

    def __post_init__(self):
        now = datetime.now()
        if not self.when_year:
            self.when_year = now.year
        if not self.when_month:
            self.when_month = now.month
        if not self.when_day:
            self.when_day = now.day
        # only fill time from now when no time component was provided at all
        if not self.when_hour and not self.when_minute and not self.when_second:
            self.when_hour = now.hour
            self.when_minute = now.minute
            self.when_second = now.second

        self.when = _when_as_str(
            when_year=self.when_year,
            when_month=self.when_month,
            when_day=self.when_day,
            when_hour=self.when_hour,
            when_minute=self.when_minute,
            when_second=self.when_second,
            debug_msg=f"dataclass CONSTRUCTOR of '{self.name}'",
        )


SS_SIDE_LEFT = "left"
SS_SIDE_RIGHT = "right"


@dataclasses.dataclass
class SicknessSymptomEntity:
    """Sickness or injury symptom."""

    activity_key: str = ""

    symptom: str = ""  # injure o disease description prefilled from user profile
    side: str = ""  # left / right / ""
    body_part: str = ""  # impacted body part
    health: int = 0  # 100% healthy or 0% (sick)


@dataclasses.dataclass
class ExerciseEntity:
    activity_key: str = ""

    name: str = ""

    weight: float = 0.0  # kg
    series: int = 0
    repetitions: int = 0

    duration: int = 0  # seconds
    rest: int = 0  # seconds


@dataclasses.dataclass
class LapEntity:
    """Lap within an activity - represents a single lap/interval in a workout."""

    activity_key: str = ""
    order: int = 0  # order of the lap in the activity (1, 2, 3, ...)

    name: str = ""  # reference to standalone lap type or custom name

    distance: int = 0  # meters (overrides default from lap type if set)
    duration: int = 0  # seconds (overrides default from lap type if set)
    comment: str = ""  # additional notes for this specific lap
    ranked: bool = False  # ranked lap used to build PBs/PRs


# transient fields that should NOT be persisted (they are calculated)
ACTIVITY_TRANSIENT_FIELDS = {
    "duration",
    "duration_seconds",
    "avg_speed",
    "pace",
    "bmi",
    "burnt_fat",
    "exercise_kgs",
    "transient_fields",
}

# map: activity entity field (str) -> default value
ACTIVITY_FIELD_DEFAULTS = {
    # time 2 distance and vice versa
    "distance": 0,
    "hours": 0,
    "minutes": 0,
    "seconds": 0,
    # stats
    "kcal": 0,
    "duration": "00h00m00s",
    "duration_seconds": 0,
    "avg_speed": 0.0,
    "bmi": 0.0,
    "burnt_fat": 0.0,
    "fitness_score": 0.0,
}


@dataclasses.dataclass
class ActivityEntity(DbEntity):
    """Activity is a building block of the workout. Typical workout is formed by a
    warm-up activity, a main workout activity and a cool down activity.

    Conventions:

    - 0 ... unused value
    - 1 ... sort codes, workouts, ... are counted from 1 (not 0)

    sort_code : int
      Order of the activity within the workout.
    workout_sort_code : int
      Workout identifier - just a number which binds multiple activities to
      a workout. This identifier is not database key. This identifier is used also as
      a sort code i.e. morning workout sort code will be lower than evening workout
      sort code (in case of multiple workouts within the day).
    activity_type_key : str
      Sport like "ride", "run", "rowing", "ski", "rollerski" as open enum
      containing values gathered from all workout entries.
    formula : str
      Workout formula describing what was exercised, number of repetitions, rest and
      more. For instance:
        - 3*(10*squats + 5*crunches)
        - 3*(2k/r30s + 3k/r20s)
    intensity : str
      Activity intensity like easy, hard, regen, LSD, fartlek, tempo, race,
      ... as open enum
    time : str
      Activity time as string: 00h00m00s
    src : str
      Source of the activity e.g. on Strava or concept2.com (open enum):
      - strava.com
      - concept2.com
      - manual (default)
    src_descriptor : str
      Extension point allowing to specify additional information for ``src`` e.g. in
      which XLS sheet or paper log book I have this entry e.g. green paper log book '97
    src_key : str
      Strava UUID or other service internal ID which can be used to uniquely identify
      this activity.

    """

    sort_code: int = 1  # order of this activity within the workout
    workout_sort_code: int = 1  # key of the workout where this activity belongs

    tags: list[str] = dataclasses.field(default_factory=list)
    is_plan: bool = dataclasses.field(default=False)  # is planned activity

    where: str = ""

    activity_type_key: str = "run"
    intensity: str = commons.INTENSITY_EASY
    gears: list[str] = dataclasses.field(default_factory=lambda: [])
    outfit: str = ""
    formula: str = ""  # formula w/ my DSL/convention: w2k + 5x500m@1:45/r30s + c10'

    exercises: list[ExerciseEntity] | None = dataclasses.field(
        default_factory=lambda: []
    )

    sickness_symptoms: list[SicknessSymptomEntity] | None = dataclasses.field(
        default_factory=lambda: []
    )

    laps: list[LapEntity] | None = dataclasses.field(default_factory=lambda: [])

    # duration
    hours: int = 0
    minutes: int = 0
    seconds: int = 0

    distance: int = 0  # meters

    warm_up: bool = False
    cool_down: bool = False
    commute: bool = False
    race: bool = False  # marks the activity which was a race
    ranked: bool = False  # ranked activity used to build PBs/PRs like on concept2.com

    kcal: int = 0  # kcal
    max_speed: float = 0.0  # km/h
    elevation_gain: int = 0  # meters
    elevation_min: int = 0  # meters
    elevation_max: int = 0  # meters

    avg_watts: float = 0.0  # Watts (power)
    max_watts: float = 0.0

    avg_cadence: float = 0.0  # revolutions/strokes per minute
    max_cadence: float = 0.0

    avg_hr: float = 0.0
    max_hr: float = 0.0
    min_hr: float = 0.0  # resting HR (like weight) - not related to activity, but day

    weight: float = 0.0  # kg

    cost: float = 0.0  # cost of the activity (e.g., gym entry, sauna, race fee)

    weather: str = ""  # cloudy, sunny, windy, ...
    temperature: int = 18  # celsius

    fitness_score: float = 0.0

    src: str = "manual"  # manual, paper-import, strava-import, concept2-import
    src_descriptor: str = ""  # any key=value; attributes/parameters/...
    src_key: str = ""  # 3rd party UUID
    src_url: str = ""  # for instance strava.com link

    # keys pointing into blobstore to original .fit/.gpx/.hrm/* files: UUID.[suffix]
    recorded_blob_keys: list[str] = dataclasses.field(default_factory=lambda: [])
    # map from recoded blob key ^ (w/o suffix) -> to Parquet key in the blobstore
    recorded_parquet_keys: dict[str, str] = dataclasses.field(
        default_factory=lambda: {}
    )
    # blobstore keys pointing to activity's photos
    photo_blob_keys: list[str] = dataclasses.field(default_factory=lambda: [])
    # blobstore key pointing to activity's HIGHLIGHT photos
    highlight_photo_blob_key: str = ""

    # statistics are calculated from the input values from above

    duration: str = ""  # 00h00m00s
    duration_seconds: int = 0
    exercise_kgs: float = 0.0  # total exercise kilograms
    avg_speed: float = 0.0  # km/h
    pace: str = ""
    bmi: float = 0.0
    burnt_fat: float = 0.0  # grams

    # ^ statistical fields which must NOT be stored to database as they were NOT set
    # by user/on import, but they were calculated from the input values to be shown in
    # the UI
    # map: field (str) -> original value prior to calculation
    transient_fields: dict | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    def to_sparse_dict(self) -> dict:
        """Convert to sparse dictionary containing only non-default values."""
        sparse_dict = {}
        for field in dataclasses.fields(self):
            # skip transient fields that should not be persisted
            if field.name in ACTIVITY_TRANSIENT_FIELDS:
                continue

            value = getattr(self, field.name)
            if (
                field.default is dataclasses.MISSING
                and field.default_factory is dataclasses.MISSING
            ):
                sparse_dict[field.name] = value
            elif field.default_factory is not dataclasses.MISSING:
                default_value = field.default_factory()
                if value != default_value:
                    if field.name in [KEY_SICKNESS_SYMPTOMS, KEY_EXERCISES, KEY_LAPS]:
                        sparse_dict[field.name] = [dataclasses.asdict(v) for v in value]
                    else:
                        # plain list fields (e.g. gears, photo_blob_keys)
                        sparse_dict[field.name] = value
            else:
                if value != field.default:
                    sparse_dict[field.name] = value
        return sparse_dict

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class UserActivities:
    """User activities."""

    def __init__(self, activities: list[ActivityEntity] | None = None) -> None:
        self.by_key = {a.key: a for a in activities} if activities else {}

    def from_dict(self, data: dict):
        self.by_key = {k: ActivityEntity(**v) for k, v in data.items()}

    def empty(self) -> bool:
        return not self.by_key

    def exists(self, key: str) -> bool:
        return key in self.by_key

    def delete(self, key: str):
        del self.by_key[key]


def recording_blob_uuid(entry: str) -> str:
    """Extract the blob UUID from a recorded_blob_keys entry.

    Parameters
    ----------
    entry : str
        Entry in the format ``"<UUID>.<ext>"`` (e.g. ``"abc123.fit"``).

    Returns
    -------
    str
        The UUID portion before the last dot.
    """
    return entry.rsplit(".", 1)[0]


def recording_ext(entry: str) -> str:
    """Extract the file extension from a recorded_blob_keys entry.

    Parameters
    ----------
    entry : str
        Entry in the format ``"<UUID>.<ext>"`` (e.g. ``"abc123.fit"``).

    Returns
    -------
    str
        The extension including the leading dot (e.g. ``".fit"``).
    """
    return "." + entry.rsplit(".", 1)[-1]


def activity_clear_transient_fields(entity: ActivityEntity) -> ActivityEntity:
    """Clear transient fields of the activity entity."""
    if entity.transient_fields:
        for field in entity.transient_fields:
            setattr(entity, field, None)

    return entity


def evaluate_exercise_kgs(entity: ActivityEntity) -> float:
    """Calculate total exercise kilograms."""
    if entity.exercises:
        if isinstance(entity.exercises[0], dict):
            return sum([e.weight * e.series * e.repetitions for e in entity.exercises])
        else:
            return sum([e.weight * e.series * e.repetitions for e in entity.exercises])
    return 0.0


def evaluate_activity(
    entity: ActivityEntity, user_profile: settings.UserProfile | None = None
) -> ActivityEntity:

    entity.when = _when_as_str(
        when_year=entity.when_year,
        when_month=entity.when_month,
        when_day=entity.when_day,
        when_hour=entity.when_hour,
        when_minute=entity.when_minute,
        when_second=entity.when_second,
        debug_msg=f"evaluate_entity('{entity.name}')",
    )

    entity.duration_seconds = (
        entity.hours * 3_600 + entity.minutes * 60 + entity.seconds
    )

    entity.duration = f"{entity.hours:02}h{entity.minutes:02}m{entity.seconds:02}s"

    entity.exercise_kgs = evaluate_exercise_kgs(entity)

    entity.avg_speed = (
        (entity.distance / entity.duration_seconds) * 3.6
        if entity.duration_seconds
        else 0.0
    )

    entity.pace = kmh_to_pace(entity.avg_speed)

    if user_profile:
        entity.bmi = (
            entity.weight / ((user_profile.height / 100.0) ** 2)
            if user_profile and user_profile.height
            else 0.0
        )
    entity.burnt_fat = entity.burnt_fat or 0.0

    return entity


@dataclasses.dataclass
class WorkoutEntity(DbEntity):
    """Workout is formed by activities - typically by a warm-up activity,
    a main workout activity and a cool down activity:

    1. warm-up: 2k row
    2. warm-up stretching
    3. concept2: 5x500m@1:45/r30s
    4. cool-down: 10' row

    Workout entity is expendable - exported dataset is formed by activities where
    activity is the row in the dataset. Workout is "index" i.e. it might be built
    from the activities, and it must **not** contain any value which cannot be
    inferred/calculated from activities (like additional description)

    warm_up : List
      Warm up activities.
    distance : int
      Total distance in meters.
    total_time : str
      Total time as string in format 00h00m00s

    """

    activities: list[ActivityEntity] | None = None

    total_distance: int = 0
    total_hours: int = 0
    total_minutes: int = 0
    total_seconds: int = 0

    # values below are calculated from the values above - values above are
    # authoritative i.e. if the value below is inconsistent/wrong, then it is
    # recalculated using values above

    warm_up: list[ActivityEntity] | None = None
    cool_down: list[ActivityEntity] | None = None

    total_duration: str = ""  # 00h00m00s
    total_duration_seconds: int = 0


# activity types that typically record distance
_DISTANCE_ACTIVITY_TYPES: set[str] = {
    "run",
    "ride",
    "row",
    "swim",
    "walk",
    "ski",
    "rollerski",
    "xcski",
    "inline",
    "ice",
    "paddle",
    "kayak",
    "canoe",
    "hike",
    "trek",
    "mtb",
    "cx",
    "elliptical",
    "treadmill",
}


# severity levels for activity validation
SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


def validate_activity(entity: ActivityEntity) -> list[tuple[str, str]]:
    """Check an activity for data problems and return a list of (description, severity).

    Severity levels:
    - ``"error"``: Internal inconsistency or impossible value (e.g. avg > max).
    - ``"warning"``: Suspicious but potentially legitimate value (e.g. elite athlete).

    An empty list means the activity is valid with no detected problems.

    Validation checks performed:

    **Errors — internal consistency (average must not exceed maximum):**
    - ``avg_cadence > max_cadence`` when both are non-zero
    - ``avg_hr > max_hr`` when both are non-zero
    - ``avg_watts > max_watts`` when both are non-zero
    - ``avg_speed > max_speed`` when both are non-zero
    - ``elevation_min > elevation_max`` when both are non-zero

    **Errors — zero-value anomalies (one field set, related field missing):**
    - ``distance > 0`` but ``duration_seconds == 0`` (no time recorded)
    - ``duration_seconds > 0`` but ``distance == 0`` for distance-based activity types

    **Warnings — out-of-range values (suspiciously high or low):**
    - ``distance > 500 000 m`` (500 km in a single activity)
    - ``duration_seconds > 172 800 s`` (48 hours)
    - ``max_speed > 100 km/h`` (suspicious for any human-powered activity)
    - ``avg_speed`` outside reasonable range for the activity type:
      - run 3-25 km/h
      - ride/mtb/cx 5-70 km/h
      - row/paddle/kayak/canoe 2-20 km/h
      - swim 1-8 km/h
      - walk/hike/trek 1-12 km/h
      - ski/rollerski/xcski/inline/ice 3-50 km/h
    - ``avg_cadence > 250 rpm`` or ``max_cadence > 300 rpm``
    - ``avg_hr > 230 bpm`` or ``max_hr > 240 bpm``
    - ``min_hr < 25 bpm`` or ``min_hr > 120 bpm`` (resting HR range)
    - ``kcal`` burn rate ``> 2000 kcal/h``
    - ``elevation_gain / (distance_km) > 150 m/km`` (implausibly steep)
    - ``avg_watts > 2500 W`` or ``max_watts > 3000 W``
    - ``temperature < -70 C`` or ``temperature > 70 C``
    - ``weight < 20 kg`` or ``weight > 300 kg``

    Parameters
    ----------
    entity : ActivityEntity
        The activity to validate. Should already have transient fields
        (duration_seconds, avg_speed, pace, etc.) computed via
        ``evaluate_activity()``.

    Returns
    -------
    list[tuple[str, str]]
        List of (description, severity) tuples. Severity is ``"error"`` or
        ``"warning"``. Empty if no problems found.
    """
    problems: list[tuple[str, str]] = []

    # -- internal consistency: average must not exceed maximum --

    if entity.avg_cadence > 0 and entity.max_cadence > 0:
        if entity.avg_cadence > entity.max_cadence:
            problems.append(
                (
                    f"Avg cadence ({entity.avg_cadence:.0f} rpm) > "
                    f"max cadence ({entity.max_cadence:.0f} rpm)",
                    SEVERITY_ERROR,
                )
            )

    if entity.avg_hr > 0 and entity.max_hr > 0:
        if entity.avg_hr > entity.max_hr:
            problems.append(
                (
                    f"Avg HR ({entity.avg_hr:.0f} bpm) > "
                    f"max HR ({entity.max_hr:.0f} bpm)",
                    SEVERITY_ERROR,
                )
            )

    if entity.avg_watts > 0 and entity.max_watts > 0:
        if entity.avg_watts > entity.max_watts:
            problems.append(
                (
                    f"Avg power ({entity.avg_watts:.0f} W) > "
                    f"max power ({entity.max_watts:.0f} W)",
                    SEVERITY_ERROR,
                )
            )

    if entity.avg_speed > 0 and entity.max_speed > 0:
        if entity.avg_speed > entity.max_speed:
            problems.append(
                (
                    f"Avg speed ({entity.avg_speed:.1f} km/h) > "
                    f"max speed ({entity.max_speed:.1f} km/h)",
                    SEVERITY_ERROR,
                )
            )

    if entity.elevation_min > 0 and entity.elevation_max > 0:
        if entity.elevation_min > entity.elevation_max:
            problems.append(
                (
                    f"Min elevation ({entity.elevation_min} m) > "
                    f"max elevation ({entity.elevation_max} m)",
                    SEVERITY_ERROR,
                )
            )

    # -- zero-value anomalies --

    if entity.distance > 0 and entity.duration_seconds == 0:
        problems.append(
            (
                f"Distance {entity.distance} m recorded but duration is zero",
                SEVERITY_ERROR,
            )
        )

    at = entity.activity_type_key
    if entity.duration_seconds > 0 and entity.distance == 0:
        if at in _DISTANCE_ACTIVITY_TYPES:
            problems.append(
                (
                    f"Duration {entity.duration} recorded but distance is zero "
                    f"({at} activity)",
                    SEVERITY_ERROR,
                )
            )

    # -- out-of-range values --

    if entity.distance > 500_000:
        problems.append(
            (
                f"Distance {entity.distance} m ({entity.distance / 1000:.0f} km) "
                f"is suspiciously large",
                SEVERITY_WARNING,
            )
        )

    if entity.duration_seconds > 172_800:
        problems.append(
            (
                f"Duration {entity.duration} ({entity.duration_seconds / 3600:.0f} h) "
                f"is suspiciously long (> 48 h)",
                SEVERITY_WARNING,
            )
        )

    if entity.max_speed > 100:
        problems.append(
            (
                f"Max speed {entity.max_speed:.1f} km/h is suspiciously high",
                SEVERITY_WARNING,
            )
        )

    # speed ranges by activity type
    if entity.avg_speed > 0:
        if at == "run":
            if entity.avg_speed > 25:
                problems.append(
                    (
                        f"Avg speed {entity.avg_speed:.1f} km/h is too high "
                        f"for running",
                        SEVERITY_WARNING,
                    )
                )
            elif entity.avg_speed < 3 and entity.distance > 1000:
                problems.append(
                    (
                        f"Avg speed {entity.avg_speed:.1f} km/h "
                        f"({entity.pace} min/km) is too slow for running",
                        SEVERITY_WARNING,
                    )
                )
        elif at in ("ride", "mtb", "cx"):
            if entity.avg_speed > 70:
                problems.append(
                    (
                        f"Avg speed {entity.avg_speed:.1f} km/h is too high "
                        f"for cycling",
                        SEVERITY_WARNING,
                    )
                )
            elif entity.avg_speed < 5 and entity.distance > 1000:
                problems.append(
                    (
                        f"Avg speed {entity.avg_speed:.1f} km/h is too slow "
                        f"for cycling",
                        SEVERITY_WARNING,
                    )
                )
        elif at in ("row", "paddle", "kayak", "canoe"):
            if entity.avg_speed > 20:
                problems.append(
                    (
                        f"Avg speed {entity.avg_speed:.1f} km/h is too high for {at}",
                        SEVERITY_WARNING,
                    )
                )
        elif at == "swim":
            if entity.avg_speed > 8:
                problems.append(
                    (
                        f"Avg speed {entity.avg_speed:.1f} km/h is too high "
                        f"for swimming",
                        SEVERITY_WARNING,
                    )
                )
        elif at in ("walk", "hike", "trek"):
            if entity.avg_speed > 12:
                problems.append(
                    (
                        f"Avg speed {entity.avg_speed:.1f} km/h is too high "
                        f"for walking",
                        SEVERITY_WARNING,
                    )
                )
            elif entity.avg_speed < 1 and entity.distance > 500:
                problems.append(
                    (
                        f"Avg speed {entity.avg_speed:.1f} km/h is too slow "
                        f"for walking",
                        SEVERITY_WARNING,
                    )
                )
        elif at in (
            "ski",
            "rollerski",
            "xcski",
            "inline",
            "ice",
        ):
            if entity.avg_speed > 50:
                problems.append(
                    (
                        f"Avg speed {entity.avg_speed:.1f} km/h is too high for {at}",
                        SEVERITY_WARNING,
                    )
                )

    # cadence ranges
    if entity.avg_cadence > 250:
        problems.append(
            (
                f"Avg cadence {entity.avg_cadence:.0f} rpm is suspiciously high",
                SEVERITY_WARNING,
            )
        )
    if entity.max_cadence > 300:
        problems.append(
            (
                f"Max cadence {entity.max_cadence:.0f} rpm is suspiciously high",
                SEVERITY_WARNING,
            )
        )

    # HR ranges
    if entity.avg_hr > 230:
        problems.append(
            (
                f"Avg HR {entity.avg_hr:.0f} bpm is suspiciously high",
                SEVERITY_WARNING,
            )
        )
    if entity.max_hr > 240:
        problems.append(
            (
                f"Max HR {entity.max_hr:.0f} bpm is suspiciously high",
                SEVERITY_WARNING,
            )
        )
    if entity.min_hr > 0:
        if entity.min_hr < 25:
            problems.append(
                (
                    f"Resting HR {entity.min_hr:.0f} bpm is suspiciously low",
                    SEVERITY_WARNING,
                )
            )
        elif entity.min_hr > 120:
            problems.append(
                (
                    f"Resting HR {entity.min_hr:.0f} bpm is suspiciously high",
                    SEVERITY_WARNING,
                )
            )

    # kcal burn rate
    if entity.kcal > 0 and entity.duration_seconds > 0:
        kcal_per_hour = entity.kcal / (entity.duration_seconds / 3600)
        if kcal_per_hour > 2000:
            problems.append(
                (
                    f"Calorie burn rate {kcal_per_hour:.0f} kcal/h "
                    f"is suspiciously high",
                    SEVERITY_WARNING,
                )
            )

    # elevation gain per km
    if entity.elevation_gain > 0 and entity.distance > 0:
        elev_per_km = entity.elevation_gain / (entity.distance / 1000)
        if elev_per_km > 150:
            problems.append(
                (
                    f"Elevation gain {entity.elevation_gain} m over "
                    f"{entity.distance / 1000:.1f} km "
                    f"({elev_per_km:.0f} m/km) is implausibly steep",
                    SEVERITY_WARNING,
                )
            )

    # power ranges
    if entity.avg_watts > 2500:
        problems.append(
            (
                f"Avg power {entity.avg_watts:.0f} W is suspiciously high",
                SEVERITY_WARNING,
            )
        )
    if entity.max_watts > 3000:
        problems.append(
            (
                f"Max power {entity.max_watts:.0f} W is suspiciously high",
                SEVERITY_WARNING,
            )
        )

    # temperature range
    if entity.temperature < -70:
        problems.append(
            (
                f"Temperature {entity.temperature} C is suspiciously low",
                SEVERITY_WARNING,
            )
        )
    elif entity.temperature > 70:
        problems.append(
            (
                f"Temperature {entity.temperature} C is suspiciously high",
                SEVERITY_WARNING,
            )
        )

    # weight range
    if entity.weight > 0:
        if entity.weight < 20:
            problems.append(
                (
                    f"Weight {entity.weight:.1f} kg is suspiciously low",
                    SEVERITY_WARNING,
                )
            )
        elif entity.weight > 300:
            problems.append(
                (
                    f"Weight {entity.weight:.1f} kg is suspiciously high",
                    SEVERITY_WARNING,
                )
            )

    return problems
