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

    meta_activity_type: str = ""  # meta activity type: commons::AT_TAXONOMY

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

    avg_cadence: int = 0  # revolutions/strokes per minute
    max_cadence: int = 0

    avg_hr: int = 0
    max_hr: int = 0
    min_hr: int = 0  # resting HR (like weight) - not related to activity, but day

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

    entity.duration = f"{entity.hours:02}h{entity.minutes:02}m{entity.seconds:02}s"

    entity.duration_seconds = (
        entity.hours * 3_600 + entity.minutes * 60 + entity.seconds
    )

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
