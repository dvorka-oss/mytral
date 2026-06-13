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

"""Random attach w/ synthetic data generator excels at:

* Functional validation:
  do features, data model fields, ... make sense?
* Performance and load testing:
  How does the system perform w/ large datasets?
* Demos on anonymized datasets::
  Showcasing application w/o sharing (potentially) sensitive real data.

This module brings ability to:

- Generate synthetic anonymized MyTraL datasets.

"""

import datetime
import io
import math
import os
import pathlib
import random
import uuid

import polars
import pytest

from mytral import blobstore as blobstore_pkg
from mytral import cals
from mytral import commons
from mytral import config
from mytral import settings
from mytral.backends import dataset_json
from mytral.backends import entities
from mytral.blobstore import activity_service as blob_svc_module
from tests import _given

UNSET_DATE = "YYYY-MM-DD"


def _attack_activity_types(
    max_activity_types: int, user_id: str, u_ds: dataset_json.JsonUsersDataset
) -> tuple[dict, list]:
    """Generate random custom activity types."""
    activity_types_dict: dict[str, settings.ActivityType] = {}

    for _ in range(max_activity_types):
        c_at = u_ds.create_activity_type(
            user_id=user_id,
            activity_type=settings.ActivityType(
                name=config.MytralConfig.gen_takenoko(syllables=6),
                is_distance=random.choice([True, False]),
                is_exercise=random.choice([True, False]),
                is_regen=random.choice([True, False]),
                emoji=random.choice(["🏃", "🚴", "🏊", "🏋️", "🧘", "🎿", "⛷️", "🏂"]),
                color=random.choice(
                    ["red", "blue", "green", "yellow", "orange", "purple", "pink"]
                ),
            ),
        )
        activity_types_dict[c_at.key] = c_at

    activity_types_keys = list(activity_types_dict.keys())
    return activity_types_dict, activity_types_keys


def _attack_exercises(
    max_exercises: int, user_id: str, u_ds: dataset_json.JsonUsersDataset
) -> tuple[dict, list]:
    """Generate random custom exercises."""
    exercises_dict: dict[str, settings.Exercise] = {}

    for _ in range(max_exercises):
        c_ex = u_ds.create_exercise(
            user_id=user_id,
            exercise=settings.Exercise(
                name=config.MytralConfig.gen_takenoko(syllables=6),
                description=_given.given_markdown_ipsum(),
                weight=random.uniform(0.0, 300.0),
                tags=[
                    config.MytralConfig.gen_takenoko(syllables=3)
                    for _ in range(random.randint(0, 3))
                ],
            ),
        )
        exercises_dict[c_ex.key] = c_ex

    exercises_keys = list(exercises_dict.keys())
    return exercises_dict, exercises_keys


def _attack_gear_components(max_gear_components: int) -> list[dict]:
    """Generate random gear components."""
    # components are part of gear, not standalone
    components = []
    for _ in range(random.randint(0, max_gear_components)):
        year = random.randint(2020, 2026)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        installed = f"{year}-{month:02d}-{day:02d}"
        service_year = random.randint(2020, 2026)
        service_month = random.randint(1, 12)
        service_day = random.randint(1, 28)
        service = f"{service_year}-{service_month:02d}-{service_day:02d}"
        components.append(
            settings.GearComponent(
                name=config.MytralConfig.gen_takenoko(syllables=4),
                cost=random.uniform(0.0, 500.0),
                installed_date=installed,
                last_service_date=service,
                notes=_given.given_markdown_ipsum(),
            ).to_dict()
        )
    return components


