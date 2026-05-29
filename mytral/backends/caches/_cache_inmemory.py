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
import sys
import threading

from mytral import loggers
from mytral import settings
from mytral import stats
from mytral import views
from mytral.backends import cache
from mytral.backends import entities


class InMemoryMytralUserCache(cache.MytralUserCache):
    """All data of a particular MyTraL user - activities and settings."""

    def __init__(self, user_id: str, logger: loggers.MytralLogger) -> None:

        # user

        self._user_id: str = user_id
        self._profile: settings.UserProfile | None = None

        # activities

        # "lifelong" or a custom (expert) name
        self._activities_ds_name: str = ""
        # ALL activities - dict[activity ID -> entity]
        self._activities: dict[str, entities.ActivityEntity] | None = None
        # ALL activities stats - ...
        self._activities_stats: stats.UserDatasetStats | None = None

        # dict: str[year] -> dict[activity ID -> entity]
        self._activities_years: dict[str, dict[str, entities.ActivityEntity]] = {}
        # activities stats for particular year
        self._activities_year_stats: dict | None = None

        # indices

        # BMI, ...
        self._profile_stats: stats.UserProfileStats | None = None

        self._activity_types_stats: stats.UserActivityTypesStats | None = None
        self._exercises_stats: stats.UserExercisesStats | None = None
        self._gear_stats: stats.UserGearStats | None = None
        self._outfits_stats: stats.UserOutfitsStats | None = None
        self._symptoms_stats: stats.UserSymptomsStats | None = None
        self._laps_stats: stats.UserLapsStats | None = None

        # ALL activities activity type heatmap: year -> week number -> list[activity]
        self._activity_type_heatmap = None  # TODO type hint
        # ALL activities sickness (sick & injured) heatmap
        self._sick_heatmap = None  # TODO type hint

        # settings

        self._activity_types: settings.UserActivityTypes | None = None
        self._component_templates: settings.UserComponentTemplates | None = None
        self._exercises: settings.UserExercises | None = None
        self._gear: settings.UserGear | None = None
        self._goals: settings.UserGoals | None = None
        self._laps: settings.UserLaps | None = None
        self._outfits: settings.UserOutfits | None = None
        self._strava_gear: settings.StravaUserGear | None = None
        self._symptoms: settings.UserSymptoms | None = None

        # runtime

        self.logger = logger

    #
    # user
    #

    def profile(self) -> settings.UserProfile | None:
        return self._profile

    def set_profile(self, profile: settings.UserProfile) -> settings.UserProfile:
        self._profile = profile
        return self._profile

    #
    # dataset
    #

    def dataset_name(self) -> str:
        return self._activities_ds_name

    def set_dataset_name(self, dataset_name: str):
        self._activities_ds_name = dataset_name

    #
    # activities
    #

    def activities(self, dataset_name: str) -> dict[str, entities.ActivityEntity]:
        # ensure integrity by verifying the current dataset name ~ persistency mode
        if self._activities_ds_name == dataset_name:
            return self._activities
        return {}

    def set_activities(
        self,
        activities: dict[str, entities.ActivityEntity],
        dataset_name: str,
    ) -> dict[str, entities.ActivityEntity]:
        """Set all (lifelong or custom dataset) activities. If the dataset name is
        DIFFERENT, then activity related cache entries are  EVICTED:

        - (all) activities stats
        - * settings stats

        """
        if dataset_name != self._activities_ds_name:
            # evict all activities and activities-based cache entries
            self.evict_activities()

        self._activities_ds_name = dataset_name
        self._activities = activities
        return self._activities

    def activities_stats(self, dataset_name: str) -> stats.UserDatasetStats | None:
        """User activities statistics based on ALL activities."""

        # TODO
        # TODO
        # TODO
        # raise NotImplementedError("Calculate stats in here")
        return None

    def set_activities_stats(
        self, activities_stats: stats.UserDatasetStats
    ) -> stats.UserDatasetStats | None:
        self._activities_stats = activities_stats
        return self._activities_stats

    def activities_years(self) -> dict:
        return self._activities_years

    def activities_year(self, year: str) -> dict:
        """Get YEAR (or CUSTOM) dataset by year (4 numbers as string) or year dataset
        name.

        """
        err_msg = (
            f"Invalid year specification when getting year dataset from cache: '{year}'"
        )
        if not isinstance(year, str):
            raise ValueError(err_msg)
        if len(year) != 4:
            if len(year) < 4:
                raise ValueError(err_msg)
            prefix_activities = "activities-"
            if year.startswith(prefix_activities):
                year = year.replace(prefix_activities, "")

        if not self._activities_years.get(year):
            self._activities_years[year] = {}

        return self._activities_years[year]

    #
    # indices
    #

    def profile_stats(self) -> stats.UserProfileStats | None:
        return self._profile_stats

    def set_profile_stats(
        self,
        profile_stats: stats.UserProfileStats,
    ) -> stats.UserProfileStats:
        self._profile_stats = profile_stats
        return self._profile_stats

    def evict_profile_stats(self):
        self._profile_stats = None

    def activity_types_stats(self) -> stats.UserActivityTypesStats | None:
        return self._activity_types_stats

    def set_activity_types_stats(
        self, activity_types_stats: stats.UserActivityTypesStats
    ) -> stats.UserActivityTypesStats:
        self._activity_types_stats = activity_types_stats
        return self._activity_types_stats

    def evict_activity_types_stats(self):
        self._activity_types_stats = None

    def exercises_stats(self) -> stats.UserExercisesStats | None:
        return self._exercises_stats

    def set_exercises_stats(
        self, exercises_stats: stats.UserExercisesStats
    ) -> stats.UserExercisesStats | None:
        self._exercises_stats = exercises_stats
        return self._exercises_stats

    def evict_exercises_stats(self):
        self._exercises_stats = None

    def gear_stats(self) -> stats.UserGearStats | None:
        return self._gear_stats

    def set_gear_stats(
        self, gear_stats: stats.UserGearStats
    ) -> stats.UserGearStats | None:
        self._gear_stats = gear_stats
        return self._gear_stats

    def evict_gear_stats(self):
        self._gear_stats = None

    def outfits_stats(self) -> stats.UserOutfitsStats | None:
        return self._outfits_stats

    def set_outfits_stats(
        self, outfits_stats: stats.UserOutfitsStats
    ) -> stats.UserOutfitsStats | None:
        self._outfits_stats = outfits_stats
        return self._outfits_stats

    def evict_outfits_stats(self):
        self._outfits_stats = None

    def symptoms_stats(self) -> stats.UserSymptomsStats | None:
        return self._symptoms_stats

    def set_symptoms_stats(
        self, symptoms_stats: stats.UserSymptomsStats
    ) -> stats.UserSymptomsStats:
        self._symptoms_stats = symptoms_stats
        return self._symptoms_stats

    def evict_symptoms_stats(self):
        self._symptoms_stats = None

    def laps_stats(self) -> stats.UserLapsStats | None:
        return self._laps_stats

    def set_laps_stats(self, laps_stats: stats.UserLapsStats) -> stats.UserLapsStats:
        self._laps_stats = laps_stats
        return self._laps_stats

    def evict_laps_stats(self):
        self._laps_stats = None

    def activity_type_heatmap(self) -> views.CalendarHeatmap:
        """Lifetime activity type heatmap:

        - LAZY automatic build when the heatmap is not available
        - lifelong/ALL activities are used to build the heatmap

        """
        if not self._activity_type_heatmap:
            self._activity_type_heatmap = views.CalendarHeatmap(
                from_year=self.profile().born_year,
                to_year=datetime.date.today().year,
                user_profile=self.profile(),
                activity_types=self.activity_types(),
                logger=self.logger,
            )

        return self._activity_type_heatmap

    def sick_heatmap(self) -> views.CalendarHeatmap:
        """Lifetime sickness heatmap: ``CalendarHeatmap::build_sickness_heatmap():

        - LAZY automatic build when the heatmap is not available
        - lifelong/ALL activities are used to build the heatmap
        - BOTH "sick" and "injured" is considered

        """
        if not self._sick_heatmap:
            self._sick_heatmap = views.CalendarHeatmap(
                from_year=self.profile().born_year,
                to_year=datetime.date.today().year,
                user_profile=self.profile(),
                activity_types=self.activity_types(),
                logger=self.logger,
            )

        return self._sick_heatmap

    #
    # settings
    #

    def activity_types(self) -> settings.UserActivityTypes | None:
        return self._activity_types

    def set_activity_types(
        self, activity_types: settings.UserActivityTypes
    ) -> settings.UserActivityTypes:
        self._activity_types = activity_types
        return self._activity_types

    def gear(self) -> settings.UserGear | None:
        return self._gear

    def set_gear(self, gear: settings.UserGear) -> settings.UserGear:
        self._gear = gear
        return self._gear

    def strava_gear(self) -> settings.StravaUserGear | None:
        return self._strava_gear

    def set_strava_gear(
        self, strava_gear: settings.StravaUserGear
    ) -> settings.StravaUserGear:
        self._strava_gear = strava_gear
        return self._strava_gear

    def outfits(self) -> settings.UserOutfits | None:
        return self._outfits

    def set_outfits(self, outfits: settings.UserOutfits) -> settings.UserOutfits:
        self._outfits = outfits
        return self._outfits

    def component_templates(self) -> settings.UserComponentTemplates | None:
        return self._component_templates

    def set_component_templates(
        self, templates: settings.UserComponentTemplates
    ) -> settings.UserComponentTemplates:
        self._component_templates = templates
        return self._component_templates

    def goals(self) -> settings.UserGoals | None:
        return self._goals

    def set_goals(self, goals: settings.UserGoals) -> settings.UserGoals:
        self._goals = goals
        return self._goals

    def symptoms(self) -> settings.UserSymptoms:
        """Loaded once (on user login) and then never evicted. Any change is made
        in cache and then written to the filesystem.

        """
        return self._symptoms

    def set_symptoms(self, symptoms: settings.UserSymptoms) -> settings.UserSymptoms:
        """Loaded once (on user login) and then never evicted. Any change is made
        in cache and then written to the filesystem.

        """
        self._symptoms = symptoms
        return self._symptoms

    def exercises(self) -> settings.UserExercises:
        return self._exercises

    def set_exercises(
        self, exercises: settings.UserExercises
    ) -> settings.UserExercises:
        self._exercises = exercises
        return self._exercises

    def laps(self) -> settings.UserLaps:
        return self._laps

    def set_laps(self, laps: settings.UserLaps) -> settings.UserLaps:
        self._laps = laps
        return self._laps

    #
    # runtime
    #

    def evict_settings(self):
        self._activity_types = None
        self._component_templates = None
        self._exercises = None
        self._gear = None
        self._goals = None
        self._laps = None
        self._outfits = None
        self._strava_gear = None
        self._symptoms = None

    def evict_indices(self):
        self._activities_stats = None
        self._activities_year_stats = None

        self._profile_stats = None

        self._activity_types_stats = None
        self._exercises_stats = None
        self._gear_stats = None
        self._symptoms_stats = None
        self._laps_stats = None

        self._activity_type_heatmap = None
        self._sick_heatmap = None

    def evict_activities(self):
        self._activities_years = {}
        self._activities = None  # LIFELING ~ index

        self.evict_indices()

    def evict_on_activity_cud(self):
        self.evict_indices()

    def evict(self):
        # user_id ... is kept ~ this USER cache is for that user, right?
        # profile ... is kept ~ no reason why to evict it

        self._activities_ds_name = ""

        self.evict_activities()
        self.evict_indices()
        self.evict_settings()

    def memory_size(self) -> int:
        """Return size of the user cache in bytes - performs deep walk through cache
        entries.

        Returns
        -------
        int :
            Cache size in bytes.

        """
        total_size = 0

        # user
        total_size += sys.getsizeof(self._user_id)
        if self._profile:
            total_size += sys.getsizeof(self._profile)

        # activities
        total_size += sys.getsizeof(self._activities_ds_name)
        if self._activities:
            total_size += sys.getsizeof(self._activities)
            for activity_id, activity in self._activities.items():
                total_size += sys.getsizeof(activity_id)
                total_size += sys.getsizeof(activity)
        if self._activities_stats:
            total_size += sys.getsizeof(self._activities_stats)
        if self._activities_years:
            total_size += sys.getsizeof(self._activities_years)
            for year, activities in self._activities_years.items():
                total_size += sys.getsizeof(year)
                total_size += sys.getsizeof(activities)
                for activity_id, activity in activities.items():
                    total_size += sys.getsizeof(activity_id)
                    total_size += sys.getsizeof(activity)
        if self._activities_year_stats:
            total_size += sys.getsizeof(self._activities_year_stats)

        # indices
        if self._profile_stats:
            total_size += sys.getsizeof(self._profile_stats)
        if self._exercises_stats:
            total_size += sys.getsizeof(self._exercises_stats)
        if self._activity_types_stats:
            total_size += sys.getsizeof(self._activity_types_stats)
        if self._gear_stats:
            total_size += sys.getsizeof(self._gear_stats)
        if self._symptoms_stats:
            total_size += sys.getsizeof(self._symptoms_stats)
        if self._laps_stats:
            total_size += sys.getsizeof(self._laps_stats)
        if self._activity_type_heatmap:
            total_size += sys.getsizeof(self._activity_type_heatmap)
        if self._sick_heatmap:
            total_size += sys.getsizeof(self._sick_heatmap)

        # settings
        if self._gear:
            total_size += sys.getsizeof(self._gear)
        if self._strava_gear:
            total_size += sys.getsizeof(self._strava_gear)
        if self._outfits:
            total_size += sys.getsizeof(self._outfits)
        if self._goals:
            total_size += sys.getsizeof(self._goals)
        if self._activity_types:
            total_size += sys.getsizeof(self._activity_types)
        if self._laps:
            total_size += sys.getsizeof(self._laps)
        if self._symptoms:
            total_size += sys.getsizeof(self._symptoms)
        if self._exercises:
            total_size += sys.getsizeof(self._exercises)

        return total_size


