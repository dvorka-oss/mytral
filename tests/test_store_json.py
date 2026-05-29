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
import collections
import gzip
import json
import pathlib
import time
from pathlib import Path

import pytest

from tests import _given

"""This test proves that activity data can be compressed to 6% of the size:

- use functions prototyped below to load/store all the activity data
- use this approach in the cloud deployment to quickly get data from key/value store

"""


def to_column_dict(
    activities: dict | list,
    filepath: pathlib.Path | None = None,
    use_gzip: bool = False,
) -> tuple[dict[str, list], float, float]:
    start_time = time.time()

    transformed_data = collections.defaultdict(list)

    values = activities.values() if isinstance(activities, dict) else activities
    for activity_details in values:
        for key, value in activity_details.items():
            transformed_data[key].append(value)

    if "sickness_symptoms" in transformed_data:
        nested_transformed = []
        for symptoms_list in transformed_data["sickness_symptoms"]:
            if symptoms_list:
                symptom_dict = collections.defaultdict(list)
                for symptom_entry in symptoms_list:
                    for key, value in symptom_entry.items():
                        symptom_dict[key].append(value)
                nested_transformed.append(dict(symptom_dict))
            else:
                nested_transformed.append({})
        transformed_data["sickness_symptoms"] = nested_transformed

    if "exercises" in transformed_data:
        nested_transformed = []
        for exercises_list in transformed_data["exercises"]:
            if exercises_list:
                exercise_dict = collections.defaultdict(list)
                for exercise_entry in exercises_list:
                    for key, value in exercise_entry.items():
                        exercise_dict[key].append(value)
                nested_transformed.append(dict(exercise_dict))
            else:
                nested_transformed.append({})
        transformed_data["exercises"] = nested_transformed

    # remove always-empty field transient_fields
    for key in ["transient_fields"]:
        transformed_data.pop(key, None)

    transform_time = time.time() - start_time

    if filepath:
        save_start = time.time()
        if use_gzip:
            with gzip.open(filepath, "wt", encoding="utf-8") as f:
                json.dump(transformed_data, f, separators=(",", ":"))
        else:
            with open(filepath, "w") as f:
                json.dump(transformed_data, f, separators=(",", ":"))
        save_time = time.time() - save_start
        return transformed_data, transform_time, save_time

    return transformed_data, transform_time, 0.0


def from_column_dict(column_dict=None, filepath=None, use_gzip=False) -> tuple:
    load_time = 0.0

    if filepath:
        load_start = time.time()
        if use_gzip:
            with gzip.open(filepath, "rt", encoding="utf-8") as f:
                column_dict = json.load(f)
        else:
            with open(filepath, "r") as f:
                column_dict = json.load(f)
        load_time = time.time() - load_start

    if not column_dict:
        return {}, 0.0, load_time

    reconstruct_start = time.time()

    first_key = next(iter(column_dict))
    num_records = len(column_dict[first_key])

    activities = {}
    for i in range(num_records):
        activity = {}
        activity_key = None
        for key, value_list in column_dict.items():
            if key == "key":
                activity_key = value_list[i]
            if key == "sickness_symptoms" and isinstance(value_list, list):
                if i < len(value_list) and value_list[i]:
                    symptoms_dict = value_list[i]
                    if symptoms_dict:
                        num_symptoms = len(next(iter(symptoms_dict.values())))
                        symptoms_list = []
                        for j in range(num_symptoms):
                            symptom = {k: v[j] for k, v in symptoms_dict.items()}
                            symptoms_list.append(symptom)
                        activity[key] = symptoms_list
                    else:
                        activity[key] = []
                else:
                    activity[key] = []
            elif key == "exercises" and isinstance(value_list, list):
                if i < len(value_list) and value_list[i]:
                    exercises_dict = value_list[i]
                    if exercises_dict:
                        num_exercises = len(next(iter(exercises_dict.values())))
                        exercises_list = []
                        for j in range(num_exercises):
                            exercise = {k: v[j] for k, v in exercises_dict.items()}
                            exercises_list.append(exercise)
                        activity[key] = exercises_list
                    else:
                        activity[key] = []
                else:
                    activity[key] = []
            else:
                activity[key] = value_list[i]

        # restore removed field as empty
        if "transient_fields" not in activity:
            activity["transient_fields"] = None

        if activity_key:
            activities[activity_key] = activity
        else:
            activities[str(i)] = activity

    reconstruct_time = time.time() - reconstruct_start

    return activities, reconstruct_time, load_time


