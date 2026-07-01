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
import sys

from mytral import loggers
from mytral import settings
from mytral import stats
from mytral import views
from mytral.backends import cache
from mytral.backends import entities


class PassthroughUserCache(cache.MytralUserCache):
    """User cache that never stores data - all getters return None.

    This subclass overrides all getter methods to return None, forcing
    the dataset layer to always load from filesystem. Setter methods
    accept and return values but don't store them - this allows the
    pattern `cache.set_xxx(value)` to return the value for immediate use
    while ensuring subsequent `cache.xxx()` calls return None to force reload.

    """

    def __init__(self, user_id: str, logger: loggers.MytralLogger) -> None:
        cache.MytralUserCache.__init__(self, user_id=user_id, logger=logger)

    #
    # TODO abstract methods which were not implemented ~ NOP all of them?
    #

    def activities_years(self) -> dict:
        return {}

    def set_outfits_stats(
        self, outfits_stats: stats.UserOutfitsStats
    ) -> stats.UserOutfitsStats | None:
        pass

    def activities_year(self, year: str) -> dict:
        return {}

    def evict_profile_stats(self):
        pass

    def evict_activity_types_stats(self):
        pass

    def evict_exercises_stats(self):
        pass

    def evict_gear_stats(self):
        pass

    def evict_outfits_stats(self):
        pass

    def evict_symptoms_stats(self):
        pass

    def evict_laps_stats(self):
        pass

    def evict_settings(self):
        pass

    def evict_indices(self):
        pass

    def evict_activities(self):
        pass

    def evict_on_activity_cud(self):
        pass

    def evict(self):
        pass

    def memory_size(self) -> int:
        return 0

    #
    # override all getters to return None/empty
    #

    def dataset_name(self) -> str:
        # always return empty so _load always re-reads from filesystem
        return ""

    def set_dataset_name(self, dataset_name: str):
        # no-op: dataset name must not be persisted in passthrough mode
        pass

    def profile(self) -> settings.UserProfile | None:
        return None

    def activities(self, dataset_name: str) -> dict:
        return {}

    def activities_stats(self, dataset_name: str) -> stats.UserDatasetStats | None:
        return None

    def profile_stats(self) -> stats.UserProfileStats | None:
        return None

    def activity_types(self) -> settings.UserActivityTypes | None:
        return None

    def activity_types_stats(self) -> stats.UserActivityTypesStats | None:
        return None

    def exercises(self) -> settings.UserExercises | None:
        return None

    def exercises_stats(self) -> stats.UserExercisesStats | None:
        return None

    def gear(self) -> settings.UserGear | None:
        return None

    def gear_stats(self) -> stats.UserGearStats | None:
        return None

    def outfits_stats(self) -> stats.UserOutfitsStats | None:
        return None

    def symptoms(self) -> settings.UserSymptoms | None:
        return None

    def symptoms_stats(self) -> stats.UserSymptomsStats | None:
        return None

    def laps(self) -> settings.UserLaps | None:
        return None

    def laps_stats(self) -> stats.UserLapsStats | None:
        return None

    def strava_gear(self) -> settings.StravaUserGear | None:
        return None

    def outfits(self) -> settings.UserOutfits | None:
        return None

    def bookmarks(self) -> settings.UserBookmarks | None:
        return None

    def component_templates(self) -> settings.UserComponentTemplates | None:
        return None

    def goals(self) -> settings.UserGoals | None:
        return None

    def activity_type_heatmap(self) -> views.CalendarHeatmap | None:
        return None

    def sick_heatmap(self) -> views.CalendarHeatmap | None:
        return None

    #
    # setters are pass-through (return value but don't store)
    #

    def set_profile(self, profile: settings.UserProfile) -> settings.UserProfile:
        return profile

    def set_activities(
        self,
        activities: dict[str, entities.ActivityEntity],
        dataset_name: str,
    ) -> dict[str, entities.ActivityEntity]:
        return activities

    def set_activities_stats(
        self, activities_stats: stats.UserDatasetStats
    ) -> stats.UserDatasetStats | None:
        return activities_stats

    def set_profile_stats(
        self, profile_stats: stats.UserProfileStats
    ) -> stats.UserProfileStats:
        return profile_stats

    def set_activity_types(
        self, activity_types: settings.UserActivityTypes
    ) -> settings.UserActivityTypes:
        return activity_types

    def set_activity_types_stats(
        self, activity_types_stats: stats.UserActivityTypesStats
    ) -> stats.UserActivityTypesStats:
        return activity_types_stats

    def set_exercises(
        self, exercises: settings.UserExercises
    ) -> settings.UserExercises:
        return exercises

    def set_exercises_stats(
        self, exercises_stats: stats.UserExercisesStats
    ) -> stats.UserExercisesStats | None:
        return exercises_stats

    def set_gear(self, gear: settings.UserGear) -> settings.UserGear:
        return gear

    def set_gear_stats(
        self, gear_stats: stats.UserGearStats
    ) -> stats.UserGearStats | None:
        return gear_stats

    def set_symptoms(self, symptoms: settings.UserSymptoms) -> settings.UserSymptoms:
        return symptoms

    def set_symptoms_stats(
        self, symptoms_stats: stats.UserSymptomsStats
    ) -> stats.UserSymptomsStats:
        return symptoms_stats

    def set_laps(self, laps: settings.UserLaps) -> settings.UserLaps:
        return laps

    def set_laps_stats(self, laps_stats: stats.UserLapsStats) -> stats.UserLapsStats:
        return laps_stats

    def set_strava_gear(
        self, strava_gear: settings.StravaUserGear
    ) -> settings.StravaUserGear:
        return strava_gear

    def set_outfits(self, outfits: settings.UserOutfits) -> settings.UserOutfits:
        return outfits

    def set_bookmarks(
        self, bookmarks: settings.UserBookmarks
    ) -> settings.UserBookmarks:
        return bookmarks

    def set_component_templates(
        self, templates: settings.UserComponentTemplates
    ) -> settings.UserComponentTemplates:
        return templates

    def set_goals(self, goals: settings.UserGoals) -> settings.UserGoals:
        return goals


class PassthroughMytralCache(cache.MytralCache):
    def __init__(
        self,
        cache_initializer: cache.MytralCacheInitializer,
        logger: loggers.MytralLogger,
        max_users: int = 2,
    ) -> None:
        cache.MytralCache.__init__(self, logger)

        self._cache_initializer = cache_initializer  # will NOT be needed > pass through
        self._max_users = max_users

        self._user_cache: dict = {}

    def user(self, user_id: str) -> cache.MytralUserCache:
        if user_id not in self._user_cache:
            if len(self._user_cache) >= self._max_users:
                # delete the first (oldest) key
                del self._user_cache[next(iter(self._user_cache))]

            self._user_cache[user_id] = PassthroughUserCache(
                user_id=user_id, logger=self.logger
            )

            # load all the data to cache > data NOT loaded to cache > pass through

        return self._user_cache[user_id]

    def evict(self, user_id: str) -> None:
        self._user_cache.pop(user_id, None)

    def memory_size(self) -> int:
        total_size = sys.getsizeof(self._user_cache)
        for user_id, user_cache in self._user_cache.items():
            total_size += sys.getsizeof(user_id)
            total_size += user_cache.memory_size()
        return total_size
