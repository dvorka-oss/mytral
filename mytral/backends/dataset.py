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

"""MyTraL persistence stack:

- MyTraL cache @ MyTraL dataset
  - in memory
  - (Memcached)
  - ...

- MyTraL dataset @ MyTraL database
  - persistence AGNOSTIC data layer
  - do:
      - filesystem (JSON) + BLOB store (Parquet)
      - (relational DB)
      - (document DB)
      - (datatable)

- MyTraL persistence
  - helper methods for:
      - filesystem
      - memory
      - DB

"""

import abc
import datetime
import pathlib
import uuid

from mytral import commons
from mytral import config
from mytral import loggers
from mytral import profilers
from mytral import settings
from mytral import stats
from mytral import views
from mytral.backends import entities


class UserDataset(abc.ABC):
    """User dataset - activities, gear, symptoms, exercise types ~ all user data.

    - persistence type agnostic (DB, file, memory)
    - smart (global) cache eviction control

    """

    def __init__(self):
        """User dataset constructor."""
        self.config = None
        self.logger = None
        self._cache = None

    def configure(
        self,
        mytral_config: config.MytralConfig,
        logger: loggers.MytralLogger | None = None,
    ):
        """Configure dataset with MyTraL configuration.

        Parameters
        ----------
        mytral_config : MytralConfig
            User cache instance.
        logger :
            MyTraL logger.

        """
        self.config = mytral_config
        self.logger = logger or loggers.MytralStructLogger()

    @abc.abstractmethod
    def create_key(self) -> str:
        """Create a new unique key."""
        raise NotImplementedError

    @abc.abstractmethod
    def register_new_user(
        self,
        user_name: str = commons.DEFAULT_USER_NAME,
        user_id: str = "",
        password_enc: str = "",
    ):
        """Create new user (sandbox / entries / tables).

        Parameters
        ----------
        user_name : str
            Username.
        user_id : str
            Unique user ID.
        password_enc : str
            Encrypted password.

        """
        raise NotImplementedError

    @abc.abstractmethod
    def cache_evict(self, user_id):
        """Evict cache of the given user."""
        raise NotImplementedError

    def cache_memory_size(self, user_id):
        return self._cache.user(user_id).memory_size()

    #
    # export
    #

    @abc.abstractmethod
    def export(
        self, user_id: str, archive_path: pathlib.Path, export_format: str = "zip"
    ):
        """Export all data."""
        raise NotImplementedError

    #
    # user profiles
    #

    @abc.abstractmethod
    def _load_profile(self, user_id: str) -> settings.UserProfile:
        """Load user profile."""
        raise NotImplementedError

    @abc.abstractmethod
    def create_profile(
        self, user_profile: settings.UserProfile
    ) -> settings.UserProfile:
        raise NotImplementedError

    @abc.abstractmethod
    def update_profile(
        self, user_profile: settings.UserProfile
    ) -> settings.UserProfile:
        raise NotImplementedError

    def profile(self, user_id: str) -> settings.UserProfile:
        """Get user profile."""
        return self._cache.user(user_id).profile() or self._cache.user(
            user_id
        ).set_profile(profile=self._load_profile(user_id))

    @abc.abstractmethod
    def list_profiles(self) -> list[str]:
        """List all user IDs."""
        raise NotImplementedError

    @abc.abstractmethod
    def list_profile_names(self, auto_login: bool = False) -> dict[str, str]:
        """List all usernames.

        Parameters
        ----------
        auto_login : bool
            When True, return only profiles with auto-login enabled.

        Returns
        -------
        dict[str, str]
             Username to user ID map.

        """
        raise NotImplementedError

    @abc.abstractmethod
    def _build_profile_stats(
        self, user_id: str, dataset_name: str
    ) -> stats.UserProfileStats:
        raise NotImplementedError

    def profile_stats(self, user_id: str, dataset_name: str) -> stats.UserProfileStats:
        return self._cache.user(user_id).profile_stats() or self._cache.user(
            user_id
        ).set_profile_stats(
            profile_stats=self._build_profile_stats(
                user_id=user_id, dataset_name=dataset_name
            )
        )

    #
    # activities
    #

    def create_activities_dataset(self, user_id: str, dataset_name: str):
        raise NotImplementedError

    def delete_activities_dataset(self, user_id: str, dataset_name: str):
        raise NotImplementedError

    @abc.abstractmethod
    def _load_all_activities(
        self, user_id: str, dataset_name: str
    ) -> dict[str, entities.ActivityEntity]:
        """Load all user activities."""
        raise NotImplementedError

    @abc.abstractmethod
    def create_activity(
        self,
        user_id: str,
        dataset_name: str,
        entity: entities.ActivityEntity,
        check_column: str = "",
        check_value=None,
        check_override: bool = True,
    ) -> entities.ActivityEntity:
        raise NotImplementedError

    @abc.abstractmethod
    def create_activities(
        self,
        user_id: str,
        dataset_name: str,
        entity_list: list[entities.ActivityEntity],
    ) -> list[entities.ActivityEntity]:
        raise NotImplementedError

    @abc.abstractmethod
    def update_activity(
        self, user_id: str, dataset_name: str, entity: entities.ActivityEntity
    ) -> entities.ActivityEntity:
        raise NotImplementedError

    @abc.abstractmethod
    def update_activities(
        self, user_id: str, dataset_name: str, activities: list[entities.ActivityEntity]
    ):
        """Bulk update of activities:

        - activities are clustered by year
        - activities w/ the same year are routed to their target dataset files for year

        """
        raise NotImplementedError

    @abc.abstractmethod
    def delete_activity(self, user_id: str, dataset_name: str, key: str):
        raise NotImplementedError

    @abc.abstractmethod
    def get_activity(
        self, user_id: str, dataset_name: str, key: str
    ) -> entities.ActivityEntity:
        raise NotImplementedError

    def all_activities(
        self, user_id: str, dataset_name: str
    ) -> dict[str, entities.ActivityEntity]:
        """Get all user activities."""
        return self._cache.user(user_id).activities(
            dataset_name=dataset_name
        ) or self._cache.user(user_id).set_activities(
            activities=self._load_all_activities(
                user_id=user_id, dataset_name=dataset_name
            ),
            dataset_name=dataset_name,
        )

    @staticmethod
    def sorted_activities(
        activities: dict[str, entities.ActivityEntity],
    ) -> list[entities.ActivityEntity]:
        return sorted(activities.values(), reverse=True, key=lambda x: x.when)

    def list_activities(
        self,
        user_id: str,
        dataset_name: str,
        filter_year: int = 0,
        filter_month: int = 0,
        filter_day: int = 0,
        skip_future: bool = False,
        skip_meta: bool = False,
        sort_by_when: bool = False,
    ) -> list[entities.ActivityEntity]:
        """Filter and list user activities."""

        def _is_future(a: entities.ActivityEntity) -> bool:
            today = datetime.datetime.now()

            if (
                a.when_year > today.year
                or (a.when_year >= today.year and a.when_month > today.month)
                or (
                    a.when_year >= today.year
                    and a.when_month >= today.month
                    and a.when_day > today.day
                )
            ):
                return True

            return False

        activity_types = None
        if skip_meta:
            activity_types = self.list_activity_types(user_id)

        try:
            filter_year = int(filter_year) if filter_year is not None else 0
        except ValueError:
            filter_year = 0

        activities = [
            activity
            for activity in self.all_activities(
                user_id=user_id, dataset_name=dataset_name
            ).values()
            if (
                (not filter_year or activity.when_year == filter_year)
                and (not filter_month or activity.when_month == filter_month)
                and (not filter_day or activity.when_day == filter_day)
                and (not skip_future or not _is_future(activity))
                and (
                    not skip_meta
                    or not activity_types.is_meta(activity.activity_type_key)
                )
            )
        ]

        if sort_by_when:
            activities = sorted(activities, reverse=True, key=lambda x: x.when)

        return activities

    @abc.abstractmethod
    def export_activities(
        self,
        user_id: str,
        dataset_name: str,
    ) -> str:
        raise NotImplementedError

    #
    # statistics of the activities dataset
    #

    def activities_stats(
        self,
        user_id: str,
        dataset_name: str,
        activities: list[entities.ActivityEntity] | None = None,
        include_meta: bool = False,
        force_cache: bool = True,
    ) -> stats.UserDatasetStats:
        """Get user dataset statistics:

        - either for all activities (cached)
        - or for a subset (NOT cached)

        """
        p = profilers.Profiler(logger=self.logger).start()

        # ALL activities (including meta activities) might be cached
        if activities is None:
            if include_meta or force_cache:
                cached = self._cache.user(user_id).activities_stats(dataset_name)
                if not cached:
                    cached = stats.UserDatasetStats()
                    cached.update(
                        activities=list(
                            self.all_activities(user_id, dataset_name).values()
                        ),
                        activity_types=self.list_activity_types(
                            user_id, dataset_name=dataset_name
                        ),
                        include_meta=include_meta,
                        logger=self.logger,
                    )
                    self._cache.user(user_id).set_activities_stats(
                        activities_stats=cached
                    )
                p.stop()
                p.print("activities load")
                return cached
            else:
                activities = list(self.all_activities(user_id, dataset_name).values())

        # ELSE stats for a custom set of activities
        user_ds_stats = stats.UserDatasetStats()
        user_ds_stats.update(
            activities=activities,
            activity_types=self.list_activity_types(user_id),
            include_meta=include_meta,
            logger=self.logger,
        )
        p.stop()
        p.print("custom activities load")
        return user_ds_stats

    #
    # activity types
    #

    @abc.abstractmethod
    def _load_activity_types(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserActivityTypes:
        raise NotImplementedError

    @abc.abstractmethod
    def create_activity_type(
        self, user_id: str, activity_type: settings.ActivityType
    ) -> settings.ActivityType:
        raise NotImplementedError

    @abc.abstractmethod
    def update_activity_type(
        self, user_id: str, activity_type: settings.ActivityType
    ) -> settings.ActivityType:
        raise NotImplementedError

    @abc.abstractmethod
    def delete_activity_type(self, user_id: str, key: str):
        raise NotImplementedError

    def get_activity_type(self, user_id: str, key: str) -> settings.ActivityType:
        by_key = self.list_activity_types(user_id).activity_types_by_key
        if key not in by_key:
            raise ValueError(f"Activity type with key '{key}' does not exist")
        return by_key[key]

    def list_activity_types(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserActivityTypes:
        """List all user activity types.

        Parameters
        ----------
        user_id : str
            User ID.
        dataset_name : str
            Optional dataset name which is used to calculate statistics of the activity
            types. If not provided, the statistics are not calculated.

        """

        return self._cache.user(user_id).activity_types() or self._cache.user(
            user_id
        ).set_activity_types(
            activity_types=self._load_activity_types(
                user_id=user_id, dataset_name=dataset_name
            )
        )

    @abc.abstractmethod
    def _build_activity_types_stats(
        self, user_id: str, dataset_name: str
    ) -> stats.UserActivityTypesStats:
        raise NotImplementedError

    def activity_types_stats(
        self, user_id: str, dataset_name: str
    ) -> stats.UserActivityTypesStats:
        return self._cache.user(user_id).activity_types_stats() or self._cache.user(
            user_id
        ).set_activity_types_stats(
            activity_types_stats=self._build_activity_types_stats(
                user_id=user_id, dataset_name=dataset_name
            )
        )

    #
    # gear
    #

    @abc.abstractmethod
    def _load_gears(self, user_id: str, dataset_name: str = "") -> settings.UserGear:
        raise NotImplementedError

    @abc.abstractmethod
    def create_gear(
        self, user_id: str, gear: settings.Gear, dataset_name: str
    ) -> settings.Gear:
        raise NotImplementedError

    @abc.abstractmethod
    def update_gear(
        self, user_id: str, gear: settings.Gear, dataset_name: str
    ) -> settings.Gear:
        raise NotImplementedError

    @abc.abstractmethod
    def delete_gear(self, user_id: str, key: str, dataset_name: str):
        raise NotImplementedError

    def get_gear(self, user_id: str, key: str, dataset_name: str) -> settings.Gear:
        by_key = self.list_gear(user_id=user_id, dataset_name=dataset_name).gear_by_key
        if key not in by_key:
            raise ValueError(f"Gear with key '{key}' does not exist")
        return by_key[key]

    def gear_km_at_date(
        self,
        user_id: str,
        dataset_name: str,
        gear_key: str,
        iso_date: str,
    ) -> tuple[float, float]:
        """Compute (km, hours) of gear activities up to and including iso_date.

        Uses actual activity records, not the potentially-stale
        ``component.distance_meters`` snapshot. This gives accurate
        cumulative usage figures that can be used to compute per-service
        deltas (km/hours between consecutive service events).

        Parameters
        ----------
        user_id : str
            User ID.
        dataset_name : str
            Dataset name.
        gear_key : str
            Gear key to filter activities.
        iso_date : str
            Upper-bound date in ISO format (``YYYY-MM-DD``). Activities
            whose ``when`` date is on or before this date are included.

        Returns
        -------
        tuple[float, float]
            (total_km, total_hours) for this gear up to iso_date.
        """
        # normalise the cut-off to a ``YYYY-MM-DD`` string for prefix comparison
        cutoff = iso_date[:10].replace("/", "-") if iso_date else ""
        all_acts = self.all_activities(user_id, dataset_name)
        total_m = 0
        total_s = 0
        for activity in all_acts.values():
            gears = getattr(activity, "gears", None) or []
            if not gears:
                raw_gear = getattr(activity, "gear", "") or ""
                if raw_gear:
                    gears = [raw_gear]
            if gear_key not in gears:
                continue
            when_raw = getattr(activity, "when", "") or ""
            when_date = when_raw[:10].replace("/", "-")
            if cutoff and when_date > cutoff:
                continue
            total_m += activity.distance or 0
            total_s += activity.duration_seconds or 0
        return total_m / 1000.0, total_s / 3600.0

    def recompute_gear_service_intervals(
        self,
        user_id: str,
        dataset_name: str,
        gear: settings.Gear,
    ) -> None:
        """Recompute service interval km/hours for all gear components from activities.

        Iterates activity records to derive accurate per-interval km and hours
        for every service history entry, and updates ``last_service_km``,
        ``last_service_hours``, ``distance_meters`` and ``time_seconds`` on each
        component dict. Mutates *gear* in memory only — does NOT persist to disk.

        This is the authoritative calculation path. It is immune to stale
        component odometer values caused by bulk-imported activities that
        bypassed ``_update_gear_component_usage``.

        Parameters
        ----------
        user_id : str
            User ID.
        dataset_name : str
            Dataset name.
        gear : settings.Gear
            The gear object to update in place.
        """
        today_str = datetime.date.today().isoformat()
        today_km, today_h = self.gear_km_at_date(
            user_id, dataset_name, gear.key, today_str
        )

        for component_dict in gear.components:
            component_key = component_dict.get("key", "")
            install_date = component_dict.get("installed_date", "")
            status = component_dict.get("status", "active")

            # gear km/hours at component install — the zero baseline for this component
            if install_date:
                install_km, install_h = self.gear_km_at_date(
                    user_id, dataset_name, gear.key, install_date
                )
            else:
                # no install date: assume component was there from gear purchase (0 km)
                install_km, install_h = 0.0, 0.0

            # walk history entries in chronological order, computing each interval
            # prev_km/prev_h track the gear odometer at the previous event (install or
            # last service); each entry stores the delta since that previous event
            prev_km, prev_h = install_km, install_h
            history = gear.component_history.get(component_key, [])
            for entry in sorted(history, key=lambda e: e.get("date", "")):
                entry_date = entry.get("date", "")
                if not entry_date:
                    continue
                km_at, h_at = self.gear_km_at_date(
                    user_id, dataset_name, gear.key, entry_date
                )
                entry["km_at_service"] = max(0.0, km_at - prev_km)
                entry["hours_at_service"] = max(0.0, h_at - prev_h)
                prev_km = km_at
                prev_h = h_at

            # store component-relative baselines so distance_km reflects actual
            # component usage (not the gear's absolute odometer reading)
            component_dict["last_service_km"] = max(0.0, prev_km - install_km)
            component_dict["last_service_hours"] = max(0.0, prev_h - install_h)

            if status == "active":
                component_dict["distance_meters"] = int((today_km - install_km) * 1000)
                component_dict["time_seconds"] = int((today_h - install_h) * 3600)
            else:
                # retired: use last history entry date as the retirement point;
                # if no history exists, assume retired "now" so the component
                # gets credit for all gear km up to today
                sorted_history = sorted(history, key=lambda e: e.get("date", ""))
                retire_date = (
                    sorted_history[-1].get("date") if sorted_history else today_str
                )
                retire_km, retire_h = self.gear_km_at_date(
                    user_id, dataset_name, gear.key, retire_date
                )
                component_dict["distance_meters"] = int((retire_km - install_km) * 1000)
                component_dict["time_seconds"] = int((retire_h - install_h) * 3600)

    def list_gear(self, user_id: str, dataset_name: str = "") -> settings.UserGear:
        return self._cache.user(user_id).gear() or self._cache.user(user_id).set_gear(
            gear=self._load_gears(user_id=user_id, dataset_name=dataset_name)
        )

    @abc.abstractmethod
    def _build_gear_stats(self, user_id: str, dataset_name: str) -> stats.UserGearStats:
        raise NotImplementedError

    def gear_stats(self, user_id: str, dataset_name: str) -> stats.UserGearStats:
        return self._cache.user(user_id).gear_stats() or self._cache.user(
            user_id
        ).set_gear_stats(
            gear_stats=self._build_gear_stats(
                user_id=user_id, dataset_name=dataset_name
            )
        )

    #
    # Strava gear ~ gear IDs exported from Strava & used by the given user
    #

    @abc.abstractmethod
    def _load_strava_gears(self, user_id: str) -> settings.StravaUserGear:
        raise NotImplementedError

    def list_strava_gear(self, user_id: str) -> settings.StravaUserGear:
        return self._load_strava_gears(user_id)

    @abc.abstractmethod
    def update_strava_gears(
        self, user_id: str, strava_gears: settings.StravaUserGear
    ) -> settings.StravaUserGear:
        raise NotImplementedError

    #
    # outfits
    #

    @abc.abstractmethod
    def _load_outfits(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserOutfits:
        raise NotImplementedError

    @abc.abstractmethod
    def _build_outfits_stats(
        self, user_id: str, dataset_name: str
    ) -> stats.UserOutfitsStats:
        raise NotImplementedError

    def outfits_stats(self, user_id: str, dataset_name: str) -> stats.UserOutfitsStats:
        return self._cache.user(user_id).outfits_stats() or self._cache.user(
            user_id
        ).set_outfits_stats(
            outfits_stats=self._build_outfits_stats(
                user_id=user_id, dataset_name=dataset_name
            )
        )

    @abc.abstractmethod
    def create_outfit(self, user_id: str, outfit: settings.Outfit) -> settings.Outfit:
        raise NotImplementedError

    @abc.abstractmethod
    def update_outfit(self, user_id: str, outfit: settings.Outfit) -> settings.Outfit:
        raise NotImplementedError

    @abc.abstractmethod
    def delete_outfit(self, user_id: str, key: str):
        raise NotImplementedError

    def get_outfit(self, user_id: str, key: str) -> settings.Outfit:
        by_key = self.list_outfits(user_id).outfits_by_key
        if key not in by_key:
            raise ValueError(f"Outfit with key '{key}' does not exist")
        return by_key[key]

    def list_outfits(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserOutfits:
        return self._cache.user(user_id).outfits() or self._cache.user(
            user_id
        ).set_outfits(
            outfits=self._load_outfits(user_id=user_id, dataset_name=dataset_name)
        )

    #
    # activity bookmarks
    #

    @abc.abstractmethod
    def _load_bookmarks(self, user_id: str) -> settings.UserBookmarks:
        raise NotImplementedError

    @abc.abstractmethod
    def create_bookmark(
        self, user_id: str, activity_key: str
    ) -> settings.UserBookmarks:
        raise NotImplementedError

    @abc.abstractmethod
    def delete_bookmark(
        self, user_id: str, activity_key: str
    ) -> settings.UserBookmarks:
        raise NotImplementedError

    @abc.abstractmethod
    def move_bookmark(
        self, user_id: str, activity_key: str, direction: str
    ) -> settings.UserBookmarks:
        raise NotImplementedError

    def list_bookmarks(self, user_id: str) -> settings.UserBookmarks:
        return self._cache.user(user_id).bookmarks() or self._cache.user(
            user_id
        ).set_bookmarks(bookmarks=self._load_bookmarks(user_id=user_id))

    #
    # component templates
    #

    @abc.abstractmethod
    def _load_component_templates(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserComponentTemplates:
        raise NotImplementedError

    @abc.abstractmethod
    def create_component_template(
        self, user_id: str, template: settings.ComponentTemplate
    ) -> settings.ComponentTemplate:
        raise NotImplementedError

    @abc.abstractmethod
    def update_component_template(
        self, user_id: str, template: settings.ComponentTemplate
    ) -> settings.ComponentTemplate:
        raise NotImplementedError

    @abc.abstractmethod
    def delete_component_template(self, user_id: str, key: str) -> None:
        raise NotImplementedError

    def get_component_template(
        self, user_id: str, key: str
    ) -> settings.ComponentTemplate | None:
        """Get a component template by key."""
        return self.list_component_templates(user_id).get_by_key(key)

    def list_component_templates(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserComponentTemplates:
        """List all component templates, using cache when available."""
        cache = self._cache.user(user_id)
        cached = cache.component_templates()
        if cached is not None:
            return cached
        return cache.set_component_templates(
            self._load_component_templates(user_id, dataset_name)
        )

    #
    # goals
    #

    @abc.abstractmethod
    def _load_goals(self, user_id: str, dataset_name: str = "") -> settings.UserGoals:
        raise NotImplementedError

    @abc.abstractmethod
    def create_goal(self, user_id: str, goal: settings.Goal) -> settings.Goal:
        raise NotImplementedError

    @abc.abstractmethod
    def update_goal(self, user_id: str, goal: settings.Goal) -> settings.Goal:
        raise NotImplementedError

    @abc.abstractmethod
    def delete_goal(self, user_id: str, key: str):
        raise NotImplementedError

    def get_goal(self, user_id: str, key: str) -> settings.Goal:
        by_key = self.list_goals(user_id).goals_by_key
        if key not in by_key:
            raise ValueError(f"Goal with key '{key}' does not exist")
        return by_key[key]

    def list_goals(self, user_id: str, dataset_name: str = "") -> settings.UserGoals:
        return self._cache.user(user_id).goals() or self._cache.user(user_id).set_goals(
            goals=self._load_goals(user_id=user_id, dataset_name=dataset_name)
        )

    #
    # exercises
    #

    @abc.abstractmethod
    def _load_exercises(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserExercises:
        raise NotImplementedError

    @abc.abstractmethod
    def create_exercise(
        self, user_id: str, exercise: settings.Exercise
    ) -> settings.Exercise:
        raise NotImplementedError

    @abc.abstractmethod
    def update_exercise(
        self, user_id: str, exercise: settings.Exercise
    ) -> settings.Exercise:
        raise NotImplementedError

    @abc.abstractmethod
    def delete_exercise(self, user_id: str, key: str):
        raise NotImplementedError

    def get_exercise(self, user_id: str, key: str) -> settings.Exercise:
        by_key = self.list_exercises(user_id).exercise_by_key
        if key not in by_key:
            raise ValueError(f"Exercise with key '{key}' does not exist")
        return by_key[key]

    def list_exercises(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserExercises:
        return self._cache.user(user_id).exercises() or self._cache.user(
            user_id
        ).set_exercises(
            exercises=self._load_exercises(user_id=user_id, dataset_name=dataset_name)
        )

    @abc.abstractmethod
    def _build_exercises_stats(
        self, user_id: str, dataset_name: str
    ) -> stats.UserExercisesStats:
        raise NotImplementedError

    def exercises_stats(
        self, user_id: str, dataset_name: str
    ) -> stats.UserExercisesStats:
        return self._cache.user(user_id).exercises_stats() or self._cache.user(
            user_id
        ).set_exercises_stats(
            exercises_stats=self._build_exercises_stats(
                user_id=user_id, dataset_name=dataset_name
            )
        )

    #
    # laps
    #

    @abc.abstractmethod
    def _load_laps(self, user_id: str, dataset_name: str = "") -> settings.UserLaps:
        raise NotImplementedError

    @abc.abstractmethod
    def create_lap(
        self, user_id: str, lap: settings.Lap, dataset_name: str = ""
    ) -> settings.Lap:
        raise NotImplementedError

    @abc.abstractmethod
    def update_lap(
        self, user_id: str, lap: settings.Lap, dataset_name: str = ""
    ) -> settings.Lap:
        raise NotImplementedError

    @abc.abstractmethod
    def delete_lap(self, user_id: str, key: str, dataset_name: str = ""):
        raise NotImplementedError

    def get_lap(self, user_id: str, key: str, dataset_name: str = "") -> settings.Lap:
        by_key = self.list_laps(user_id, dataset_name).lap_by_key
        if key not in by_key:
            raise ValueError(f"Lap with key '{key}' does not exist")
        return by_key[key]

    def list_laps(self, user_id: str, dataset_name: str = "") -> settings.UserLaps:
        return self._cache.user(user_id).laps() or self._cache.user(user_id).set_laps(
            laps=self._load_laps(user_id=user_id, dataset_name=dataset_name)
        )

    #
    # symptoms
    #

    @abc.abstractmethod
    def _load_symptoms(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserSymptoms:
        raise NotImplementedError

    @abc.abstractmethod
    def create_symptom(
        self, user_id: str, symptom: settings.Symptom
    ) -> settings.Symptom:
        raise NotImplementedError

    @abc.abstractmethod
    def update_symptom(
        self, user_id: str, symptom: settings.Symptom
    ) -> settings.Symptom:
        raise NotImplementedError

    @abc.abstractmethod
    def delete_symptom(self, user_id: str, key: str):
        raise NotImplementedError

    def get_symptom(self, user_id: str, key: str) -> settings.Symptom:
        by_key = self.list_symptoms(user_id).symptoms_by_key
        if key not in by_key:
            raise ValueError(f"Symptom with key '{key}' does not exist")
        return by_key[key]

    def list_symptoms(
        self, user_id: str, dataset_name: str = ""
    ) -> settings.UserSymptoms:
        return self._cache.user(user_id).symptoms() or self._cache.user(
            user_id
        ).set_symptoms(
            symptoms=self._load_symptoms(user_id=user_id, dataset_name=dataset_name)
        )

    @abc.abstractmethod
    def _build_symptoms_stats(
        self, user_id: str, dataset_name: str
    ) -> stats.UserSymptomsStats:
        raise NotImplementedError

    def symptoms_stats(
        self, user_id: str, dataset_name: str
    ) -> stats.UserSymptomsStats:
        return self._cache.user(user_id).symptoms_stats() or self._cache.user(
            user_id
        ).set_symptoms_stats(
            symptoms_stats=self._build_symptoms_stats(
                user_id=user_id, dataset_name=dataset_name
            )
        )

    @abc.abstractmethod
    def _build_laps_stats(self, user_id: str, dataset_name: str) -> stats.UserLapsStats:
        raise NotImplementedError

    def laps_stats(self, user_id: str, dataset_name: str) -> stats.UserLapsStats:
        return self._cache.user(user_id).laps_stats() or self._cache.user(
            user_id
        ).set_laps_stats(
            laps_stats=self._build_laps_stats(
                user_id=user_id, dataset_name=dataset_name
            )
        )

    #
    # tasks
    #

    @abc.abstractmethod
    def user_task_json_path(self, user_id: str, task_id: str) -> pathlib.Path:
        """Get path to task JSON file."""
        raise NotImplementedError

    @abc.abstractmethod
    def user_task_log_path(self, user_id: str, task_id: str) -> pathlib.Path:
        """Get path to task log file."""
        raise NotImplementedError

    @abc.abstractmethod
    def save_task(self, user_id: str, task_dict: dict) -> None:
        """Save task metadata to JSON file (excludes logs)."""
        raise NotImplementedError

    @abc.abstractmethod
    def append_task_logs(
        self, user_id: str, task_id: str, log_entries: list[str]
    ) -> None:
        """Append log entries to task's .log file."""
        raise NotImplementedError

    @abc.abstractmethod
    def load_task(self, user_id: str, task_id: str) -> dict:
        """Load task metadata from JSON file (excludes logs)."""
        raise NotImplementedError

    @abc.abstractmethod
    def load_task_logs(self, user_id: str, task_id: str, tail: int = 100) -> list[str]:
        """Load logs from .log file."""
        raise NotImplementedError

    @abc.abstractmethod
    def list_task_files(self, user_id: str) -> list[pathlib.Path]:
        """List all task JSON files for user."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete_task_files(self, user_id: str, task_id: str) -> None:
        """Delete task JSON and log files."""
        raise NotImplementedError

    #
    # heatmaps
    #

    def activity_type_heatmap(
        self, user_id: str, dataset_name: str
    ) -> views.CalendarHeatmap:
        """Get activity_type_key heatmap from cache or build it."""
        heatmap = self._cache.user(user_id).activity_type_heatmap()
        if not heatmap:
            # cache returned None - need to build new heatmap
            profile = self.profile(user_id)
            activity_types = self.list_activity_types(user_id)
            heatmap = views.CalendarHeatmap(
                from_year=profile.born_year,
                to_year=datetime.date.today().year,
                user_profile=profile,
                activity_types=activity_types,
                logger=self.logger,
            )
        if not heatmap.activities:
            heatmap.build_activity_type_heatmap(
                activities=self.list_activities(
                    user_id=user_id, dataset_name=dataset_name, skip_meta=False
                )
            )
        return heatmap

    def sick_heatmap(self, user_id: str, dataset_name: str) -> views.CalendarHeatmap:
        """Get sickness heatmap from cache or build it."""
        heatmap = self._cache.user(user_id).sick_heatmap()
        if not heatmap:
            # cache returned None - need to build new heatmap
            profile = self.profile(user_id)
            activity_types = self.list_activity_types(user_id)
            heatmap = views.CalendarHeatmap(
                from_year=profile.born_year,
                to_year=datetime.date.today().year,
                user_profile=profile,
                activity_types=activity_types,
                logger=self.logger,
            )
        if not heatmap.activities:
            heatmap.build_sickness_heatmap(
                activities=self.list_activities(
                    user_id=user_id, dataset_name=dataset_name, skip_meta=False
                )
            )
        return heatmap


class MytralDatasetImplementationsRegistry:
    """MyTraL dataset do registry decouples interface from its impls."""

    __create_key = object()
    __singleton = None

    @classmethod
    def registry(cls):
        if cls.__singleton is None:
            return MytralDatasetImplementationsRegistry(cls.__create_key)
        return cls.__singleton

    def __init__(self, create_key):
        assert create_key == MytralDatasetImplementationsRegistry.__create_key, (
            "This is singleton! Constructor calls are forbidden"
        )

        self._implementations: dict[config.PersistenceType, UserDataset] = {}

    def add_implementation(
        self, persistence_type: config.PersistenceType, user_dataset: UserDataset
    ):
        if not issubclass(user_dataset.__class__, UserDataset):
            raise ValueError(
                "Dataset implementation class must be a subclass of MyTraL's "
                "UserDataset"
            )

        self._implementations[persistence_type] = user_dataset

    def get_implementation(
        self, persistence_type: config.PersistenceType
    ) -> UserDataset:
        return self._implementations[persistence_type]


# registry of UserDataset do
user_dataset_registry = MytralDatasetImplementationsRegistry.registry()


class MyTraLDataset:
    """MyTraL dataset - application and user data singleton.

    MyTraL dataset is:

    - persistence AGNOSTIC:
      it can be implemented by filesystem, DB, document DB, ... and for MyTraL runtime
      there is no change.

    - includes application data AND user data:
      it provides user management (list/validate/* users), and has getter
      for USER DATASET which is the interface for persistence AGNOSTIC do
      of user data management - activities, profile (gear, exercises, symptoms)

    - user-centric:
      all data is organized by user to support multi-tenant MyTraL runtime,
      behind user dataset interface

    - INTERNAL cache:
      it uses internally caching which cannot / should not be manipulated from outside

    """

    PREFIX_DS_NAME = "activities-"

    def __init__(
        self, mytral_config: config.MytralConfig, logger: loggers.MytralLogger
    ) -> None:
        self.config = mytral_config
        self.logger = logger

        # user dataset for configured persistence type
        self._users_dataset = None

    #
    # users
    #

    def user_ids(self) -> list[str]:
        """List all user IDs."""
        return self.user().list_profiles()

    def is_user_id(self, user_id: str) -> bool:
        user_ids = self.user_ids()
        return True if user_id in user_ids else False

    def user_names(self) -> dict[str, str]:
        """List all usernames."""
        return self.user().list_profile_names()

    def is_user_name(self, user_name: str) -> bool:
        user_names = self.user_names()
        return True if user_name in list(user_names.keys()) else False

    #
    # datasets
    #

    @staticmethod
    def create_dataset_name(custom_name: str) -> str:
        """Verify, transform and return valid dataset name for given custom name."""
        if not custom_name:
            return f"{MyTraLDataset.PREFIX_DS_NAME}{uuid.uuid4()}"
        elif not custom_name.startswith(MyTraLDataset.PREFIX_DS_NAME):
            return f"{MyTraLDataset.PREFIX_DS_NAME}{custom_name}"

        return custom_name

    def user(self) -> UserDataset:
        """Get user dataset - with respect to persistence type."""
        if self.config.persistence_type == config.PersistenceType.FILESYSTEM:
            if not self._users_dataset:
                self._users_dataset = user_dataset_registry.get_implementation(
                    config.PersistenceType.FILESYSTEM
                )
                # ensure proper initialization
                self._users_dataset.configure(
                    mytral_config=self.config,
                    logger=self.logger,
                )
            return self._users_dataset

        raise RuntimeError(
            f"Unsupported persistence type: {self.config.persistence_type}"
        )