def _attack_gears(
    max_gears: int,
    max_gear_components: int,
    user_id: str,
    u_ds: dataset_json.JsonUsersDataset,
    a_types_keys: list[str],
    dataset_name: str,
) -> tuple[dict, list]:
    """Generate random gears."""
    gears_dict: dict[str, settings.Gear] = {}

    for _ in range(max_gears):
        year = random.randint(2018, 2026)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        purchased = f"{year}-{month:02d}-{day:02d}"
        c_gear = u_ds.create_gear(
            user_id=user_id,
            dataset_name=dataset_name,
            gear=settings.Gear(
                activity_type_key=random.choice(a_types_keys),
                name=config.MytralConfig.gen_takenoko(syllables=6),
                vendor=config.MytralConfig.gen_takenoko(syllables=5),
                model=config.MytralConfig.gen_takenoko(syllables=7),
                size=random.choice(["S", "M", "L", "XL", "42", "43", "44", "45"]),
                comment=_given.given_markdown_ipsum(),
                is_default=random.choice([True, False]),
                retired=random.choice([True, False]),
                tcoo_base=random.uniform(50.0, 5000.0),
                purchased=purchased,
                components=_attack_gear_components(
                    max_gear_components=max_gear_components
                ),
            ),
        )
        gears_dict[c_gear.key] = c_gear

    gears_keys = list(gears_dict.keys())
    return gears_dict, gears_keys


def _attack_goals(
    max_goals: int,
    user_id: str,
    u_ds: dataset_json.JsonUsersDataset,
    a_types_keys: list[str],
) -> tuple[dict, list]:
    """Generate random goals."""
    goals_dict: dict[str, settings.Goal] = {}

    for _ in range(max_goals):
        c_goal = u_ds.create_goal(
            user_id=user_id,
            goal=settings.Goal(
                name=config.MytralConfig.gen_takenoko(syllables=8),
                activity_type=random.choice(a_types_keys),
                description=_given.given_markdown_ipsum(),
                tag=config.MytralConfig.gen_takenoko(syllables=4),
                done=random.choice([True, False]),
                urgency=random.uniform(0.0, 1.0),
                importance=random.uniform(0.0, 1.0),
            ),
        )
        goals_dict[c_goal.key] = c_goal

    goals_keys = list(goals_dict.keys())
    return goals_dict, goals_keys


def _attack_outfits(
    max_outfits: int,
    user_id: str,
    u_ds: dataset_json.JsonUsersDataset,
    a_types_keys: list[str],
) -> tuple[dict, list]:
    outfits_dict: dict[str, settings.Outfit] = {}

    for i in range(max_outfits):
        c_o = u_ds.create_outfit(
            user_id=user_id,
            outfit=settings.Outfit(
                name=config.MytralConfig.gen_takenoko(syllables=8),
                activity_type=random.choice(a_types_keys),
                description=_given.given_markdown_ipsum(),
            ),
        )
        outfits_dict[c_o.key] = c_o

    outfits_keys = list(outfits_dict.keys())

    return outfits_dict, outfits_keys


def _attack_laps(
    max_laps: int, user_id: str, u_ds: dataset_json.JsonUsersDataset
) -> tuple[dict, list]:
    """Generate random custom lap types."""
    laps_dict: dict[str, settings.Lap] = {}

    lap_names = [
        "warmup",
        "interval",
        "fast",
        "rest",
        "cooldown",
        "tempo",
        "easy",
        "hard",
        "recovery",
        "sprint",
        "threshold",
        "endurance",
    ]

    for _ in range(max_laps):
        # randomly choose distance-based or duration-based lap
        if random.choice([True, False]):
            # distance-based lap
            c_lap = u_ds.create_lap(
                user_id=user_id,
                lap=settings.Lap(
                    name=f"{random.choice(lap_names)} {random.randint(100, 5000)}m",
                    description=_given.given_markdown_ipsum(),
                    default_distance=random.randint(100, 5000),  # 100m to 5km
                    default_duration=0,
                ),
            )
        else:
            # duration-based lap
            duration = random.randint(30, 1800)  # 30s to 30min
            minutes = duration // 60
            seconds = duration % 60
            c_lap = u_ds.create_lap(
                user_id=user_id,
                lap=settings.Lap(
                    name=f"{random.choice(lap_names)} {minutes}'{seconds:02d}\"",
                    description=_given.given_markdown_ipsum(),
                    default_distance=0,
                    default_duration=duration,
                ),
            )
        laps_dict[c_lap.key] = c_lap

    laps_keys = list(laps_dict.keys())
    return laps_dict, laps_keys


