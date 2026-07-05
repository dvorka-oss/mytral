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

"""
JSON-based persistence PURPOSE:

- it is meant for 1 user / desktop use (however, it can be used LOCALLY w/ >1 user)
- it is NOT meant for many users - RDBMS (embedded/cluster) is for that purpose

JSON-based persistence TENETS:

- MindForger persistence RULEZ ~ BEWARE changing files under running MyTraL server!
- SINGLE user
- when user logs in:
  - ALL activity/settings/* are loaded
  - lifelong is build in memory and stored to cache: [user] -> [filename key] -> [dict]
  - settings are loaded to memory and stored in cache
  - *-stats are build in memory and stored to cache
- data are READ from MEMORY ~ in-memory cache
- data are WRITTEN to FILESYSTEM through MEMORY (cache)
  - lifelong is NOT persisted: it is considered to be an in memory index
  - *-stats are NOT persisted: they are considered to be in memory indices
- CACHE is integral part of the JSON dataset, NOT other as they may have different needs
- CACHE is controlled by JSON dataset implementation to do its own OPTIMIZATIONS

JSON-based user activities dataset DESIGN:

- FILESYSTEM ~ file names:
    - ACTIVITIES:
      - activities-<YEAR>.json
        - RESERVED file name
        - activities are grouped by YEAR
        - NEW activities are routed to its year file

    - PROFILE:
        - user-<SETTING>.json
            - specific profile settings like gear, outfits, goals, routes, ...
        - user-<SETTING>-stats.json
            - LAZY: created on demand when needed
            - stats calculated from ALL activities e.g. use of a given gear
            - not all settings need stats files

    - DIARY:
      - diary-weekly-<YEAR>.json
        - RESERVED file name
        - no special treatment

    - DIGITIZATION / WORKING / RAW ACTIVITIES:
        - activities-<WHATEVER>.json
          - NOT clashing with the RESERVED names of production JSON activity files
          - invisible in non-expert mode

- in-memory CACHE ~ keys:
    - see MytralCache for more details: activities, settings and indices (cache ONLY)

Dataset MODEs:

1. LIFELONG:
  - default
  - works on MULTIPLE activities-*.json files
  - activities are routed to file by when year
2. CUSTOM ACTIVITIES DATASET:
  - custom year / dataset
  - works on SINGLE activities-*.json file
  - no routing (the file is used), no lifelong (the file is lifelong itself)

"""

import dataclasses
import datetime
import json
import pathlib
import re
import uuid
from typing import Callable

from mytral import commons
from mytral import config
from mytral import loggers
from mytral import persistences
from mytral import security
from mytral import settings
from mytral import stats
from mytral.backends import cache
from mytral.backends import caches
from mytral.backends import dataset
from mytral.backends import entities

# constants
FILE_ACTIVITIES_PRE = "activities-"
FILE_STATS_INFIX = "stats"
EXT_JSON = "json"


def list_activity_dataset_names(user_dir: pathlib.Path) -> list[str]:
    wild = user_dir.glob(f"{dataset.MyTraLDataset.PREFIX_DS_NAME}*.json")
    names = [str(f.stem) for f in wild if f.is_file() and "user" not in str(f.stem)]
    if (
        JsonUsersDataset.FILE_DATASET_MAIN not in names
        and (user_dir / f"{JsonUsersDataset.FILE_DATASET_MAIN}.json").exists()
    ):
        names.append(JsonUsersDataset.FILE_DATASET_MAIN)

    # always include lifelong as it's a symbolic/virtual dataset
    if JsonUsersDataset.FILE_DATASET_MAIN not in names:
        names.append(JsonUsersDataset.FILE_DATASET_MAIN)

    return names


def list_activity_year_dataset_names(user_dir: pathlib.Path) -> list[str]:
    activities_ds_names = list_activity_dataset_names(user_dir=user_dir)
    if activities_ds_names:
        pattern = r"^activities-\d{4}$"
        year_ds_names = []
        for a_ds_name in activities_ds_names:
            if a_ds_name and bool(re.match(pattern, a_ds_name)):
                year_ds_names.append(a_ds_name)
        return year_ds_names
    return activities_ds_names