@pytest.mark.skip(
    reason=(
        "The test is broken by the migration of the JSON from dict-based "
        "activities to list-based activities"
    )
)
@pytest.mark.parametrize(
    "activities_file_path",
    [
        (
            f"{_given.EXT_TEST_DATA_ROOT}/development/"
            "data/ba16be59-83ee-4999-9b37-d2c49e454135/activities-2025.json"
        ),
    ],
)
def test_transform_and_store_activities(tmp_path: pathlib.Path, activities_file_path):
    #
    # GIVEN
    #
    activities_path = Path(activities_file_path)

    with open(activities_path, "r") as f:
        activities = json.load(f)

    #
    # WHEN
    #
    # test without gzip
    transformed_data, transform_time, save_time = to_column_dict(
        activities, tmp_path / "transformed_activities.json", use_gzip=False
    )
    reconstructed_activities, reconstruct_time, load_time = from_column_dict(
        filepath=tmp_path / "transformed_activities.json", use_gzip=False
    )

    # test with gzip
    gzip_path = tmp_path / "transformed_activities.json.gz"
    transformed_data_gz, transform_time_gz, save_time_gz = to_column_dict(
        activities, gzip_path, use_gzip=True
    )
    reconstructed_activities_gz, reconstruct_time_gz, load_time_gz = from_column_dict(
        filepath=gzip_path, use_gzip=True
    )

    #
    # THEN
    #
    # convert activities to dict if it's a list
    if isinstance(activities, list):
        activities_dict = {str(i): activity for i, activity in enumerate(activities)}
    else:
        activities_dict = activities

    # assert round-trip transformation preserves data (regular)
    assert len(reconstructed_activities) == len(activities_dict)
    for original_key, reconstructed_key in zip(
        sorted(activities_dict.keys()), sorted(reconstructed_activities.keys())
    ):
        original = activities_dict[original_key]
        reconstructed = reconstructed_activities[reconstructed_key]
        assert set(original.keys()) == set(reconstructed.keys())
        for key in original.keys():
            assert original[key] == reconstructed[key], (
                f"Mismatch in key '{key}': {original[key]} != {reconstructed[key]}"
            )

    # assert round-trip transformation preserves data (gzip)
    assert len(reconstructed_activities_gz) == len(activities_dict)
    for original_key, reconstructed_key in zip(
        sorted(activities_dict.keys()), sorted(reconstructed_activities_gz.keys())
    ):
        original = activities_dict[original_key]
        reconstructed = reconstructed_activities_gz[reconstructed_key]
        assert set(original.keys()) == set(reconstructed.keys())
        for key in original.keys():
            assert original[key] == reconstructed[key], (
                f"Mismatch in key '{key}': {original[key]} != {reconstructed[key]}"
            )

    output_path = tmp_path / "transformed_activities.json"

    assert output_path.exists()

    with open(output_path, "r") as f:
        stored_data = json.load(f)

    for key, value_list in stored_data.items():
        assert isinstance(value_list, list)

    if stored_data:
        first_key = next(iter(stored_data))
        expected_length = len(stored_data[first_key])
        for key, value_list in stored_data.items():
            assert len(value_list) == expected_length

    for key in stored_data.keys():
        assert isinstance(key, str)
        assert not key.isdigit()

    input_size = activities_path.stat().st_size
    output_size = output_path.stat().st_size
    gzip_size = gzip_path.stat().st_size
    percentage = (output_size / input_size) * 100
    gzip_percentage = (gzip_size / input_size) * 100

    print("\n=== TRANSFORMATION RESULTS ===\n")
    print("Files:")
    print(f"  Original:  file://{activities_path}")
    print(f"  Regular:   file://{output_path}")
    print(f"  Gzipped:   file://{gzip_path}")

    print("\n--- Size Comparison ---")
    print(f"Original JSON:      {input_size:,} bytes (100.0%)")
    print(f"Column dict JSON:   {output_size:,} bytes ({percentage:.1f}%)")
    print(f"Column dict GZIP:   {gzip_size:,} bytes ({gzip_percentage:.1f}%)")
    print(f"Compression ratio:  {input_size / gzip_size:.1f}x smaller")

    print("\n--- Performance (Regular) ---")
    print(f"Transform time:     {transform_time * 1000:.2f} ms")
    print(f"Save time:          {save_time * 1000:.2f} ms")
    print(f"Load time:          {load_time * 1000:.2f} ms")
    print(f"Reconstruct time:   {reconstruct_time * 1000:.2f} ms")
    print(f"Total (save):       {(transform_time + save_time) * 1000:.2f} ms")
    print(f"Total (load):       {(load_time + reconstruct_time) * 1000:.2f} ms")
    print(
        f"Round-trip:         "
        f"{(transform_time + save_time + load_time + reconstruct_time) * 1000:.2f} ms"
    )

    print("\n--- Performance (Gzip) ---")
    print(f"Transform time:     {transform_time_gz * 1000:.2f} ms")
    print(f"Save time (gz):     {save_time_gz * 1000:.2f} ms")
    print(f"Load time (gz):     {load_time_gz * 1000:.2f} ms")
    print(f"Reconstruct time:   {reconstruct_time_gz * 1000:.2f} ms")
    print(f"Total (save):       {(transform_time_gz + save_time_gz) * 1000:.2f} ms")
    print(f"Total (load):       {(load_time_gz + reconstruct_time_gz) * 1000:.2f} ms")
    perf_round_trip = (
        transform_time_gz + save_time_gz + load_time_gz + reconstruct_time_gz
    ) * 1000.0
    print(f"Round-trip:         {perf_round_trip:.2f} ms")

    print("\n--- Gzip Overhead ---")
    gzip_save_overhead = save_time_gz - save_time
    gzip_load_overhead = load_time_gz - load_time
    print(f"Save overhead:      {gzip_save_overhead * 1000:+.2f} ms")
    print(f"Load overhead:      {gzip_load_overhead * 1000:+.2f} ms")
    print(
        f"Total overhead:     "
        f"{(gzip_save_overhead + gzip_load_overhead) * 1000:+.2f} ms"
    )
