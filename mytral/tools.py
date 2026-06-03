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
import datetime
import time
import uuid

from mytral import app_logger
from mytral import commons
from mytral import settings
from mytral import utils
from mytral.backends import dataset
from mytral.backends import entities
from mytral.integrations import icommons


def optimize_current_dataset(user_id: str, dataset_name: str, ds: dataset.UserDataset):
    """Tool to optimize user dataset:

    - workout number uniqueness within the same day
    - convert Strava activity_type_key IDs to MyTraL activity type IDs
    - rename hike workouts to use czech language, not czech&english combined

    """
    app_logger.info(f"Optimizing dataset of user {user_id}:")

    activities = ds.list_activities(
        user_id=user_id,
        dataset_name=dataset_name,
    )

    valid_activity_type_ids = list(
        ds.list_activity_types(user_id).activity_types_by_key.keys()
    )

    # WORKOUT NUMBER UNIQUENESS WITHIN THE SAME DAY
    # map: year -> month -> day -> [activities]
    as_by_day = {}
    for a in activities:
        year = a.when_year
        month = a.when_month
        day = a.when_day
        if year not in as_by_day:
            as_by_day[year] = {}
        if month not in as_by_day[year]:
            as_by_day[year][month] = {}
        if day not in as_by_day[year][month]:
            as_by_day[year][month][day] = []
        as_by_day[year][month][day].append(a)

        # FIX: Strava activity_type_key IDs normalization
        if a.activity_type_key not in valid_activity_type_ids:
            a.activity_type_key = icommons.STRAVA_TO_MYTRAL_AT.get(
                a.activity_type_key, a.activity_type_key
            )

        # FIX: 0:00:00 time in sauna, steam and fyzio
        if a.hours == 0 and a.minutes == 0 and a.seconds == 0:
            if a.activity_type_key in [
                commons.AT_SAUNA,
                commons.AT_STEAM,
            ]:
                a.hours = 1
                ds.update_activity(user_id=user_id, dataset_name=dataset_name, entity=a)
            if a.activity_type_key in [
                commons.AT_PHYSIO,
            ]:
                a.hours = 0
                a.minutes = 20
                ds.update_activity(user_id=user_id, dataset_name=dataset_name, entity=a)

        # FIX: EN&CZ -> CZ
        if a.name:
            if "Procházka (morning)" in a.name:
                a.name = a.name.replace("Procházka (morning)", "Procházka (ráno)")
                ds.update_activity(user_id=user_id, dataset_name=dataset_name, entity=a)
            elif "Procházka (evening)" in a.name:
                a.name = a.name.replace("Procházka (evening)", "Procházka (večer)")
                ds.update_activity(user_id=user_id, dataset_name=dataset_name, entity=a)

        # refresh calculated fields
        entities.evaluate_activity(entity=a, user_profile=ds.profile(user_id))

    activity_types = ds.list_activity_types(user_id)

    # optimize
    for year, months in as_by_day.items():
        for month, days in months.items():
            for day, as_in_day in days.items():
                if len(as_in_day) > 1:
                    app_logger.info(
                        f"Day {year}-{month}-{day} has {len(as_in_day)} activities"
                    )
                    # sort by time
                    as_in_day = sorted(as_in_day, key=lambda aa: aa.when, reverse=False)
                    # map: workout order -> activity order -> activity
                    workouts = {}
                    max_workout = 0
                    for i, a in enumerate(as_in_day):
                        app_logger.info(f"  {i + 1}. {a}")
                        if activity_types.is_exercise(
                            a.activity_type_key
                        ) or activity_types.is_distance(a.activity_type_key):
                            if a.workout_sort_code not in workouts:
                                max_workout = max(max_workout, a.workout_sort_code)
                                workouts[a.workout_sort_code] = {a.sort_code: a}
                            elif a.sort_code not in workouts[a.workout_sort_code]:
                                workouts[a.workout_sort_code][a.sort_code] = a
                            else:
                                # conflict
                                max_workout += 1
                                a.workout_sort_code = max_workout
                                workouts[a.workout_sort_code] = {a.sort_code: a}
                                # save
                                ds.update_activity(
                                    user_id=user_id, dataset_name=dataset_name, entity=a
                                )