# TODO rename JSONUser > JsonUser...
class JSONUserActivitiesDataset:
    """JSON implementation of user activities dataset.

    Activities synchronization:

    - In order to avoid race conditions in reading/writing the activities
      w/ or w/o cache, all activity related methods are mutually exclusive,
      including statistics.

    """

    @staticmethod
    def _ddict_2_dict(
        activities: dict[str, dict] | list[dict],
    ) -> dict[str, entities.ActivityEntity]:
        """Convert dict (old) or list (new) format to runtime dict."""
        # normalize to dict format for processing
        activities_dict = persistences.normalize_dict_or_list_to_dict(activities)

        user_ds_d = {}
        for d in activities_dict.values():
            # backward compatibility: migrate gear (str) to gears (list[str])
            if "gear" in d and "gears" not in d:
                gear_value = d.pop("gear")
                if gear_value:
                    d["gears"] = [gear_value]

            # backward compatibility: migrate legacy single recording keys
            gpx_blob_key = d.pop("gpx_blob_key", "")
            fit_blob_key = d.pop("fit_blob_key", "")
            if "recorded_blob_keys" not in d or d["recorded_blob_keys"] is None:
                d["recorded_blob_keys"] = []
            if gpx_blob_key:
                gpx_entry = f"{gpx_blob_key}.gpx"
                if gpx_entry not in d["recorded_blob_keys"]:
                    d["recorded_blob_keys"].append(gpx_entry)
            if fit_blob_key:
                fit_entry = f"{fit_blob_key}.fit"
                if fit_entry not in d["recorded_blob_keys"]:
                    d["recorded_blob_keys"].append(fit_entry)

            entity = entities.ActivityEntity(**d)
            entity.exercises = [entities.ExerciseEntity(**e) for e in entity.exercises]
            entity.sickness_symptoms = [
                entities.SicknessSymptomEntity(**e) for e in entity.sickness_symptoms
            ]
            entity.laps = [
                entities.LapEntity(**lap)
                for lap in (entity.laps if entity.laps else [])
            ]

            user_ds_d[entity.key] = entity

        return user_ds_d

    def __init__(
        self,
        mytral_config: config.MytralConfig,
        key_generator: Callable[[], str],
        data_dir: pathlib.Path,
        ext: str,
        mytral_cache: cache.MytralCache,
        # TODO there is a bug: assert for None when_* > unit test load&safe&compare ALL
        persistence_sparse: bool = False,
        persistence_msgpack: bool = False,
        logger: loggers.MytralLogger | None = None,
    ):
        """User activities dataset stored in text or binary JSON files.

        Parameters
        ----------
        mytral_config : config.MytralConfig
            Application configuration.
        key_generator : Callable[[], str]
            Function to generate new unique keys for activities.
        data_dir : pathlib.Path
            Base directory where user data is stored.
        ext : str
            File extension to use for the dataset files (e.g., 'json').
        mytral_cache : cache.MytralCacheAbc
            Cache instance to use for caching user data - JSON persistence controls
            the cache set/get/evict cycle as it is aware of modification (can evict
            all the impacted indices) as well as when to read from memory and when
            to write to filesystem through memory.
        persistence_sparse : bool, optional
            If True, save only non-default values in the dataset files to save space.
        persistence_msgpack : bool
            If True, use MessagePack format for persistence instead of plain JSON.
            This class supports switching between JSON and MessagePack formats. The
            logic works as follows when MessagePack is enabled:

            - loading: if BOTH files exist, compare timestamps and load the newer one
            - saving: save MessagePack file ONLY and delete the JSON file

            If MessagePack is disabled, then JSON works analogously as MessagePack.

        """
        self.logger = logger or loggers.MytralStructLogger()
        self.log_name = "[JSON user activities]"

        self.config = mytral_config
        self.new_key = key_generator
        self.data_dir = data_dir
        self.ext = ext

        # caching
        self.cached_dataset_name = ""
        self._cache = mytral_cache

        # sparse mode: save only non-default values, complete on load
        self.persistence_sparse = persistence_sparse
        # persistence format: JSON (.json) vs. MessagePack (.msgpack)
        self.persistence_msgpack = persistence_msgpack

    @staticmethod
    def _ds_name_for_activity(
        dataset_name: str,
        entity: entities.ActivityEntity | int,
    ) -> str:
        """Get (target) dataset name for given activity."""
        when_year = entity if isinstance(entity, int) else entity.when_year
        if commons.DS_LIFELONG == dataset_name:
            upper_year_limit = datetime.date.today().year + 50
            if not (1900 < when_year < upper_year_limit):
                raise RuntimeError(
                    f"Activity's year is out of range: '{when_year}', most "
                    f"probably an error and therefore the activity cannot be saved, "
                    f"because such dataset file does NOT exist and will not be created."
                )
            return f"{FILE_ACTIVITIES_PRE}{when_year}"

        # else SINGLE dataset
        return dataset_name

    def _ds_path(
        self, user_id: str, dataset_name: str, ext: str = persistences.EXT_JSON
    ) -> pathlib.Path:
        return self.data_dir / user_id / f"{dataset_name}.{ext}"

    def _ds_stats_path(
        self, user_id: str, dataset_name: str, ext: str = persistences.EXT_JSON
    ) -> pathlib.Path:
        return self.data_dir / user_id / f"{dataset_name}-{FILE_STATS_INFIX}.{ext}"

    def _dict_2_ddict(
        self, activities: dict[str, entities.ActivityEntity]
    ) -> list[dict]:
        """Dict of entities to list of dicts (new format)."""
        if self.persistence_sparse:
            return [a.to_sparse_dict() for a in activities.values()]

        return [dataclasses.asdict(a) for a in activities.values()]

    def user_dir(self, user_id: str) -> pathlib.Path:
        user_dir = self.data_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    #
    # CACHE mgmt
    #

    def _lifelong_cache_refresh(self, user_id: str, dataset_name: str) -> dict:
        self.logger.info(
            f"  {self.log_name} REFRESH '{dataset_name}' dataset to CACHE..."
        )
        lifelong_ds = {}
        years_cache = self._cache.user(user_id).activities_years()
        for y_ds in years_cache:
            lifelong_ds.update(years_cache[y_ds])
        self._cache.user(user_id).set_activities(
            activities=lifelong_ds, dataset_name=dataset_name
        )
        self.logger.info(
            f"  {self.log_name} DONE '{dataset_name}' dataset CACHED with "
            f"{len(lifelong_ds)} activities"
        )

        return lifelong_ds

    #
    # CACHE through CRUD
    #

    def _load(
        self, user_id: str, dataset_name: str
    ) -> dict[str, entities.ActivityEntity]:
        """Load LIFELONG/custom activities either from cache or from the filesystem
        (to the cache).

        - Initializes NON-INITIALIZED cache by loading all YEAR activities files
          and refreshing LIFELONG/custom by merging YEARs there.

        Returns
        -------
        dict :
            LIFELONG/custom activities' dataset.

        """

        # INVARIANT: profile and settings are loaded in cache

        # CACHE initialization ~ load YEAR files || CUSTOM file
        user_cache = self._cache.user(user_id)
        if user_cache.dataset_name() != dataset_name:
            self.logger.info(
                f"{self.log_name} INITIALIZING cache on the dataset change: "
                f"'{user_cache.dataset_name()}' -> '{dataset_name}'"
            )

            # dataset NOT yet loaded OR switched
            user_cache.evict_activities()
            user_cache.set_dataset_name(dataset_name)

            # INITIALIZE the cache by loading data from the filesystem
            if commons.DS_LIFELONG == dataset_name:
                year_a_ds_names = list_activity_year_dataset_names(
                    user_dir=self.user_dir(user_id=user_id)
                )
                year_a_cache_dict = user_cache.activities_years()
                for year_a_ds_name in year_a_ds_names:
                    year_str = year_a_ds_name[11:]
                    if not year_str:
                        raise RuntimeError(
                            f"Unable to extract year from '{year_a_ds_names}' when "
                            f"initializing JSON cache"
                        )
                    year_ds_path = self._ds_path(user_id, year_a_ds_name)
                    if not year_ds_path.exists():
                        year_ds_dd: dict = {}
                    else:
                        year_ds_dd = persistences.load_json(year_ds_path)
                    year_activities = JSONUserActivitiesDataset._ddict_2_dict(
                        year_ds_dd
                    )
                    year_a_cache_dict[year_str] = year_activities
                    self.logger.info(
                        f"{self.log_name} '{year_str}' ({len(year_activities)}) "
                        f"activities loaded to cache"
                    )
            else:  # custom dataset
                self.logger.info(f"{self.log_name} custom dataset - no year cache data")

            # cache INITIALIZED
            user_cache.set_dataset_name(dataset_name=dataset_name)

        # LIFELONG dataset
        all_activities = self._cache.user(user_id).activities(dataset_name)
        if not all_activities:
            all_activities = self._lifelong_cache_refresh(
                user_id=user_id, dataset_name=dataset_name
            )

        return all_activities

    def _exists(self, user_id: str, dataset_name: str) -> bool:
        return self._ds_path(user_id=user_id, dataset_name=dataset_name).exists()

    def _save(self, ds: dict[str, dict], user_id: str, dataset_name: str):
        persistences.save_json(
            file_path=self._ds_path(user_id=user_id, dataset_name=dataset_name),
            data_dict=ds,
        )

    def create_dataset(self, user_id: str, dataset_name: str):
        if self._exists(user_id=user_id, dataset_name=dataset_name):
            raise ValueError(
                f"{self.log_name} Dataset '{dataset_name}' already exists for user "
                f"{user_id}"
            )

        self._save(
            ds=self._dict_2_ddict({}),
            user_id=user_id,
            dataset_name=dataset_name,
        )

    def delete_dataset(self, user_id: str, dataset_name: str):
        if not self._exists(user_id=user_id, dataset_name=dataset_name):
            raise ValueError(
                f"{self.log_name} Unable to delete dataset '{dataset_name}' for user "
                f"{user_id} as it does not exist"
            )

        ds_path = self._ds_path(user_id=user_id, dataset_name=dataset_name)
        ds_path.unlink()

    def _pre_modify_activity(
        self,
        user_id: str,
        dataset_name: str,
        entity: entities.ActivityEntity | int,
    ) -> tuple[dict, str]:
        # assess target dataset name from the when_year
        target_dataset_name = self._ds_name_for_activity(
            dataset_name=dataset_name,
            entity=entity,
        )

        # YEAR
        # load YEAR datasets from filesystem to cache, refresh LIFELONG/CUSTOM
        self._load(user_id=user_id, dataset_name=dataset_name)
        # get YEAR dataset from cache
        year_ds = self._cache.user(user_id=user_id).activities_year(target_dataset_name)

        return year_ds, target_dataset_name

    def _post_modify_activity(
        self,
        user_id: str,
        dataset_name: str,
        target_dataset_name: str,
        entity: entities.ActivityEntity,
        year_ds: dict,
    ):
        # write YEAR dataset to filesystem || CUSTOM dataset file
        self._save(
            ds=self._dict_2_ddict(activities=year_ds),
            user_id=user_id,
            dataset_name=target_dataset_name,
        )

        # LIFELONG (in-memory only)
        lifelong_ds = self._cache.user(user_id=user_id).activities(
            dataset_name=dataset_name
        )
        lifelong_ds[entity.key] = entity  # add/set, do not re-merge all YEARS - faster
        # update YEAR cache -> evict indices
        self._cache.user(user_id).evict_on_activity_cud()

        # update component usage if activity has gear
        if hasattr(entity, "gears") and entity.gears:
            for gear_key in entity.gears:
                self._update_gear_component_usage(
                    user_id=user_id,
                    dataset_name=dataset_name,
                    gear_key=gear_key,
                    activity_distance_meters=entity.distance or 0,
                    activity_time_seconds=entity.duration_seconds or 0,
                    activity_timestamp=entity.when or "",
                )

    def _update_gear_component_usage(
        self,
        user_id: str,
        dataset_name: str,
        gear_key: str,
        activity_distance_meters: int,
        activity_time_seconds: int,
        activity_timestamp: str,
    ):
        """Update usage for all active components of a gear based on an activity."""
        try:
            # get gear
            gear = self._parent.get_gear(
                user_id=user_id, key=gear_key, dataset_name=dataset_name
            )

            if not gear or not gear.components:
                return

            # check if this activity is newer than last processed
            if (
                gear.last_activity_processed
                and activity_timestamp <= gear.last_activity_processed
            ):
                return  # already processed

            # update all active components
            for component_dict in gear.components:
                if component_dict.get("status") == "active":
                    component_dict["distance_meters"] = (
                        component_dict.get("distance_meters", 0)
                        + activity_distance_meters
                    )
                    component_dict["time_seconds"] = (
                        component_dict.get("time_seconds", 0) + activity_time_seconds
                    )

            # update last processed timestamp
            if (
                not gear.last_activity_processed
                or activity_timestamp > gear.last_activity_processed
            ):
                gear.last_activity_processed = activity_timestamp

            # save gear
            self._parent.update_gear(
                user_id=user_id, gear=gear, dataset_name=dataset_name
            )
        except Exception:
            # silently fail - don't break activity creation if gear update fails
            pass

    def create_activity(
        self,
        user_id: str,
        dataset_name: str,
        entity: entities.ActivityEntity,
    ) -> entities.ActivityEntity:
        """Create a new entity:

        - resolve target dataset file
        - cache:
          - evict what needs to be evicted on modification:
            lifelong, stats, settings stats, ...
          - add activity to cached dataset for YEAR
          - add activity to cached LIFELONG dataset
          ? let build settings stats (which depend on activities) vs. on-demand

        Parameters
        ----------
        user_id : str
          User ID.
        dataset_name : str
          Dataset is either `lifelong` or a custom dataset - which determines mode
          and routing of activities to dataset activities files.
        entity: entities.ActivityEntity
          Activity to be saved.

        """
        # complete and validate activity
        entity.key = self.new_key()
        # TODO IMPROVE verification:
        #  - sort codes must not clash
        #  - keys must be unique
        #  - ...
        entities.evaluate_activity(entity)

        year_ds, target_dataset_name = self._pre_modify_activity(
            user_id=user_id, dataset_name=dataset_name, entity=entity
        )

        # add entity to YEAR dataset
        year_ds[entity.key] = entity

        self._post_modify_activity(
            user_id=user_id,
            dataset_name=dataset_name,
            target_dataset_name=target_dataset_name,
            entity=entity,
            year_ds=year_ds,
        )

        return entity

    def create_activities(
        self,
        user_id: str,
        dataset_name: str,
        entity_list: list[entities.ActivityEntity],
    ) -> list[entities.ActivityEntity]:
        """Bulk creation of activities:

        - activities are clustered by year
        - activities w/ the same year are routed to their target dataset files for year

        """
        result: list[entities.ActivityEntity] = []

        today = datetime.datetime.now()

        # STEP: cluster activities by year
        a2year: dict[int, list[entities.ActivityEntity]] = {}
        for e in entity_list:
            when_year = e.when_year if isinstance(e.when_year, int) else today.year
            upper_year_limit = datetime.date.today().year + 50
            if not (1900 < when_year < upper_year_limit):
                raise RuntimeError(
                    f"Activity's year is out of range: '{when_year}', most "
                    f"probably an error and therefore the activity cannot be saved, "
                    f"because such dataset file does NOT exist and will not be created."
                )

            if when_year not in a2year:
                a2year[when_year] = []
            a2year[when_year].append(e)

        # STEP: get datasets for years > save clusters
        for y in a2year:
            pivot_a = a2year[y][0]
            target_dataset_name = self._ds_name_for_activity(
                dataset_name=dataset_name,
                entity=pivot_a,
            )
            # load YEAR datasets from filesystem to cache, refresh LIFELONG/CUSTOM
            self._load(user_id=user_id, dataset_name=dataset_name)
            # get YEAR dataset from cache
            year_ds = self._cache.user(user_id=user_id).activities_year(
                target_dataset_name
            )

            # STEP: add ALL activities of the year to the YEAR dataset
            for a in a2year[y]:
                year_ds[a.key] = a
                result.append(a)

            # STEP: exactly 1 write per YEAR dataset to filesystem || CUSTOM ds file
            self._save(
                ds=self._dict_2_ddict(activities=year_ds),
                user_id=user_id,
                dataset_name=target_dataset_name,
            )
            # LIFELONG (in-memory only)
            lifelong_ds = self._cache.user(user_id=user_id).activities(
                dataset_name=dataset_name
            )
            for a in a2year[y]:
                lifelong_ds[a.key] = a  # add/set, do not re-merge all YEARS - faster

                # STEP: update gear / component usage
                # - IMPROVE: consider checking whether activities even has a gear
                if a.gears:
                    for gear_key in a.gears:
                        self._update_gear_component_usage(
                            user_id=user_id,
                            dataset_name=dataset_name,
                            gear_key=gear_key,
                            activity_distance_meters=a.distance or 0,
                            activity_time_seconds=a.duration_seconds or 0,
                            activity_timestamp=a.when or "",
                        )

            # STEP: on behalf of ALL years - update YEAR caches -> evict indices
            self._cache.user(user_id).evict_on_activity_cud()

        return result

    def update_activity(
        self,
        user_id: str,
        dataset_name: str,
        entity: entities.ActivityEntity,
    ) -> entities.ActivityEntity:
        # evaluate activity to calculate duration and other transient fields
        entities.evaluate_activity(entity)

        year_ds, target_dataset_name = self._pre_modify_activity(
            user_id=user_id, dataset_name=dataset_name, entity=entity
        )

        if entity.key not in year_ds:
            lifelong_ds = self._cache.user(user_id=user_id).activities(
                dataset_name=dataset_name
            )
            if entity.key not in lifelong_ds:
                raise ValueError(
                    f"Unable to find the activity to update - {entity.key} not found "
                    f"in activities datasets"
                )
            old_when_year = lifelong_ds[entity.key].when_year
            old_target_dataset_name = self._ds_name_for_activity(
                dataset_name=dataset_name,
                entity=old_when_year,
            )
            old_year_ds = self._cache.user(user_id=user_id).activities_year(
                old_target_dataset_name
            )
            if entity.key in old_year_ds:
                del old_year_ds[entity.key]
                # write old YEAR dataset to filesystem || CUSTOM dataset file
                self._save(
                    ds=self._dict_2_ddict(activities=old_year_ds),
                    user_id=user_id,
                    dataset_name=old_target_dataset_name,
                )

        # set entity to YEAR dataset
        year_ds[entity.key] = entity

        self._post_modify_activity(
            user_id=user_id,
            dataset_name=dataset_name,
            target_dataset_name=target_dataset_name,
            entity=entity,
            year_ds=year_ds,
        )

        return entity

    def update_activities(
        self, user_id: str, dataset_name: str, activities: list[entities.ActivityEntity]
    ):
        """Bulk update of activities:

        - activities are evaluated to calculate duration and other transient fields
        - activities are clustered by year
        - activities w/ the same year are routed to their target dataset files for year

        """
        # evaluate activities to calculate duration and other transient fields
        for activity in activities:
            entities.evaluate_activity(activity)

        today = datetime.datetime.now()

        # STEP: cluster activities by year
        a2year: dict[int, list[entities.ActivityEntity]] = {}
        for e in activities:
            when_year = e.when_year if isinstance(e.when_year, int) else today.year
            upper_year_limit = datetime.date.today().year + 50
            if not (1900 < when_year < upper_year_limit):
                raise RuntimeError(
                    f"Activity's year is out of range: '{when_year}', most "
                    f"probably an error and therefore the activity cannot be saved, "
                    f"because such dataset file does NOT exist and will not be created."
                )

            if when_year not in a2year:
                a2year[when_year] = []
            a2year[when_year].append(e)

        # STEP: get datasets for years > save clusters
        for y in a2year:
            pivot_a = a2year[y][0]
            target_dataset_name = self._ds_name_for_activity(
                dataset_name=dataset_name,
                entity=pivot_a,
            )
            # load YEAR datasets from filesystem to cache, refresh LIFELONG/CUSTOM
            self._load(user_id=user_id, dataset_name=dataset_name)
            # get YEAR dataset from cache
            year_ds = self._cache.user(user_id=user_id).activities_year(
                target_dataset_name
            )

            # STEP: add ALL activities of the year to the YEAR dataset
            for a in a2year[y]:
                year_ds[a.key] = a

            # STEP: exactly 1 write per YEAR dataset to filesystem || CUSTOM ds file
            self._save(
                ds=self._dict_2_ddict(activities=year_ds),
                user_id=user_id,
                dataset_name=target_dataset_name,
            )
            # LIFELONG (in-memory only)
            lifelong_ds = self._cache.user(user_id=user_id).activities(
                dataset_name=dataset_name
            )
            for a in a2year[y]:
                lifelong_ds[a.key] = a  # add/set, do not re-merge all YEARS - faster

                # STEP: update gear / component usage
                if a.gears:
                    for gear_key in a.gears:
                        self._update_gear_component_usage(
                            user_id=user_id,
                            dataset_name=dataset_name,
                            gear_key=gear_key,
                            activity_distance_meters=a.distance or 0,
                            activity_time_seconds=a.duration_seconds or 0,
                            activity_timestamp=a.when or "",
                        )

            # STEP: on behalf of ALL years - update YEAR caches -> evict indices
            self._cache.user(user_id).evict_on_activity_cud()

    def delete_activity(self, user_id: str, dataset_name: str, key: str) -> None:
        # load YEAR datasets from filesystem to cache, refresh LIFELONG/CUSTOM
        lifelong_ds = self._load(user_id=user_id, dataset_name=dataset_name)
        if key not in lifelong_ds:
            raise ValueError(
                f"Unable to find the activity to delete - {key} not found in LIFELONG "
                f"dataset w/ {len(lifelong_ds)} activities"
            )

        # YEAR dataset (filesystem)
        entity = lifelong_ds[key]
        year_ds, target_dataset_name = self._pre_modify_activity(
            user_id=user_id, dataset_name=dataset_name, entity=entity
        )
        del year_ds[key]
        self._save(
            ds=self._dict_2_ddict(activities=year_ds),
            user_id=user_id,
            dataset_name=target_dataset_name,
        )

        # LIFELONG (in-memory only) - use already loaded lifelong_ds to avoid
        # re-fetch returning empty dict in passthrough cache mode
        if key in lifelong_ds:
            del lifelong_ds[key]

        # INVALIDATE cache
        self._cache.user(user_id).evict_on_activity_cud()

    def get_activity(
        self, user_id: str, dataset_name: str, key: str
    ) -> entities.ActivityEntity:
        user_ds_d = self._load(user_id=user_id, dataset_name=dataset_name)

        if key not in user_ds_d:
            raise ValueError(
                f"Unable to get activity - activity with key '{key}' not found in "
                f"the JSON database"
            )

        return user_ds_d[key]

    def list_activities(
        self,
        user_id: str,
        dataset_name: str,
        filter_year: int = 0,
        filter_month: int = 0,
        filter_day: int = 0,
        skip_future: bool = False,
    ) -> dict[str, entities.ActivityEntity]:
        user_ds_d = self._load(user_id=user_id, dataset_name=dataset_name)

        today = datetime.datetime.now()

        activities = {}
        for a in user_ds_d.values():
            if filter_year and a.when_year != filter_year:
                continue
            if filter_month and a.when_month != filter_month:
                continue
            if filter_day and a.when_day != filter_day:
                continue

            if skip_future and (
                a.when_year > today.year
                or (a.when_year >= today.year and a.when_month > today.month)
                or (
                    a.when_year >= today.year
                    and a.when_month >= today.month
                    and a.when_day > today.day
                )
            ):
                continue

            activities[a.key] = a

        return activities

    def export_activities(
        self,
        user_id: str,
        dataset_name: str,
    ) -> str:
        user_ds_d = self._load(user_id=user_id, dataset_name=dataset_name)
        return json.dumps(
            self._dict_2_ddict(activities=user_ds_d),
            indent=4,
        )