def _attack_symptoms(
    max_symptoms: int, user_id: str, u_ds: dataset_json.JsonUsersDataset
) -> tuple[dict, list]:
    """Generate random symptoms."""
    symptoms_dict: dict[str, settings.Symptom] = {}

    for _ in range(max_symptoms):
        c_symptom = u_ds.create_symptom(
            user_id=user_id,
            symptom=settings.Symptom(
                name=config.MytralConfig.gen_takenoko(syllables=6),
                body_parts=[
                    config.MytralConfig.gen_takenoko(syllables=3)
                    for _ in range(random.randint(0, 3))
                ],
            ),
        )
        symptoms_dict[c_symptom.key] = c_symptom

    symptoms_keys = list(symptoms_dict.keys())
    return symptoms_dict, symptoms_keys


def _generate_laps(
    activity_key: str,
    laps_dict: dict[str, settings.Lap],
    laps_keys: list[str],
) -> list[entities.LapEntity]:
    """Generate random lap entities for an activity using persisted lap types.

    Parameters
    ----------
    activity_key : str
        The activity key to associate laps with.
    laps_dict : dict[str, settings.Lap]
        Dictionary of available lap types by key.
    laps_keys : list[str]
        List of lap type keys.

    Returns
    -------
    list[entities.LapEntity]
        List of generated lap entities.

    """
    # 30% chance of no laps
    if random.randint(0, 9) < 3:
        return []

    # generate 1-8 laps
    num_laps = random.randint(1, 8)
    lap_entities = []

    for i in range(num_laps):
        # pick a random lap type from persisted laps
        lap_key = random.choice(laps_keys)
        lap_type = laps_dict[lap_key]

        lap_entities.append(
            entities.LapEntity(
                activity_key=activity_key,
                order=i + 1,
                name=lap_type.name,
                # use defaults from lap type, or override with random values
                distance=lap_type.default_distance
                if lap_type.default_distance > 0
                else random.randint(100, 5000),
                duration=lap_type.default_duration
                if lap_type.default_duration > 0
                else random.randint(30, 1800),
                comment=_given.given_lorem_ipsum()
                if random.choice([True, False])
                else "",
                ranked=random.choice([True, False]),
            )
        )

    return lap_entities


def _pregenerate_parquets(
    recording_dir: pathlib.Path, tmp_path: pathlib.Path
) -> dict[str, list[tuple[pathlib.Path, bytes]]]:
    """Pre-generate parquets for a few sample files to speed up tests."""
    from mytral.integrations import polar_hrm
    from mytral.recordings import parquet_converter

    samples: dict[str, list[tuple[pathlib.Path, bytes]]] = {
        ".fit": [],
        ".gpx": [],
        ".hrm": [],
    }

    if not recording_dir.exists():
        return samples

    for ext in samples.keys():
        files = list(recording_dir.glob(f"**/*{ext}")) + list(
            recording_dir.glob(f"**/*{ext.upper()}")
        )
        if not files:
            continue

        # take up to 3 samples for each type
        selected = random.sample(files, k=min(3, len(files)))
        for f_path in selected:
            try:
                with open(f_path, "rb") as f:
                    data = f.read()

                if ext == ".fit":
                    p_bytes = parquet_converter.fit_to_parquet(data)
                elif ext == ".gpx":
                    p_bytes = parquet_converter.gpx_to_parquet(data)
                elif ext == ".hrm":
                    hrm_dict = polar_hrm.parse_hrm(data.decode("utf-8", "ignore"))
                    p_bytes = parquet_converter.hrm_to_parquet(hrm_dict)
                else:
                    continue

                # store parquet to tmp_path for the test
                p_name = f"{f_path.stem}.parquet"
                p_path = tmp_path / p_name
                with open(p_path, "wb") as f_p:
                    f_p.write(p_bytes)

                samples[ext].append((f_path, p_bytes))
            except Exception as exc:
                print(f"Failed to pre-generate parquet for {f_path}: {exc}")

    return samples