def migrate_activity_type(
    user_id: str,
    dataset_name: str,
    from_type_key: str,
    to_type_key: str,
    ds: dataset.UserDataset,
) -> int:
    """Migrate all activities from one activity type to another.

    Parameters
    ----------
    user_id : str
        User ID.
    dataset_name : str
        Name of the dataset to migrate.
    from_type_key : str
        Activity type key to migrate from.
    to_type_key : str
        Activity type key to migrate to.
    ds : backends.dataset.UserDataset
        User dataset.

    Returns
    -------
    int
        Number of migrated activities.
    """
    app_logger.info(
        f"Migrating activities from '{from_type_key}' to '{to_type_key}' "
        f"in dataset '{dataset_name}' of user '{user_id}'"
    )

    activities = ds.list_activities(user_id=user_id, dataset_name=dataset_name)

    user_profile = ds.profile(user_id)
    migrated = 0
    for a in activities:
        if a.activity_type_key == from_type_key:
            a.activity_type_key = to_type_key
            entities.evaluate_activity(entity=a, user_profile=user_profile)
            ds.update_activity(user_id=user_id, dataset_name=dataset_name, entity=a)
            migrated += 1

    app_logger.info(f"  Migrated {migrated} activities")
    return migrated


def fix_gear_keys(user_id: str, dataset_name: str, ds: dataset.UserDataset):
    """Tool to fix gear keys in the dataset of the given user - migrates gear keys
    in activities from gear names, Strava IDs, ... to MyTraL gear keys. The fix is
    performed in place.

    """
    app_logger.info(f"Fixing gear keys in the dataset of user {user_id}:")

    activities = ds.list_activities(
        user_id=user_id, dataset_name=dataset_name, skip_future=True
    )

    if activities:
        gear = ds.list_gear(user_id=user_id, dataset_name=dataset_name)
        name2gear = gear.to_dict_by_name()
        strava2gear = gear.to_dict_by_external_id(settings.UserGear.SERVICE_STRAVA)

        for a in activities:
            activity_gears = (
                a.gears
                if hasattr(a, "gears")
                else ([a.gear] if hasattr(a, "gear") and a.gear else [])
            )
            fixed_gears = []
            needs_update = False

            for gear_key in activity_gears:
                if gear_key is None or gear_key == "":
                    needs_update = True
                    continue
                elif utils.is_uuid(gear_key):
                    app_logger.info(
                        f"  OK: gear key is UUID {gear_key} in activity {a.key}"
                    )
                    fixed_gears.append(gear_key)
                elif gear_key in name2gear:
                    app_logger.info(
                        f"  FIX: gear key is name '{gear_key}' -> "
                        f"{name2gear[gear_key].key} in activity {a.key}"
                    )
                    fixed_gears.append(name2gear[gear_key].key)
                    needs_update = True
                elif gear_key in strava2gear:
                    new_key = strava2gear[gear_key].key
                    app_logger.info(
                        f"  FIX: gear key is Strava ID "
                        f"'{gear_key}' -> {new_key} "
                        f"in activity {a.key}"
                    )
                    fixed_gears.append(new_key)
                    needs_update = True
                else:
                    app_logger.info(
                        f"  ERROR: gear key is unknown '{gear_key}' in activity {a.key}"
                    )
                    fixed_gears.append(gear_key)

            if needs_update:
                a.gears = fixed_gears
                ds.update_activity(user_id=user_id, dataset_name=dataset_name, entity=a)