class InMemoryMytralCache(cache.MytralCache):
    """In memory MyTraL cache.

    Thread safe in memory cache is ensured - not evicting & loading at the same time -
    using Python idiomatic lock & context manager.

    """

    def __init__(
        self,
        cache_initializer: cache.MytralCacheInitializer,
        logger: loggers.MytralLogger,
        max_users: int = 2,
    ) -> None:
        """Constructor.

        Parameters
        ----------
        cache_initializer : MytralCacheInitializer
            Persistence capable of loading the data to the cache.
        logger : loggers.MytralLogger
           Logger.
        max_users : int
           Maximum number of users to keep in the cache to avoid OOM.

        """
        cache.MytralCache.__init__(self, logger)

        # ensure that method are mutually excluded
        self._thread_safe_guardian = threading.Lock()

        self._cache_initializer = cache_initializer
        self._max_users = max_users

        self._user_cache: dict = {}

    def user(self, user_id: str) -> cache.MytralUserCache:
        if user_id not in self._user_cache:
            with self._thread_safe_guardian:
                if len(self._user_cache) >= self._max_users:
                    # delete the first (oldest) key
                    del self._user_cache[next(iter(self._user_cache))]

                self._user_cache[user_id] = InMemoryMytralUserCache(
                    user_id=user_id, logger=self.logger
                )

                # load all the data to cache
                self._cache_initializer.init_user_cache(
                    user_cache=self._user_cache[user_id], user_id=user_id
                )

        return self._user_cache[user_id]

    def evict(self, user_id: str) -> None:
        with self._thread_safe_guardian:
            self._user_cache.pop(user_id, None)

    def memory_size(self) -> int:
        with self._thread_safe_guardian:
            total_size = sys.getsizeof(self._user_cache)
            for user_id, user_cache in self._user_cache.items():
                total_size += sys.getsizeof(user_id)
                total_size += user_cache.memory_size()
            return total_size