def _generate_synthetic_power_values(
    sample_count: int,
    profile: str,
) -> list[float]:
    """Generate deterministic synthetic power values in watts.

    Parameters
    ----------
    sample_count : int
        Number of power samples to generate.
    profile : str
        Profile name: ``steady`` | ``threshold`` | ``vo2`` | ``sprint``.

    Returns
    -------
    list[float]
        Power values in watts.

    """
    if sample_count <= 0:
        return []

    power_values: list[float] = []
    for idx in range(sample_count):
        if profile == "steady":
            base = 200.0
            wave = 18.0 * math.sin(idx / 45.0)
            surge = 22.0 if idx % 300 < 18 else 0.0
            power = base + wave + surge
        elif profile == "threshold":
            block = (idx // 180) % 2
            power = 285.0 if block == 0 else 165.0
            power += 12.0 * math.sin(idx / 20.0)
        elif profile == "vo2":
            block = (idx // 75) % 2
            power = 360.0 if block == 0 else 150.0
            power += 10.0 * math.sin(idx / 10.0)
        else:  # sprint
            phase = idx % 120
            if phase < 12:
                power = 700.0 - (phase * 15.0)
            elif phase < 35:
                power = 280.0
            else:
                power = 140.0
            power += 8.0 * math.sin(idx / 7.0)

        power_values.append(max(60.0, min(1200.0, power)))

    return power_values


def _synthesize_power_parquet(
    parquet_bytes: bytes,
    profile: str,
) -> bytes:
    """Overwrite parquet power channel with synthetic high-quality watts."""
    df = polars.read_parquet(io.BytesIO(parquet_bytes))
    if df.height == 0:
        return parquet_bytes

    power_values = _generate_synthetic_power_values(
        sample_count=df.height,
        profile=profile,
    )
    df = df.with_columns(
        [
            polars.Series("power", power_values, dtype=polars.Float64),
            polars.Series("has_power", [True] * df.height, dtype=polars.Boolean),
        ]
    )

    parquet_stream = io.BytesIO()
    df.write_parquet(parquet_stream)
    return parquet_stream.getvalue()


def _augment_parquet_samples_with_watts(
    parquet_samples: dict[str, list[tuple[pathlib.Path, bytes]]],
) -> dict[str, list[tuple[pathlib.Path, bytes]]]:
    """Create synthetic watts variants for each pre-generated parquet sample."""
    profiles = ["steady", "threshold", "vo2", "sprint"]
    synthetic_samples: dict[str, list[tuple[pathlib.Path, bytes]]] = {
        ext: list(samples) for ext, samples in parquet_samples.items()
    }

    for ext, samples in parquet_samples.items():
        for sample_index, (recording_path, parquet_bytes) in enumerate(samples):
            profile = profiles[sample_index % len(profiles)]
            synthetic_parquet = _synthesize_power_parquet(
                parquet_bytes=parquet_bytes,
                profile=profile,
            )
            synthetic_samples[ext].append((recording_path, synthetic_parquet))

    return synthetic_samples


# TODO add dataset ZOO as default, w/ callback to data
@pytest.mark.skipif(
    os.getenv("MYTRAL_TEST_RANDOM_ATTACK", "").lower() != "true",
    reason=(
        "Set MYTRAL_TEST_RANDOM_ATTACK=true to run random-attack dataset generation."
    ),
)
@pytest.mark.mytral
@pytest.mark.tool
@pytest.mark.parametrize(
    "attack_config",
    [
        pytest.param(
            {
                "user_display_name": "Random Attack",
                "user_name": "random",
                "user_password": "attack",
                "from_date": "2026-05-01",
                "to_date": UNSET_DATE,
                "max_activities": 100,
                "max_activity_types": 10,
                "max_exercises": 10,
                "max_gear_components": 10,
                "max_gears": 10,
                "max_goals": 10,
                "max_laps": 10,
                "max_outfits": 10,
                "max_symptoms": 10,
                "recording_attach_probability": 0.30,
            },
            id="current-settings",
        ),
        pytest.param(
            {
                "user_display_name": "Random Attack Watts",
                "user_name": "random",
                "user_password": "attack",
                "from_date": "2024-01-01",
                "to_date": UNSET_DATE,
                "max_activities": 300,
                "max_activity_types": 15,
                "max_exercises": 10,
                "max_gear_components": 10,
                "max_gears": 10,
                "max_goals": 10,
                "max_laps": 10,
                "max_outfits": 10,
                "max_symptoms": 10,
                "recording_attach_probability": 0.85,
            },
            id="watts-heavy",
        ),
    ],
)
def test_generate_mytral_dataset(
    tmp_path: pathlib.Path,
    attack_config: dict,
):
    """Generate synthetic anonymized MyTral dataset."""

    user_id = str(uuid.uuid4())
    user_display_name = attack_config["user_display_name"]
    user_name = attack_config["user_name"]
    user_password = attack_config["user_password"]
    from_date = attack_config["from_date"]
    to_date = attack_config["to_date"]
    max_activities = attack_config["max_activities"]
    max_activity_types = attack_config["max_activity_types"]
    max_exercises = attack_config["max_exercises"]
    max_gear_components = attack_config["max_gear_components"]
    max_gears = attack_config["max_gears"]
    max_goals = attack_config["max_goals"]
    max_laps = attack_config["max_laps"]
    max_outfits = attack_config["max_outfits"]
    max_symptoms = attack_config["max_symptoms"]
    recording_attach_probability = float(attack_config["recording_attach_probability"])

    watts_mode = os.getenv("MYTRAL_RANDOM_ATTACK_WATTS", "").lower() == "true"
    if watts_mode:
        recording_attach_probability = 0.85

    #
    # GIVEN
    #

    app_config = config.MytralConfig(persistence_data_dir=tmp_path)

    _, u_ds, user_profile = _given.given_test(
        test_config=app_config,
        user_id=user_id,
        user_name=user_name,
        user_display_name=user_display_name,
        user_password=user_password,
    )

    blobstore = blobstore_pkg.create_blobstore(app_config)
    blob_svc = blob_svc_module.ActivityBlobService(
        store=blobstore,
        dataset=u_ds,
        config=app_config,
    )

    # pre-generate parquets to avoid re-encoding
    recording_dir = pathlib.Path(__file__).parent / "data" / "import"
    parquet_samples = _pregenerate_parquets(recording_dir, tmp_path)
    if watts_mode:
        parquet_samples = _augment_parquet_samples_with_watts(parquet_samples)

    #
    # WHEN
    #

    a_dict: dict[str, entities.ActivityEntity] = {}

    # FIRST create profile entities, THEN activities to interlink all the deps

    a_types_dict = u_ds.list_activity_types(
        user_id=user_id,
    ).activity_types_by_key
    a_types_keys = list(a_types_dict.keys())

    # add custom activity types
    (_, custom_a_types_keys) = _attack_activity_types(
        max_activity_types=max_activity_types, user_id=user_id, u_ds=u_ds
    )
    a_types_keys.extend(custom_a_types_keys)

    # add custom exercises
    (_, exercises_keys) = _attack_exercises(
        max_exercises=max_exercises, user_id=user_id, u_ds=u_ds
    )

    # add custom symptoms
    (symptoms_dict, symptoms_keys) = _attack_symptoms(
        max_symptoms=max_symptoms, user_id=user_id, u_ds=u_ds
    )

    # add custom gears
    (_, gears_keys) = _attack_gears(
        max_gears=max_gears,
        max_gear_components=max_gear_components,
        user_id=user_id,
        u_ds=u_ds,
        a_types_keys=a_types_keys,
        dataset_name=user_profile.dataset_name,
    )

    # add custom goals
    (_, _) = _attack_goals(
        max_goals=max_goals, user_id=user_id, u_ds=u_ds, a_types_keys=a_types_keys
    )

    # add outfits
    (_, outfits_keys) = _attack_outfits(
        max_outfits=max_outfits,
        user_id=user_id,
        a_types_keys=a_types_keys,
        u_ds=u_ds,
    )

    # add custom laps - get OOTB laps first, then add custom
    laps_ootb = u_ds.list_laps(user_id=user_id)
    laps_dict = dict(laps_ootb.lap_by_key)  # copy OOTB laps
    laps_keys = list(laps_dict.keys())

    # add custom laps
    (custom_laps_dict, custom_laps_keys) = _attack_laps(
        max_laps=max_laps, user_id=user_id, u_ds=u_ds
    )
    laps_dict.update(custom_laps_dict)
    laps_keys.extend(custom_laps_keys)

    # FROM
    if from_date == UNSET_DATE:
        # 3 years by default
        from_when_year = datetime.date.today().year - 3
        from_when_month = 1
        from_when_day = 1
    else:
        (from_when_year, from_when_month, from_when_day) = from_date.split("-")
    (from_when_year, from_when_month, from_when_day) = (
        int(from_when_year),
        int(from_when_month),
        int(from_when_day),
    )
    (when_year, when_month, when_day) = (
        from_when_year,
        from_when_month,
        from_when_day,
    )

    # TO
    today = datetime.date.today()
    if to_date == UNSET_DATE:
        to_year = today.year
        to_month = today.month
        to_day = today.day
    else:
        (to_year, to_month, to_day) = from_date.split("-")
    (to_year, to_month, to_day) = (
        int(to_year),
        int(to_month),
        int(to_day),
    )

    # ACTIVITIES generation strategy:
    # from: either set or -3 years
    # to  : either set or today
    # from & to > days_from_to
    # a_for_1_day: (total_activities / days_from_to) or 1
    # 10% chance of day w/o activity

    days_from_to = cals.days_between_dates(
        from_date=f"{when_year}-{when_month:02d}-{when_day:02d}",
        to_date=f"{to_year}-{to_month:02d}-{to_day:02d}",
    )
    a_for_1_day = round(float(max_activities) / float(days_from_to))
    a_for_1_day = a_for_1_day or 1

    print(
        f"Generating activities:\n"
        f"  from                : {when_year}-{when_month:02d}-{when_day:02d}\n"
        f"  to                  : {to_year}-{to_month:02d}-{to_day:02d}\n"
        f"  days from-to        : {days_from_to}\n"
        f"  max_activities      : {max_activities}\n"
        f"  activities for 1 day: {a_for_1_day}\n"
        f"  photos              : {_given.TEST_DS_PHOTOS}"
    )

    for i in range(days_from_to):
        print("|", end="")

        # 20% days w/o activity
        if random.randint(0, 4) == 2:
            (when_year, when_month, when_day) = cals.get_tomorrow(
                year=when_year, month=when_month, day=when_day
            )
            continue

        for _ in range(a_for_1_day):
            print(".", end="")
            # pre-generate activity key for lap association
            activity_key = str(uuid.uuid4())
            activity_type_key = random.choice(a_types_keys)

            # activity
            a = u_ds.create_activity(
                user_id=user_id,
                dataset_name=u_ds.profile(user_id).dataset_name,
                entity=entities.ActivityEntity(
                    key=activity_key,
                    name=config.MytralConfig.gen_takenoko(syllables=8),
                    description=_given.given_markdown_ipsum(),
                    when_year=when_year,
                    when_month=when_month,
                    when_day=when_day,
                    when_hour=random.randint(1, 23),
                    when_minute=random.randint(1, 59),
                    when_second=random.randint(1, 59),
                    # when: str ... set by eval
                    sort_code=random.randint(1, 5),
                    workout_sort_code=random.randint(1, 5),
                    where=config.MytralConfig.gen_takenoko(syllables=4),
                    activity_type_key=activity_type_key,
                    intensity=random.choice(commons.INTENSITIES)[0],
                    gears=random.sample(
                        gears_keys, k=min(random.randint(0, 3), len(gears_keys))
                    )
                    if gears_keys
                    else [],
                    outfit=random.choice(outfits_keys) if outfits_keys else "",
                    formula=" ".join(
                        [config.MytralConfig.gen_takenoko() for _ in range(3)]
                    ),
                    exercises=[
                        entities.ExerciseEntity(
                            name=ex_key,  # use key, not name
                            weight=random.uniform(5.0, 150.0),
                            series=random.randint(1, 5),
                            repetitions=random.randint(1, 20),
                            duration=random.randint(30, 300),
                            rest=random.randint(30, 180),
                        )
                        for ex_key in random.sample(
                            exercises_keys,
                            k=min(random.randint(0, 5), len(exercises_keys)),
                        )
                    ]
                    if exercises_keys
                    else [],
                    sickness_symptoms=[
                        entities.SicknessSymptomEntity(
                            symptom=sym_key,  # use key, not name
                            side=random.choice(["", "left", "right"]),
                            body_part=random.choice(
                                symptoms_dict[sym_key].body_parts
                                if symptoms_dict[sym_key].body_parts
                                else [""]
                            ),
                            health=random.randint(0, 100),
                        )
                        for sym_key in random.sample(
                            symptoms_keys,
                            k=min(random.randint(0, 3), len(symptoms_keys)),
                        )
                    ]
                    if symptoms_keys
                    else [],
                    laps=_generate_laps(activity_key, laps_dict, laps_keys)
                    if laps_keys
                    else [],
                    # duration
                    hours=random.randint(1, 24),
                    minutes=random.randint(1, 59),
                    seconds=random.randint(1, 59),
                    distance=random.randint(1, 256_000),
                    warm_up=random.choice([True, False]),
                    cool_down=random.choice([True, False]),
                    commute=random.choice([True, False]),
                    race=random.choice([True, False]),
                    ranked=random.choice([True, False]),
                    kcal=random.randint(100, 12_000),
                    max_speed=random.randint(3, 111),
                    elevation_gain=random.randint(0, 7_000),
                    elevation_min=random.randint(0, 100),
                    elevation_max=random.randint(101, 2_500),
                    avg_watts=random.uniform(0.0, 500.0),
                    max_watts=random.uniform(0.0, 1500.0),
                    avg_hr=random.randint(45, 200),
                    max_hr=random.randint(145, 220),
                    min_hr=random.randint(35, 65),
                    max_cadence=random.randint(1, 5),
                    avg_cadence=random.randint(1, 99),
                    weight=random.uniform(72.5, 105.0),
                    cost=random.uniform(0.0, 100.0),
                    weather=random.choice(commons.WEATHERS)[0],
                    temperature=random.randint(-20, 50),
                    fitness_score=random.uniform(0.0, 100.0),
                    src=config.MytralConfig.gen_takenoko(syllables=8),
                    src_descriptor=config.MytralConfig.gen_takenoko(syllables=4),
                    src_key=str(uuid.uuid4()),
                    src_url=(
                        f"https://{config.MytralConfig.gen_takenoko(syllables=8)}."
                        f"{config.MytralConfig.gen_takenoko(syllables=3)}/"
                        f"{config.MytralConfig.gen_takenoko(syllables=6)}/"
                        f"{random.randint(1, 100)}"
                    ),
                    recorded_blob_keys=[],  # attached below
                    recorded_parquet_keys={},  # attached below
                    photo_blob_keys=[],  # attached below
                    highlight_photo_blob_key="",  # initialized below
                    # statistics are calculated from the input values from above
                    # duration: str ... evaluate() completes that
                    duration_seconds=random.randint(10 * 60, 12 * 60 * 60),
                    exercise_kgs=random.uniform(0.0, 300_000.0)
                    if a_types_dict[activity_type_key].is_exercise
                    else 0.0,
                    # avg_speed: float ... evaluate() will set it
                    # pace: str ...  evaluate() will set it
                    # TODO if WEIGHT, then do bmi: float = 0.0
                    #   TODO to FE get Jinja
                    # TODO if WEIGHT, then do burnt_fat: float ... evaluate
                    #   TODO to FE get Jinja
                    # TODO add transient fields - review code & fix code for transient
                    transient_fields=None,
                ),
            )
            entities.evaluate_activity(
                entity=a,
                user_profile=user_profile,
            )
            a_dict[a.key] = a

            # recording(s) for the activity
            # by default 30% chance of having a recording
            if any(parquet_samples.values()) and (
                random.random() < recording_attach_probability
            ):
                # choose random type from those that have samples
                available_exts = [
                    ext for ext, samples in parquet_samples.items() if samples
                ]
                if available_exts:
                    ext = random.choice(available_exts)
                    recording_path, parquet_bytes = random.choice(parquet_samples[ext])

                    with open(recording_path, "rb") as recording_stream:
                        blob_svc.upload_recording_with_parquet(
                            user_id=user_id,
                            activity_key=a.key,
                            uploaded_file=recording_stream,
                            original_filename=recording_path.name,
                            name=f"Recording for {a.name}",
                            description="Auto-attached by synthetic data generator",
                            parquet_bytes=parquet_bytes,
                        )

                    # align summary power fields when watts mode is enabled
                    if watts_mode:
                        a.avg_watts = random.uniform(180.0, 320.0)
                        a.max_watts = random.uniform(650.0, 1050.0)
                        u_ds.update_activity(
                            user_id=user_id,
                            dataset_name=u_ds.profile(user_id).dataset_name,
                            entity=a,
                        )

                    # pre-compute GPX map metadata so the Feed UI does not block
                    # on first load — see NON_BLOCKING_RANDOM_ATTACK.md
                    recording_blob_uuid = entities.recording_blob_uuid(
                        a.recorded_blob_keys[0]
                    )
                    print(
                        f"        pre-computing GPX map metadata"
                        f" for activity '{a.key}'"
                        f" from recording '{recording_blob_uuid}' ..."
                    )
                    blob_svc.ensure_gpx_map_data(
                        user_id=user_id,
                        activity_key=a.key,
                        blob_key=recording_blob_uuid,
                    )
                    print(
                        f"        DONE pre-computing GPX map metadata"
                        f" for activity '{a.key}'"
                    )

            # photo(s) for the activity
            if _given.TEST_DS_PHOTOS.exists():
                photo_files = (
                    list(_given.TEST_DS_PHOTOS.glob("*.jpg"))
                    + list(_given.TEST_DS_PHOTOS.glob("*.jpeg"))
                    + list(_given.TEST_DS_PHOTOS.glob("*.png"))
                )
                if photo_files and random.randint(0, 2) != 0:
                    photo_path = random.choice(photo_files)
                    with open(photo_path, "rb") as photo_stream:
                        blob_svc.upload_photos(
                            user_id=user_id,
                            activity_key=a.key,
                            uploaded_files=[(photo_stream, photo_path.name)],
                        )

        # TODO increase day based on the cardinality parameters
        (when_year, when_month, when_day) = cals.get_tomorrow(
            year=when_year, month=when_month, day=when_day
        )

    #
    # THEN
    #

    # save generated data for MyTraL app launch automation
    with open("/tmp/mytral-random-attack-data-dir.txt", "w") as myfile:
        myfile.write(str(tmp_path))

    # print generated data path for manual MyTraL app run
    print(
        f"Run & log in as test/test:"
        f"\n  MYTRAL_DATA_DIR={tmp_path} MYTRAL_INCARNATION=DESKTOP "
        f"MYTRAL_AUTO_LOGIN=true "
        f"MYTRAL_ENCRYPTION_KEY="
        f"{os.getenv(config.MytralConfig.ENV_MYTRAL_ENCRYPTION_KEY)} "
        f"make run"
    )