def join_datasets(
    user_id: str,
    src_dataset_name: str,
    dst_dataset_name: str,
    ds: dataset.UserDataset,
):
    """Join existing activities in the target dataset with the activities from
    the source dataset(s) - "same" activity is the activity with the same
    when date (year, month, day) + activity_type_key + **meters**.

    Method:

    - load TARGET dataset as JSON & sort it to dictionary by when date + activity type
    - load SOURCE dataset as JSON
    - iterate over SOURCE activities as dictionary
      - find the same activity in the TARGET dataset (when + activity_type_key + meters)
      - deserialize to Activity objects
      - do join Activity.join()
      - serialize back to JSON

    """
    app_logger.info(f"Joining dataset '{src_dataset_name}' to '{dst_dataset_name}' ...")

    # source
    if not src_dataset_name:
        raise ValueError("Source dataset name must be specified!")
    src_activities = ds.list_activities(user_id=user_id, dataset_name=src_dataset_name)

    # target
    if not dst_dataset_name:
        raise ValueError("Target dataset name must be specified!")
    dst_activities = ds.list_activities(user_id=user_id, dataset_name=dst_dataset_name)

    # join
    joined_activities: list[entities.ActivityEntity] = []

    # index: year -> month -> day -> [activities]
    dst_sort_idx = {}
    app_logger.info(f"  Loaded destination dataset {dst_dataset_name}")
    for a_dst in dst_activities:
        src_y = a_dst.when_year
        src_m = a_dst.when_month
        src_d = a_dst.when_day
        if src_y not in dst_sort_idx:
            dst_sort_idx[src_y] = {}
        if src_m not in dst_sort_idx[src_y]:
            dst_sort_idx[src_y][src_m] = {}
        if src_d not in dst_sort_idx[src_y][src_m]:
            dst_sort_idx[src_y][src_m][src_d] = []
        dst_sort_idx[src_y][src_m][src_d].append(a_dst)

    # join to dst
    app_logger.info(f"  Loaded source dataset: {src_dataset_name}")
    if src_activities:
        for a_src in src_activities:
            app_logger.info(f"    Joining source activity: {a_src.name}")
            src_y = a_src.when_year
            src_m = a_src.when_month
            src_d = a_src.when_day
            if (
                src_y in dst_sort_idx
                and src_m in dst_sort_idx[src_y]
                and src_d in dst_sort_idx[src_y][src_m]
            ):
                for a_dst in dst_sort_idx[src_y][src_m][src_d]:
                    # meters are compared approximately w/o the lowest meters
                    src_meters = int(a_src.distance / 10) * 10
                    dst_meters = int(a_dst.distance / 10) * 10
                    if (
                        a_src.activity_type_key == a_dst.activity_type_key
                        and src_meters == dst_meters
                    ):
                        app_logger.info(
                            f"      Joining '{a_src.name}' -> '{a_dst.name}'"
                        )

                        # Strava join
                        a_dst.when_hour = a_src.when_hour
                        a_dst.when_minute = a_src.when_minute
                        a_dst.when_second = a_src.when_second
                        a_dst.when = a_src.when
                        a_dst.where = a_src.where
                        a_dst.intensity = a_src.intensity
                        a_dst.gears = (
                            a_src.gears
                            if hasattr(a_src, "gears")
                            else (
                                [a_src.gear]
                                if hasattr(a_src, "gear") and a_src.gear
                                else []
                            )
                        )
                        a_dst.hours = a_src.hours
                        a_dst.minutes = a_src.minutes
                        a_dst.seconds = a_src.seconds
                        a_dst.distance = a_src.distance
                        a_dst.commute = a_src.commute
                        a_dst.ranked = a_src.ranked
                        a_dst.race = a_src.race
                        a_dst.kcal = a_src.kcal
                        a_dst.max_speed = a_src.max_speed
                        a_dst.elevation_max = a_src.elevation_max
                        a_dst.elevation_min = a_src.elevation_min
                        a_dst.elevation_gain = a_src.elevation_gain
                        a_dst.avg_watts = a_src.avg_watts
                        a_dst.max_watts = a_src.max_watts
                        a_dst.avg_cadence = a_src.avg_cadence
                        a_dst.max_cadence = a_src.max_cadence
                        a_dst.avg_hr = a_src.avg_hr
                        a_dst.max_hr = a_src.max_hr
                        a_dst.min_hr = a_src.min_hr
                        a_dst.fitness_score = a_src.fitness_score
                        a_dst.src_key = a_src.key
                        a_dst.src_descriptor = a_src.src_descriptor
                        a_dst.src_url = a_src.src_url
                        a_dst.duration = a_src.duration
                        a_dst.duration_seconds = a_src.duration_seconds
                        a_dst.avg_speed = a_src.avg_speed

                        joined_activities.append(a_dst)

        ds.update_activities(
            user_id=user_id, dataset_name=dst_dataset_name, activities=joined_activities
        )

    app_logger.debug(f"  Joined {len(joined_activities)} activities")