class JsonUsersDataset(dataset.UserDataset, cache.MytralCacheInitializer):
    """Users dataset stored in JSON files:

    - JSON users dataset is stateless in a sense that user ID must be provided as
      parameter to all the methods.
    - At the same time, JSON users dataset internal performs CACHING of the data for
      individual users.

    """

    DIR_DATA = "data"

    FILE_DATASET_MAIN = commons.DATASET_NAME_MAIN

    FILE_STRAVA_GEAR = "user-gear-strava.json"
    FILE_USER_ACTIVITY_TYPES = "user-activity-types.json"
    FILE_USER_EXERCISES = "user-exercises.json"
    FILE_USER_GEAR = "user-gear.json"
    FILE_USER_GOALS = "user-goals.json"
    FILE_USER_LAPS = "user-laps.json"
    FILE_USER_OUTFITS = "user-outfits.json"
    FILE_USER_BOOKMARKS = "user-activity-bookmarks.json"
    FILE_USER_COMPONENT_TEMPLATES = "user-component-templates.json"
    FILE_USER_SETTINGS = "user-settings.json"
    FILE_USER_SYMPTOMS = "user-symptoms.json"

    def __init__(self):
        """User dataset constructor."""
        dataset.UserDataset.__init__(self)

        self.config = None

        self.base_dir = None
        self.data_dir = None
        self.db_ext = None

        # cache:
        # - in-memory OR pass-through
        # - CANNOT be accessed from outside to prevent race conditions
        self._cache = None

        # activities dataset ~ avoids huge module ~ implemented in friendly class
        self._activities_dataset = None

        self.log_name = "[JSON user dataset]"

    def configure(
        self,
        mytral_config: config.MytralConfig,
        logger: loggers.MytralLogger | None = None,
    ) -> None:
        dataset.UserDataset.configure(self, mytral_config=mytral_config, logger=logger)

        # select cache implementation based on configuration
        if mytral_config.persistence_cache:
            self._cache = caches.InMemoryMytralCache(
                cache_initializer=self, logger=self.logger
            )
        else:
            self._cache = caches.PassthroughMytralCache(
                cache_initializer=self, logger=self.logger
            )

        # base directory (parent of the application data directory)
        self.base_dir = self.config.persistence_data_dir
        if not self.base_dir:
            self.base_dir = pathlib.Path().absolute()  # cwd
        self.base_dir = (
            self.base_dir
            if isinstance(self.base_dir, pathlib.Path)
            else pathlib.Path(self.base_dir)
        )
        if not self.base_dir.exists():
            raise ValueError(
                f"Specified application working directory '{self.base_dir}' does not "
                f"exist"
            )
        self.logger.info(f"Using data directory: {self.base_dir}")

        # application data directory
        self.data_dir = self.base_dir / JsonUsersDataset.DIR_DATA
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_ext = persistences.EXT_CSV

        # activities dataset
        self._activities_dataset = JSONUserActivitiesDataset(
            mytral_config=mytral_config,
            key_generator=self.create_key,
            data_dir=self.data_dir,
            ext=self.db_ext,
            mytral_cache=self._cache,
            logger=self.logger,
        )

    def create_key(self) -> str:
        return str(uuid.uuid4())

    #
    # files and dirs
    #

    def user_dir(self, user_id: str) -> pathlib.Path:
        user_dir = self.data_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def user_settings_path(
        self,
        user_id: str = commons.DEFAULT_USER_NAME,
    ):
        user_dir = self.user_dir(user_id)
        return user_dir / JsonUsersDataset.FILE_USER_SETTINGS

    def user_gear_path(self, user_id: str) -> pathlib.Path:
        return self.user_dir(user_id) / JsonUsersDataset.FILE_USER_GEAR

    def user_outfits_path(self, user_id: str) -> pathlib.Path:
        return self.user_dir(user_id) / JsonUsersDataset.FILE_USER_OUTFITS

    def user_bookmarks_path(self, user_id: str) -> pathlib.Path:
        return self.user_dir(user_id) / JsonUsersDataset.FILE_USER_BOOKMARKS

    def user_component_templates_path(self, user_id: str) -> pathlib.Path:
        return self.user_dir(user_id) / JsonUsersDataset.FILE_USER_COMPONENT_TEMPLATES

    def user_goals_path(self, user_id: str) -> pathlib.Path:
        return self.user_dir(user_id) / JsonUsersDataset.FILE_USER_GOALS

    def user_activity_types_path(self, user_id: str) -> pathlib.Path:
        return self.user_dir(user_id) / JsonUsersDataset.FILE_USER_ACTIVITY_TYPES

    def user_symptoms_path(self, user_id: str) -> pathlib.Path:
        return self.user_dir(user_id) / JsonUsersDataset.FILE_USER_SYMPTOMS

    def user_exercises_path(self, user_id: str) -> pathlib.Path:
        return self.user_dir(user_id) / JsonUsersDataset.FILE_USER_EXERCISES

    def user_laps_path(self, user_id: str) -> pathlib.Path:
        return self.user_dir(user_id) / JsonUsersDataset.FILE_USER_LAPS

    def user_strava_gear_path(self, user_id: str) -> pathlib.Path:
        return self.user_dir(user_id) / JsonUsersDataset.FILE_STRAVA_GEAR

    #
    # system
    #

    def init_user_cache(self, user_cache: cache.MytralUserCache, user_id: str):
        """Implementation of the cache initializer which loads all user data to
        the cache.

        """
        # do NOT load ALL activities ~ persistence mode is UNKNOWN ~ loaded on demand
        # do NOT load YEAR activities ~ persistence mode is UNKNOWN ~ ^

        self.logger.info(
            f"{self.log_name} INITIALIZING cache by loading profile and settings..."
        )
        user_cache.set_profile(self.profile(user_id=user_id))

        user_cache.set_activity_types(self.list_activity_types(user_id=user_id))
        user_cache.set_exercises(self.list_exercises(user_id=user_id))
        user_cache.set_gear(self.list_gear(user_id=user_id))
        user_cache.set_goals(self.list_goals(user_id=user_id))
        user_cache.set_laps(self.list_laps(user_id=user_id))
        user_cache.set_outfits(self.list_outfits(user_id=user_id))
        user_cache.set_bookmarks(self.list_bookmarks(user_id=user_id))
        user_cache.set_component_templates(
            self.list_component_templates(user_id=user_id)
        )
        user_cache.set_strava_gear(self.list_strava_gear(user_id=user_id))
        user_cache.set_symptoms(self.list_symptoms(user_id=user_id))

    def cache_evict(self, user_id: str):
        self._cache.evict(user_id)

    #
    # export
    #

    def export(
        self, user_id: str, archive_path: pathlib.Path, export_format: str = "zip"
    ):
        persistences.zip_directory(
            directory_path=self.user_dir(user_id),
            zip_file_path=archive_path,
        )

    #
    # dataset methods
    #

    def register_new_user(
        self,
        user_name: str = commons.DEFAULT_USER_NAME,
        user_id: str = "",
        user_display_name: str = "",
        password_enc: str = "",
    ):
        self.user_dir(user_id)

        # ALL user files
        self.create_profile(
            user_profile=settings.UserProfile(
                user_id=user_id,
                user=user_name,
                display_name=user_display_name,
                email="",
                password_enc=password_enc,
                dataset_name=JsonUsersDataset.FILE_DATASET_MAIN,
                dataset_names=[JsonUsersDataset.FILE_DATASET_MAIN],
                # bootstrap defaults - user should update these via onboarding
                born_year=commons.BOOTSTRAP_BORN_YEAR,
                born_month=commons.BOOTSTRAP_BORN_MONTH,
                born_day=commons.BOOTSTRAP_BORN_DAY,
                height=commons.BOOTSTRAP_HEIGHT_CM,
                gender=True,
            )
        )

        self._create_activity_types(user_id=user_id)
        self._create_exercises(user_id=user_id)
        self._create_gears(user_id=user_id)
        self._create_goals(user_id=user_id)
        self._create_laps(user_id=user_id)
        self._create_outfits(user_id=user_id)
        self._create_bookmarks(user_id=user_id)
        self._create_component_templates(user_id=user_id)
        self._create_symptoms(user_id=user_id)
        self._create_strava_gears(user_id=user_id)

        # IN-MEMORY ONLY ~ cache hosted: LIFELONG, indices (stats, heatmaps)

    #
    # user profile
    #

    def _load_profile(self, user_id: str) -> settings.UserProfile:
        path = self.user_settings_path(user_id)
        if not path.exists():
            raise ValueError(
                f"User settings path for user '{user_id}' does not exist: {path}"
            )

        profile_dict = persistences.load_json(path, logger=self.logger)
        profile_dict[settings.UserProfile.KEY_DATASET_NAMES] = (
            list_activity_dataset_names(self.user_dir(user_id=user_id))
        )
        security.decrypt_strava_secrets(
            profile_dict=profile_dict,
            enc_key=self.config.encryption_key,
        )
        return settings.UserProfile.from_dict(profile_dict)

    def create_profile(
        self, user_profile: settings.UserProfile
    ) -> settings.UserProfile:
        # ensure user ID
        user_profile.user_id = user_profile.user_id or str(uuid.uuid4())

        data_dict = user_profile.to_dict()
        security.encrypt_strava_secrets(
            data_dict=data_dict, enc_key=self.config.encryption_key
        )

        # save profile to filesystem
        persistences.save_json(
            file_path=self.user_settings_path(user_profile.user_id),
            data_dict=data_dict,
        )

        # NOTE: cache is NOT accessed here to avoid initialization issues
        # during user registration. Cache will be initialized on first actual use.
        return user_profile

    def update_profile(
        self, user_profile: settings.UserProfile
    ) -> settings.UserProfile:
        self._cache.user(user_profile.user_id).evict_profile_stats()
        return self.create_profile(user_profile)

    def list_profiles(self) -> list[str]:
        """List user profiles and return user IDs."""
        if self.data_dir.exists():
            # list directories
            wild = self.data_dir.glob("*")
            return [str(d.stem) for d in wild if d.is_dir()]

        return []

    def list_profile_names(self, auto_login: bool = False) -> dict[str, str]:
        """List user profiles and return usernames.

        Parameters
        ----------
        auto_login : bool
            When True, return only profiles with auto-login enabled.

        Returns
        -------
        dict[str, str]
            Username to user ID map.

        """
        user_names = {}
        if self.data_dir.exists():
            # list directories
            wild = self.data_dir.glob("*")
            for d in wild:
                if d.is_dir():
                    profile_path = d / JsonUsersDataset.FILE_USER_SETTINGS
                    if profile_path.exists():
                        profile_dict = persistences.load_json(profile_path)
                        if auto_login and not profile_dict.get(
                            settings.UserProfile.KEY_AUTO_LOGIN, False
                        ):
                            continue
                        # user_id must be UNIQUE, display name does NOT
                        user_names[profile_dict[settings.UserProfile.KEY_USER]] = (
                            profile_dict[settings.UserProfile.KEY_USER_ID]
                        )

        return user_names

    def _build_profile_stats(
        self, user_id: str, dataset_name: str
    ) -> stats.UserProfileStats:
        profile_stats = stats.UserProfileStats()

        a_dict: dict = self.all_activities(user_id=user_id, dataset_name=dataset_name)

        if a_dict:
            activities = a_dict.values()

            # lookup last weight - ensure activities are SORTED
            self.logger.info("LATEST weight lookup:")
            activities = sorted(activities, key=lambda aa: aa.when, reverse=False)
            for a in reversed(activities):
                if a.weight:
                    self.logger.info(f"    USING {a.when}: {a.weight}")
                    profile_stats.weight = a.weight
                    break

            profile = self.profile(user_id)
            if profile.height and profile_stats.weight:
                # BMI
                profile_stats.bmi = float(profile_stats.weight) / (
                    float(profile.height) * float(profile.height)
                )
                if profile_stats.bmi < stats.UserProfileStats.THRESHOLD_BMI_MIN:
                    profile_stats.bmi_rank = "underweight"
                elif profile_stats.bmi > stats.UserProfileStats.THRESHOLD_BMI_MAX:
                    profile_stats.bmi_rank = "overweight"
                else:
                    profile_stats.bmi_rank = "normal"
                self.logger.info(f"BMI rank set to: {profile_stats.bmi_rank}")

                # BMR
                profile_stats.bmr = (
                    (10.0 * profile_stats.weight)
                    + (6.25 * float(profile.height) * 100.0)
                    - (5.0 * float(profile.age))
                    + 5.0
                )
            else:
                profile_stats.bmi = 0.0
                profile_stats.bmi_rank = "unknown"
                profile_stats.bmr = 0.0

        self._cache.user(user_id).set_profile_stats(profile_stats)

        return profile_stats

    #
    # activities
    #

    def create_activities_dataset(self, user_id: str, dataset_name: str):
        self._activities_dataset.create_dataset(
            user_id=user_id, dataset_name=dataset_name
        )

    def delete_activities_dataset(self, user_id: str, dataset_name: str):
        self._activities_dataset.delete_dataset(
            user_id=user_id, dataset_name=dataset_name
        )

    def user_activities_path(
        self,
        user_id: str = commons.DEFAULT_USER_NAME,
        dataset_name: str = FILE_DATASET_MAIN,
    ) -> pathlib.Path:
        user_dir = self.user_dir(user_id)
        return user_dir / f"{dataset_name}.{persistences.EXT_JSON}"

    def _load_all_activities(
        self,
        user_id: str = commons.DEFAULT_USER_NAME,
        dataset_name: str = FILE_DATASET_MAIN,
    ) -> dict[str, entities.ActivityEntity]:
        return self._activities_dataset.list_activities(
            user_id=user_id, dataset_name=dataset_name
        )

    def create_activity(
        self,
        user_id: str,
        dataset_name: str,
        entity: entities.ActivityEntity,
        check_column: str = "",
        check_value=None,
        check_override: bool = True,
    ) -> entities.ActivityEntity:
        return self._activities_dataset.create_activity(
            user_id=user_id,
            dataset_name=dataset_name,
            entity=entity,
        )

    def create_activities(
        self,
        user_id: str,
        dataset_name: str,
        entity_list: list[entities.ActivityEntity],
    ) -> list[entities.ActivityEntity]:
        return self._activities_dataset.create_activities(
            user_id=user_id,
            dataset_name=dataset_name,
            entity_list=entity_list,
        )

    def update_activity(
        self, user_id: str, dataset_name: str, entity: entities.ActivityEntity
    ) -> entities.ActivityEntity:
        return self._activities_dataset.update_activity(
            user_id=user_id,
            dataset_name=dataset_name,
            entity=entity,
        )

    def update_activities(
        self, user_id: str, dataset_name: str, activities: list[entities.ActivityEntity]
    ):
        return self._activities_dataset.update_activities(
            user_id=user_id, dataset_name=dataset_name, activities=activities
        )

    def delete_activity(self, user_id: str, dataset_name: str, key: str):
        result = self._activities_dataset.delete_activity(
            user_id=user_id,
            dataset_name=dataset_name,
            key=key,
        )
        self.delete_bookmark(user_id=user_id, activity_key=key)
        return result

    def get_activity(
        self, user_id: str, dataset_name: str, key: str
    ) -> entities.ActivityEntity:
        return self._activities_dataset.get_activity(
            user_id=user_id,
            dataset_name=dataset_name,
            key=key,
        )

    def export_activities(self, user_id: str, dataset_name: str) -> str:
        return self._activities_dataset.export_activities(
            user_id=user_id, dataset_name=dataset_name
        )

    #
    # activity types
    #

    def _create_activity_types(self, user_id: str):
        activity_types = settings.UserActivityTypes(
            activity_types=settings.UserActivityTypes.bootstrap()
        )
        persistences.save_json(
            file_path=self.user_activity_types_path(user_id),
            data_dict=activity_types.to_dict_dict(),
        )

    def _load_activity_types(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserActivityTypes:
        path = self.user_activity_types_path(user_id)
        if not path.exists():
            raise ValueError(
                f"Activity types path for user '{user_id}' does not exist: {path}"
            )
        activity_types = settings.UserActivityTypes.from_dict_dict(
            persistences.load_json(path)
        )

        # refresh stats
        activity_types.reset_counts()
        if dataset_name:
            activities = self.all_activities(
                user_id=user_id, dataset_name=dataset_name
            ).values()
            for a in activities:
                if a.activity_type_key in activity_types.activity_types_by_key:
                    activity_types.activity_types_by_key[a.activity_type_key].count += 1
                else:
                    self.logger.error(
                        f"Activity type '{a.activity_type_key}' not found in activity "
                        f"types cache! (activity key: {a.key})"
                    )

        return activity_types

    def _save_activity_types(
        self, user_id: str, activity_types: settings.UserActivityTypes
    ) -> settings.UserActivityTypes:
        self._cache.user(user_id).set_activity_types(activity_types)
        persistences.save_json(
            file_path=self.user_activity_types_path(user_id),
            data_dict=activity_types.to_dict_dict(),
        )

        return activity_types

    def create_activity_type(
        self, user_id: str, activity_type: settings.ActivityType
    ) -> settings.ActivityType:
        activity_types = self.list_activity_types(user_id)
        activity_types.add_activity_type(activity_type)
        self._save_activity_types(user_id=user_id, activity_types=activity_types)

        return activity_type

    def update_activity_type(
        self, user_id: str, activity_type: settings.ActivityType
    ) -> settings.ActivityType:
        activity_types = self.list_activity_types(user_id)
        activity_types.update(activity_type)
        self._save_activity_types(user_id=user_id, activity_types=activity_types)

        return activity_type

    def delete_activity_type(self, user_id: str, key: str):
        activity_types = self.list_activity_types(user_id)
        activity_types.delete(key)
        self._save_activity_types(user_id=user_id, activity_types=activity_types)

    def _build_activity_types_stats(
        self, user_id: str, dataset_name: str
    ) -> stats.UserActivityTypesStats:
        activity_types_stats = stats.UserActivityTypesStats()

        a_dict: dict = self.all_activities(user_id=user_id, dataset_name=dataset_name)
        if a_dict:
            for a in a_dict.values():
                if a.activity_type_key:
                    at_stat = activity_types_stats.stats(a.activity_type_key)
                    if not at_stat:
                        at_stat = stats.ActivityTypeStats()
                        activity_types_stats.add_stats(a.activity_type_key, at_stat)
                    at_stat.count += 1
                    at_stat.total_distance += a.distance
                    at_stat.total_duration += a.duration_seconds

        self._cache.user(user_id).set_activity_types_stats(activity_types_stats)

        return activity_types_stats

    #
    # gear
    #

    def _create_gears(self, user_id: str):
        persistences.save_json(
            file_path=self.user_gear_path(user_id),
            data_dict=settings.UserGear(gear=[]).to_dict(),
        )

    def _load_gears(self, user_id: str, dataset_name: str = "") -> settings.UserGear:
        path = self.user_gear_path(user_id)
        if not path.exists():
            raise ValueError(f"Gear path for user '{user_id}' does not exist: {path}")
        gear = settings.UserGear.from_dict_dict(persistences.load_json(path))

        return gear

    def _save_gears(self, user_id: str, gears: settings.UserGear) -> settings.UserGear:
        self._cache.user(user_id).set_gear(gears)
        self._cache.user(user_id).evict_gear_stats()

        persistences.save_json(
            file_path=self.user_gear_path(user_id),
            data_dict=gears.to_dict_dict(),
        )

        return gears

    def create_gear(
        self, user_id: str, gear: settings.Gear, dataset_name: str
    ) -> settings.Gear:
        gears = self.list_gear(user_id=user_id, dataset_name=dataset_name)
        gears.add_gear(gear)
        self._save_gears(user_id=user_id, gears=gears)

        return gear

    def update_gear(
        self, user_id: str, gear: settings.Gear, dataset_name: str
    ) -> settings.Gear:
        gears = self.list_gear(user_id=user_id, dataset_name=dataset_name)
        gears.update(gear)
        self._save_gears(user_id=user_id, gears=gears)

        return gear

    def delete_gear(self, user_id: str, key: str, dataset_name: str):
        gears = self.list_gear(user_id=user_id, dataset_name=dataset_name)
        gears.delete(key)
        self._save_gears(user_id=user_id, gears=gears)

    def _build_gear_stats(self, user_id: str, dataset_name: str) -> stats.UserGearStats:
        # gear stats are extracted from activities stats
        user_gear_stats = stats.UserGearStats()
        activities_stats = self.activities_stats(
            user_id=user_id, dataset_name=dataset_name
        )

        user_gear = self.list_gear(user_id=user_id, dataset_name=dataset_name)

        # populate UserGearStats from activities stats
        for g in user_gear.gear.values():
            gear_stat = stats.GearStats()

            gear_stat.stat_use = activities_stats.gear_count.get(g.key, 0)

            ts = activities_stats.gear_used_from.get(g.key, None)
            gear_stat.stat_from = f"{ts[0]}-{ts[1]:02}-{ts[2]:02}" if ts else ""
            ts = activities_stats.gear_used_to.get(g.key, None)
            gear_stat.stat_to = f"{ts[0]}-{ts[1]:02}-{ts[2]:02}" if ts else ""

            gear_stat.stat_meters = activities_stats.total_m_per_gear.get(g.key, 0)
            gear_stat.stat_seconds = activities_stats.total_seconds_per_gear.get(
                g.key, 0
            )
            gear_stat.stat_km_str = f"{gear_stat.stat_meters / 1000:.0f}"

            hours, remainder = divmod(gear_stat.stat_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            gear_stat.stat_duration_str = f"{hours:02d}h{minutes:02d}m{seconds:02d}s"

            user_gear_stats.add_stats(g.key, gear_stat)

        self._cache.user(user_id).set_gear_stats(user_gear_stats)

        return user_gear_stats

    #
    # Strava gear ~ gear IDs exported from Strava & used by the given user
    #

    def _create_strava_gears(self, user_id: str):
        persistences.save_json(
            file_path=self.user_strava_gear_path(user_id),
            data_dict=settings.StravaUserGear(gears=[]).to_list(),
        )

    def _load_strava_gears(self, user_id: str) -> settings.StravaUserGear:
        path = self.user_strava_gear_path(user_id)
        if not path.exists():
            raise ValueError(
                f"Strava gear path for user '{user_id}' does not exist: {path}"
            )

        gear = settings.StravaUserGear(
            user_profile=self.profile(user_id),  # Strava auth token & user ID
            gears=persistences.load_json(path),
            logger=self.logger,
        )

        return gear

    def _save_strava_gears(self, user_id: str, strava_gears: settings.StravaUserGear):
        path = self.user_strava_gear_path(user_id)

        persistences.save_json(file_path=path, data_dict=strava_gears.gears)

    def update_strava_gears(
        self, user_id: str, strava_gears: settings.StravaUserGear
    ) -> settings.StravaUserGear:
        self._save_strava_gears(user_id=user_id, strava_gears=strava_gears)
        return strava_gears

    #
    # outfits
    #

    def _create_outfits(self, user_id: str):
        persistences.save_json(
            file_path=self.user_outfits_path(user_id),
            data_dict=settings.UserOutfits().to_dict(),
        )

    def _load_outfits(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserOutfits:
        path = self.user_outfits_path(user_id)
        if not path.exists():
            raise ValueError(
                f"Outfits path for user '{user_id}' does not exist: {path}"
            )
        outfits = settings.UserOutfits.from_dict(persistences.load_json(path))

        return outfits

    def _save_outfits(
        self, user_id: str, outfits: settings.UserOutfits
    ) -> settings.UserOutfits:
        self._cache.user(user_id).set_outfits(outfits)
        persistences.save_json(
            file_path=self.user_outfits_path(user_id),
            data_dict=outfits.to_dict(),
        )

        return outfits

    def list_outfits(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserOutfits:
        outfits = super().list_outfits(user_id=user_id, dataset_name=dataset_name)

        # reset counts as they are NOT persisted (they are calculated from activities)
        for outfit in outfits.outfits_by_key.values():
            outfit.count = 0

        if dataset_name:
            activities = self.all_activities(
                user_id=user_id, dataset_name=dataset_name
            ).values()
            for a in activities:
                if hasattr(a, "outfit") and a.outfit:
                    if a.outfit in outfits.outfits_by_key:
                        outfits.outfits_by_key[a.outfit].count += 1

        return outfits

    def _build_outfits_stats(
        self, user_id: str, dataset_name: str
    ) -> stats.UserOutfitsStats:
        outfits_stats = stats.UserOutfitsStats()

        a_dict: dict = self.all_activities(user_id=user_id, dataset_name=dataset_name)
        if a_dict:
            for a in a_dict.values():
                if hasattr(a, "outfit") and a.outfit:
                    o_stat = outfits_stats.stats(a.outfit)
                    if not o_stat:
                        o_stat = stats.OutfitStats()
                        outfits_stats.add_stats(a.outfit, o_stat)
                    o_stat.count += 1
                    o_stat.total_distance += a.distance
                    o_stat.total_duration += a.duration_seconds

        self._cache.user(user_id).set_outfits_stats(outfits_stats)

        return outfits_stats

    def create_outfit(self, user_id: str, outfit: settings.Outfit) -> settings.Outfit:
        outfits = self.list_outfits(user_id)
        outfits.add(outfit)
        self._save_outfits(user_id=user_id, outfits=outfits)

        return outfit

    def update_outfit(self, user_id: str, outfit: settings.Outfit) -> settings.Outfit:
        outfits = self.list_outfits(user_id)
        outfits.update(outfit)
        self._save_outfits(user_id=user_id, outfits=outfits)

        return outfit

    def delete_outfit(self, user_id: str, key: str):
        outfits = self.list_outfits(user_id)
        outfits.delete(key)
        self._save_outfits(user_id=user_id, outfits=outfits)

    #
    # activity bookmarks
    #

    def _create_bookmarks(self, user_id: str):
        persistences.save_json(
            file_path=self.user_bookmarks_path(user_id),
            data_dict=settings.UserBookmarks().to_dict(),
        )

    def _load_bookmarks(self, user_id: str) -> settings.UserBookmarks:
        path = self.user_bookmarks_path(user_id)
        if not path.exists():
            # accounts registered before the bookmarks feature existed have no
            # bookmarks file yet - self-heal instead of failing every request
            self._create_bookmarks(user_id=user_id)
            return settings.UserBookmarks()
        return settings.UserBookmarks.from_dict(persistences.load_json(path))

    def _save_bookmarks(
        self, user_id: str, bookmarks: settings.UserBookmarks
    ) -> settings.UserBookmarks:
        self._cache.user(user_id).set_bookmarks(bookmarks)
        persistences.save_json(
            file_path=self.user_bookmarks_path(user_id),
            data_dict=bookmarks.to_dict(),
        )

        return bookmarks

    def create_bookmark(
        self, user_id: str, activity_key: str
    ) -> settings.UserBookmarks:
        bookmarks = self.list_bookmarks(user_id)
        bookmarks.add(activity_key)
        return self._save_bookmarks(user_id=user_id, bookmarks=bookmarks)

    def delete_bookmark(
        self, user_id: str, activity_key: str
    ) -> settings.UserBookmarks:
        bookmarks = self.list_bookmarks(user_id)
        bookmarks.delete(activity_key)
        return self._save_bookmarks(user_id=user_id, bookmarks=bookmarks)

    def move_bookmark(
        self, user_id: str, activity_key: str, direction: str
    ) -> settings.UserBookmarks:
        bookmarks = self.list_bookmarks(user_id)
        if direction == "up":
            bookmarks.move_up(activity_key)
        elif direction == "down":
            bookmarks.move_down(activity_key)
        else:
            raise ValueError(f"Invalid bookmark move direction: {direction}")
        return self._save_bookmarks(user_id=user_id, bookmarks=bookmarks)

    #
    # component templates
    #

    def _create_component_templates(self, user_id: str):
        templates = settings.UserComponentTemplates()
        for tmpl in settings.COMPONENT_TEMPLATES:
            new_tmpl = settings.ComponentTemplate(
                name=tmpl.name,
                category=tmpl.category,
                default_service_km=tmpl.default_service_km,
                default_service_hours=tmpl.default_service_hours,
                default_service_months=tmpl.default_service_months,
                notes=tmpl.notes,
                key=str(uuid.uuid4()),
            )
            templates.add(new_tmpl)
        persistences.save_json(
            file_path=self.user_component_templates_path(user_id),
            data_dict=templates.to_dict(),
        )

    def _load_component_templates(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserComponentTemplates:
        path = self.user_component_templates_path(user_id)
        if not path.exists():
            self._create_component_templates(user_id=user_id)
        return settings.UserComponentTemplates.from_dict(persistences.load_json(path))

    def _save_component_templates(
        self,
        user_id: str,
        templates: settings.UserComponentTemplates,
    ) -> settings.UserComponentTemplates:
        self._cache.user(user_id).set_component_templates(templates)
        persistences.save_json(
            file_path=self.user_component_templates_path(user_id),
            data_dict=templates.to_dict(),
        )
        return templates

    def create_component_template(
        self,
        user_id: str,
        template: settings.ComponentTemplate,
    ) -> settings.ComponentTemplate:
        templates = self.list_component_templates(user_id)
        templates.add(template)
        self._save_component_templates(user_id=user_id, templates=templates)
        return template

    def update_component_template(
        self,
        user_id: str,
        template: settings.ComponentTemplate,
    ) -> settings.ComponentTemplate:
        templates = self.list_component_templates(user_id)
        templates.update(template)
        self._save_component_templates(user_id=user_id, templates=templates)
        return template

    def delete_component_template(self, user_id: str, key: str) -> None:
        templates = self.list_component_templates(user_id)
        templates.delete(key)
        self._save_component_templates(user_id=user_id, templates=templates)

    #
    # goals
    #

    def _create_goals(self, user_id: str):
        persistences.save_json(
            file_path=self.user_goals_path(user_id),
            data_dict=settings.UserGoals().to_dict(),
        )

    def _load_goals(self, user_id: str, dataset_name: str = "") -> settings.UserGoals:
        path = self.user_goals_path(user_id)
        if not path.exists():
            raise ValueError(f"goals path for user '{user_id}' does not exist: {path}")
        goals = settings.UserGoals.from_dict(persistences.load_json(path))

        return goals

    def _save_goals(
        self, user_id: str, goals: settings.UserGoals
    ) -> settings.UserGoals:
        self._cache.user(user_id).set_goals(goals)
        persistences.save_json(
            file_path=self.user_goals_path(user_id),
            data_dict=goals.to_dict(),
        )

        return goals

    def create_goal(self, user_id: str, goal: settings.Goal) -> settings.Goal:
        goals = self.list_goals(user_id)
        goals.add(goal)
        self._save_goals(user_id=user_id, goals=goals)

        return goal

    def update_goal(self, user_id: str, goal: settings.Goal) -> settings.Goal:
        goals = self.list_goals(user_id)
        goals.update(goal)
        self._save_goals(user_id=user_id, goals=goals)

        return goal

    def delete_goal(self, user_id: str, key: str):
        goals = self.list_goals(user_id)
        goals.delete(key)
        self._save_goals(user_id=user_id, goals=goals)

    #
    # exercises
    #

    def _create_exercises(self, user_id: str):
        exercises = settings.UserExercises(exercises=settings.UserExercises.bootstrap())
        persistences.save_json(
            file_path=self.user_exercises_path(user_id),
            data_dict=exercises.to_dict_dict(),
        )

    def _load_exercises(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserExercises:
        path = self.user_exercises_path(user_id)
        if not path.exists():
            raise ValueError(
                f"Exercises path for user '{user_id}' does not exist: {path}"
            )
        exercises = settings.UserExercises.from_dict_dict(persistences.load_json(path))
        return exercises

    def _save_exercises(
        self, user_id: str, exercises: settings.UserExercises
    ) -> settings.UserExercises:
        self._cache.user(user_id).set_exercises(exercises)
        self._cache.user(user_id).evict_exercises_stats()

        persistences.save_json(
            file_path=self.user_exercises_path(user_id),
            data_dict=exercises.to_dict_dict(),
        )

        return exercises

    def create_exercise(
        self, user_id: str, exercise: settings.Exercise
    ) -> settings.Exercise:
        exercises = self.list_exercises(user_id)
        exercises.add_exercise(exercise)
        self._save_exercises(user_id=user_id, exercises=exercises)

        return exercise

    def update_exercise(
        self, user_id: str, exercise: settings.Exercise
    ) -> settings.Exercise:
        exercises = self.list_exercises(user_id)
        exercises.update(exercise)
        self._save_exercises(user_id=user_id, exercises=exercises)

        return exercise

    def delete_exercise(self, user_id: str, key: str):
        exercises = self.list_exercises(user_id)
        exercises.delete(key)
        self._save_exercises(user_id=user_id, exercises=exercises)

    def _build_exercises_stats(
        self, user_id: str, dataset_name: str
    ) -> stats.UserExercisesStats:
        exercises_stats = stats.UserExercisesStats()

        a_dict: dict = self.all_activities(user_id=user_id, dataset_name=dataset_name)
        if a_dict:
            for a in a_dict.values():
                if a.exercises:
                    for ee in a.exercises:
                        e = exercises_stats.stats(ee.name)
                        if not e:
                            e = stats.ExerciseStats()
                            exercises_stats.add_stats(ee.name, e)
                        e.count += 1
                        volume = ee.weight * ee.series * ee.repetitions
                        e.total_volume += volume
                        e.total_repetitions += ee.series * ee.repetitions
                        if ee.weight > e.max_weight:
                            e.max_weight = ee.weight

        self._cache.user(user_id).set_exercises_stats(exercises_stats)

        return exercises_stats

    #
    # laps
    #

    def _create_laps(self, user_id: str):
        persistences.save_json(
            file_path=self.user_laps_path(user_id),
            data_dict=settings.UserLaps(laps=[]).to_dict(),
        )

    def _load_laps(self, user_id: str, dataset_name: str = "") -> settings.UserLaps:
        path = self.user_laps_path(user_id)
        if not path.exists():
            raise ValueError(f"Laps path for user '{user_id}' does not exist: {path}")
        laps = settings.UserLaps.from_dict_dict(persistences.load_json(path))
        return laps

    def _save_laps(self, user_id: str, laps: settings.UserLaps) -> settings.UserLaps:
        self._cache.user(user_id).set_laps(laps)

        persistences.save_json(
            file_path=self.user_laps_path(user_id),
            data_dict=laps.to_dict_dict(),
        )

        return laps

    def create_lap(
        self, user_id: str, lap: settings.Lap, dataset_name: str = ""
    ) -> settings.Lap:
        laps = self.list_laps(user_id, dataset_name)
        laps.add_lap(lap)
        self._save_laps(user_id=user_id, laps=laps)

        return lap

    def update_lap(
        self, user_id: str, lap: settings.Lap, dataset_name: str = ""
    ) -> settings.Lap:
        laps = self.list_laps(user_id, dataset_name)
        laps.update(lap)
        self._save_laps(user_id=user_id, laps=laps)

        return lap

    def delete_lap(self, user_id: str, key: str, dataset_name: str = ""):
        laps = self.list_laps(user_id, dataset_name)
        laps.delete(key)
        self._save_laps(user_id=user_id, laps=laps)

    #
    # symptoms
    #

    def _create_symptoms(self, user_id: str):
        symptoms = settings.UserSymptoms(symptoms=settings.UserSymptoms.bootstrap())
        persistences.save_json(
            file_path=self.user_symptoms_path(user_id),
            data_dict=symptoms.to_dict_dict(),
        )

    def _load_symptoms(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserSymptoms:
        path = self.user_symptoms_path(user_id)
        if not path.exists():
            raise ValueError(
                f"Symptoms path for user '{user_id}' does not exist: {path}"
            )
        symptoms = settings.UserSymptoms.from_dict_dict(persistences.load_json(path))
        return symptoms

    def _save_symptoms(
        self, user_id: str, symptoms: settings.UserSymptoms
    ) -> settings.UserSymptoms:
        self._cache.user(user_id).set_symptoms(symptoms)
        persistences.save_json(
            file_path=self.user_symptoms_path(user_id),
            data_dict=symptoms.to_dict_dict(),
        )

        return symptoms

    def create_symptom(
        self, user_id: str, symptom: settings.Symptom
    ) -> settings.Symptom:
        symptoms = self.list_symptoms(user_id)
        symptoms.add_symptom(symptom)
        self._save_symptoms(user_id=user_id, symptoms=symptoms)

        return symptom

    def update_symptom(
        self, user_id: str, symptom: settings.Symptom
    ) -> settings.Symptom:
        symptoms = self.list_symptoms(user_id)
        symptoms.update(symptom)
        self._save_symptoms(user_id=user_id, symptoms=symptoms)

        return symptom

    def delete_symptom(self, user_id: str, key: str):
        symptoms = self.list_symptoms(user_id)
        symptoms.delete(key)
        self._save_symptoms(user_id=user_id, symptoms=symptoms)

    def _build_symptoms_stats(
        self, user_id: str, dataset_name: str
    ) -> stats.UserSymptomsStats:
        symptoms_stats = stats.UserSymptomsStats()

        a_dict: dict = self.all_activities(user_id=user_id, dataset_name=dataset_name)
        if a_dict:
            for a in a_dict.values():
                if a.activity_type_key in [commons.AT_SICK, commons.AT_INJURED]:
                    if a.sickness_symptoms:
                        for ss in a.sickness_symptoms:
                            s = symptoms_stats.stats(ss.symptom)
                            if not s:
                                s = stats.SymptomStats()
                                symptoms_stats.add_stats(ss.symptom, s)
                            s.count += 1
                            s.total_health += ss.health
                            if s.count > 0:
                                s.avg_health = s.total_health / s.count

        self._cache.user(user_id).set_symptoms_stats(symptoms_stats)

        return symptoms_stats

    def _build_laps_stats(self, user_id: str, dataset_name: str) -> stats.UserLapsStats:
        laps_stats = stats.UserLapsStats()

        a_dict: dict = self.all_activities(user_id=user_id, dataset_name=dataset_name)
        if a_dict:
            for a in a_dict.values():
                if a.laps:
                    for lap in a.laps:
                        lap_stat = laps_stats.stats(lap.name)
                        if not lap_stat:
                            lap_stat = stats.LapStats()
                            laps_stats.add_stats(lap.name, lap_stat)
                        lap_stat.count += 1
                        lap_stat.total_distance += lap.distance
                        lap_stat.total_duration += lap.duration

        self._cache.user(user_id).set_laps_stats(laps_stats)

        return laps_stats

    #
    # tasks
    #

    def user_tasks_dir(self, user_id: str) -> pathlib.Path:
        tasks_dir = self.user_dir(user_id) / config.MytralPersistenceFsConfig.DIR_TASKS
        tasks_dir.mkdir(parents=True, exist_ok=True)
        return tasks_dir

    def user_task_json_path(self, user_id: str, task_id: str) -> pathlib.Path:
        return self.user_tasks_dir(user_id) / f"task-{task_id}.json"

    def user_task_log_path(self, user_id: str, task_id: str) -> pathlib.Path:
        return self.user_tasks_dir(user_id) / f"task-{task_id}.log"

    def save_task(self, user_id: str, task_dict: dict) -> None:
        task_id = task_dict["key"]
        json_path = self.user_task_json_path(user_id, task_id)
        persistences.save_json(file_path=json_path, data_dict=task_dict)

    def append_task_logs(
        self, user_id: str, task_id: str, log_entries: list[str]
    ) -> None:
        log_path = self.user_task_log_path(user_id, task_id)
        with open(log_path, "a") as f:
            for entry in log_entries:
                f.write(entry + "\n")

    def load_task(self, user_id: str, task_id: str) -> dict:
        json_path = self.user_task_json_path(user_id, task_id)
        return persistences.load_json(json_path)

    def load_task_logs(self, user_id: str, task_id: str, tail: int = 100) -> list[str]:
        log_path = self.user_task_log_path(user_id, task_id)
        if not log_path.exists():
            return []
        with open(log_path, "r") as f:
            lines = f.readlines()
        return [line.strip() for line in lines[-tail:]]

    def list_task_files(self, user_id: str) -> list[pathlib.Path]:
        tasks_dir = self.user_tasks_dir(user_id)
        if not tasks_dir.exists():
            return []
        return list(tasks_dir.glob("task-*.json"))

    def delete_task_files(self, user_id: str, task_id: str) -> None:
        json_path = self.user_task_json_path(user_id, task_id)
        log_path = self.user_task_log_path(user_id, task_id)
        if json_path.exists():
            json_path.unlink()
        if log_path.exists():
            log_path.unlink()


# self-registration to user dataset do
dataset.user_dataset_registry.add_implementation(
    persistence_type=config.PersistenceType.FILESYSTEM,
    user_dataset=JsonUsersDataset(),
)