def merge_datasets(
    user_id: str,
    ds: dataset.UserDataset,
    dataset_names: list[str] | None = None,
    target_dataset_name: str = commons.DATASET_NAME_MAIN,
):
    """Tool to merge datasets of the **given user. By **default** it merges all user's
    datasets (files matching ``dataset-*.json``) to the **main** dataset
    (``lifelong.json``).

    Parameters
    ----------
    user_id : str
        User ID used to load and save activities datasets of the right user.
    ds : backends.dataset.UserDataset
        User dataset.
    target_dataset_name : str
        Name of the target dataset to merge given datasets into. Default is the main
        dataset.
    dataset_names : List[str]
        Optional list of dataset names to be merged. Default (``None``) means merge
        of **all**  datasets of the user specified by the user profile.

    """
    # BENCHMARK:
    # - merged 5076 activities in 0.4850s
    start_time = time.perf_counter()

    # force TARGET dataset by setting it in user_profile
    profile = ds.profile(user_id)
    profile.dataset_name = target_dataset_name
    ds.update_profile(profile)

    # merge all datasets to the main dataset which will be overwritten
    do_merge_all = bool(target_dataset_name == commons.DATASET_NAME_MAIN)

    if do_merge_all:
        # create new dataset and merge everything into it
        all_years_list: list[entities.ActivityEntity] = []
    else:
        all_years_list = ds.list_activities(
            user_id=user_id, dataset_name=target_dataset_name
        )

    # list datasets to be merged - dataset-*.json files are merged ONLY
    if not dataset_names:
        dataset_names = ds.profile(user_id).dataset_names
    app_logger.info(f"Datasets of user '{user_id}':")
    if not dataset_names:
        app_logger.info("  No datasets found.")
    else:
        for d in dataset_names:
            app_logger.info(f"  {d}")
        app_logger.info(f"Merging datasets of user '{user_id}':")
    for dataset_name in dataset_names:
        app_logger.info(f"  {dataset_name}")
        if do_merge_all and not dataset_name.startswith(
            dataset.MyTraLDataset.PREFIX_DS_NAME
        ):
            app_logger.info(
                f"    SKIPPING ~ not merging {dataset_name} (not a dataset)"
            )
            continue

        src_dataset_list = ds.list_activities(
            user_id=user_id, dataset_name=dataset_name
        )
        if src_dataset_list:
            for activity in src_dataset_list:
                new_key = ds.create_key()
                app_logger.info(f"    Activity: {activity.key} -> {new_key}")
                activity.key = new_key
                all_years_list.append(activity)

                for e in activity.exercises:
                    e.activity_key = new_key
                for e in activity.sickness_symptoms:
                    e.activity_key = new_key

    # save merged dataset
    ds.update_activities(
        user_id=user_id, dataset_name=target_dataset_name, activities=all_years_list
    )

    end_time = time.perf_counter()
    duration = end_time - start_time
    app_logger.info(f"MERGED: {len(all_years_list)} activities in {duration:.4f}s")


def filter_date_range_dataset(
    user_id: str,
    ds: dataset.UserDataset,
    filter_newer_str: str,
    filter_older_str: str,
    src_dataset_name: str,
    dst_dataset_name: str = "",
    do_extract: bool = False,
    *,
    blob_service=None,
):
    """Filter activities of the source dataset from the given date range. Source dataset
    is either kept intact or its matching activities are deleted. New filtered dataset
    is stored under the given name which typically contains ``filtered`` in its name.
    Datasets are processed as JSON files i.e. MyTraL dataset is not used.

    Parameters
    ----------
    user_id : str
        User ID.
    ds : backends.dataset.UserDataset
        User dataset.
    filter_newer_str : str
        Keep activities newer that the date string in the format ``YYYY-MM-DD``,
        including this date.
    filter_older_str : str
        Keep activities older that the date string in the format ``YYYY-MM-DD``,
        including this date.
    src_dataset_name : str
        Name of the source dataset to be filtered.
    dst_dataset_name : str
        Name of the filtered dataset.
    do_extract : bool
        Whether to delete matching entities in the source dataset.
    blob_service : ActivityBlobService or None
        If provided, deletes all blobs for each activity before removing
        the activity record (only when ``do_extract`` is True).

    """
    app_logger.info(
        f"Filtering dataset '{src_dataset_name}' to '{dst_dataset_name}' ..."
    )

    if not src_dataset_name:
        raise ValueError("Source dataset name must be specified!")
    if not filter_newer_str:
        raise ValueError("Filter newer date must be specified!")
    elif (
        len(filter_newer_str) != len("2024-05-11")
        or not filter_newer_str[4] == "-"
        or not filter_newer_str[7] == "-"
    ):
        raise ValueError("Filter newer date must be in the format 'YYYY-MM-DD'")
    if not filter_older_str:
        raise ValueError("Filter older date must be specified!")
    elif (
        len(filter_older_str) != len("2024-12-31")
        or not filter_older_str[4] == "-"
        or not filter_older_str[7] == "-"
    ):
        raise ValueError("Filter older date must be in the format 'YYYY-MM-DD'")

    # source dataset
    profile = ds.profile(user_id)
    if src_dataset_name not in profile.dataset_names:
        raise FileNotFoundError(
            f"Unable to load the source dataset - unknown dataset name: "
            f"{src_dataset_name}"
        )

    # filtered dataset
    dst_dataset_name = dst_dataset_name or f"{src_dataset_name}-filtered"
    if dst_dataset_name in profile.dataset_names:
        dst_dataset_name += str(uuid.uuid4())
    dst_dataset_list = []

    # from date
    filter_newer = datetime.datetime.strptime(filter_newer_str, "%Y-%m-%d")
    # to date
    filter_older = datetime.datetime.strptime(filter_older_str, "%Y-%m-%d")

    # aliases
    src_dataset_list = ds.list_activities(
        user_id=user_id, dataset_name=src_dataset_name
    )
    matching_keys = []
    for a in src_dataset_list:
        src_y = a.when_year
        src_m = a.when_month
        src_d = a.when_day

        a_date = datetime.datetime.strptime(f"{src_y}-{src_m}-{src_d}", "%Y-%m-%d")

        if filter_older >= a_date >= filter_newer:
            matching_keys.append(a.key)
            dst_dataset_list.append(a)

    # if requested, delete matching entities in the source dataset
    if do_extract:
        for key in matching_keys:
            if blob_service:
                try:
                    blob_service.delete_all_activity_blobs(
                        user_id=user_id, activity_key=key
                    )
                except Exception as exc:
                    app_logger.warning(
                        f"  Failed to delete blobs for activity {key}: {exc}"
                    )
            ds.delete_activity(user_id=user_id, dataset_name=src_dataset_name, key=key)

        app_logger.info(
            f"  Extracted {len(matching_keys)} activities from the source dataset"
        )

    # save filtered dataset
    ds.create_activities_dataset(user_id=user_id, dataset_name=dst_dataset_name)
    ds.update_activities(
        user_id=user_id, dataset_name=dst_dataset_name, activities=dst_dataset_list
    )
    app_logger.info(f"  Filtered dataset saved to: {dst_dataset_name}")

    return dst_dataset_name


PRUNE_FILTER_ALL = "ALL"


def prune_activities(
    user_id: str,
    dataset_name: str,
    ds: dataset.UserDataset,
    filter_when_year: str = PRUNE_FILTER_ALL,
    filter_src: str = PRUNE_FILTER_ALL,
    filter_src_key: str = PRUNE_FILTER_ALL,
    filter_src_descriptor: str = PRUNE_FILTER_ALL,
    *,
    blob_service=None,
) -> int:
    """Remove activities from the current dataset that match **all** given filter
    criteria. A filter set to ``PRUNE_FILTER_ALL`` matches any value.

    Parameters
    ----------
    user_id : str
        User ID.
    dataset_name : str
        Name of the dataset to prune.
    ds : backends.dataset.UserDataset
        User dataset.
    filter_when_year : str
        Year to match (as string), or ``PRUNE_FILTER_ALL`` to skip year filtering.
    filter_src : str
        Source value to match, or ``PRUNE_FILTER_ALL`` to skip source filtering.
    filter_src_key : str
        Source key to match, or ``PRUNE_FILTER_ALL`` to skip source key filtering.
    filter_src_descriptor : str
        Source descriptor to match, or ``PRUNE_FILTER_ALL`` to skip filtering.
    blob_service : ActivityBlobService or None
        If provided, deletes all blobs for each activity before removing
        the activity record.

    Returns
    -------
    int
        Number of pruned (deleted) activities.

    """
    app_logger.info(
        f"Pruning activities from dataset '{dataset_name}' of user '{user_id}' "
        f"(year={filter_when_year}, src={filter_src}, src_key={filter_src_key}, "
        f"src_descriptor={filter_src_descriptor}) ..."
    )

    activities = ds.list_activities(user_id=user_id, dataset_name=dataset_name)

    keys_to_delete = []
    for a in activities:
        if (
            filter_when_year != PRUNE_FILTER_ALL
            and str(a.when_year) != filter_when_year
        ):
            continue
        if filter_src != PRUNE_FILTER_ALL and a.src != filter_src:
            continue
        if filter_src_key != PRUNE_FILTER_ALL and a.src_key != filter_src_key:
            continue
        if (
            filter_src_descriptor != PRUNE_FILTER_ALL
            and a.src_descriptor != filter_src_descriptor
        ):
            continue
        keys_to_delete.append(a.key)

    for key in keys_to_delete:
        if blob_service:
            try:
                blob_service.delete_all_activity_blobs(
                    user_id=user_id, activity_key=key
                )
            except Exception as exc:
                app_logger.warning(
                    f"  Failed to delete blobs for activity {key}: {exc}"
                )
        ds.delete_activity(user_id=user_id, dataset_name=dataset_name, key=key)

    app_logger.info(f"  Pruned {len(keys_to_delete)} activities")
    return len(keys_to_delete)
