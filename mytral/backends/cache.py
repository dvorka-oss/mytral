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
import abc
from abc import abstractmethod

from mytral import loggers
from mytral import settings
from mytral import stats
from mytral import views
from mytral.backends import entities

"""MyTraL cache with in memory, memcached, Redis, ... do:

- the cache maps user ID to user DATA
- the cache is CONTROLLED by DATASET do
- the cache is used FROM within the datasets PERSISTENCE do
  as different do - like JSON, RDBMS, ... - have DIFFERENT
  ways how EFFICIENTLY they can calculate statistics (in memory vs. SQL query)
- METHOD @ dataset implementation ~ controls its cache:

  JSONDataset::list_gear_stats():
    if not self.cache.gear_stats():
      ... CALCULATION ...

    return self.cache.gear_stats()

"""


class MytralUserCache(abc.ABC):
    """All data of a particular MyTraL user - activities and settings."""

    def __init__(self, user_id: str, logger: loggers.MytralLogger) -> None:
        self.user_id = user_id
        self.logger = logger

    #
    # user
    #

    @abstractmethod
    def profile(self) -> settings.UserProfile | None:
        raise NotImplementedError

    @abstractmethod
    def set_profile(self, profile: settings.UserProfile) -> settings.UserProfile:
        raise NotImplementedError

    #
    # dataset
    #

    @abstractmethod
    def dataset_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def set_dataset_name(self, dataset_name: str):
        raise NotImplementedError

    #
    # activities
    #

    @abstractmethod
    def activities(self, dataset_name: str) -> dict[str, entities.ActivityEntity]:
        raise NotImplementedError

    @abstractmethod
    def set_activities(
        self,
        activities: dict[str, entities.ActivityEntity],
        dataset_name: str,
    ) -> dict[str, entities.ActivityEntity]:
        raise NotImplementedError

    @abstractmethod
    def activities_stats(self, dataset_name: str) -> stats.UserDatasetStats | None:
        raise NotImplementedError

    @abstractmethod
    def set_activities_stats(
        self, activities_stats: stats.UserDatasetStats
    ) -> stats.UserDatasetStats | None:
        raise NotImplementedError

    @abstractmethod
    def activities_years(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def activities_year(self, year: str) -> dict:
        raise NotImplementedError

    #
    # indices
    #

    @abstractmethod
    def profile_stats(self) -> stats.UserProfileStats | None:
        raise NotImplementedError

    @abstractmethod
    def set_profile_stats(
        self,
        profile_stats: stats.UserProfileStats,
    ) -> stats.UserProfileStats:
        raise NotImplementedError

    @abstractmethod
    def evict_profile_stats(self):
        raise NotImplementedError

    @abstractmethod
    def activity_types_stats(self) -> stats.UserActivityTypesStats | None:
        raise NotImplementedError

    @abstractmethod
    def set_activity_types_stats(
        self, activity_types_stats: stats.UserActivityTypesStats
    ) -> stats.UserActivityTypesStats:
        raise NotImplementedError

    @abstractmethod
    def evict_activity_types_stats(self):
        raise NotImplementedError

    @abstractmethod
    def exercises_stats(self) -> stats.UserExercisesStats | None:
        raise NotImplementedError

    @abstractmethod
    def set_exercises_stats(
        self, exercises_stats: stats.UserExercisesStats
    ) -> stats.UserExercisesStats | None:
        raise NotImplementedError

    @abstractmethod
    def evict_exercises_stats(self):
        raise NotImplementedError

    @abstractmethod
    def gear_stats(self) -> stats.UserGearStats | None:
        raise NotImplementedError

    @abstractmethod
    def set_gear_stats(
        self, gear_stats: stats.UserGearStats
    ) -> stats.UserGearStats | None:
        raise NotImplementedError

    @abstractmethod
    def evict_gear_stats(self):
        raise NotImplementedError

    @abstractmethod
    def outfits_stats(self) -> stats.UserOutfitsStats | None:
        raise NotImplementedError

    @abstractmethod
    def set_outfits_stats(
        self, outfits_stats: stats.UserOutfitsStats
    ) -> stats.UserOutfitsStats | None:
        raise NotImplementedError

    @abstractmethod
    def evict_outfits_stats(self):
        raise NotImplementedError

    @abstractmethod
    def symptoms_stats(self) -> stats.UserSymptomsStats | None:
        raise NotImplementedError

    @abstractmethod
    def set_symptoms_stats(
        self, symptoms_stats: stats.UserSymptomsStats
    ) -> stats.UserSymptomsStats:
        raise NotImplementedError

    @abstractmethod
    def evict_symptoms_stats(self):
        raise NotImplementedError

    @abstractmethod
    def laps_stats(self) -> stats.UserLapsStats | None:
        raise NotImplementedError

    @abstractmethod
    def set_laps_stats(self, laps_stats: stats.UserLapsStats) -> stats.UserLapsStats:
        raise NotImplementedError

    @abstractmethod
    def evict_laps_stats(self):
        raise NotImplementedError

    @abstractmethod
    def activity_type_heatmap(self) -> views.CalendarHeatmap:
        raise NotImplementedError

    @abstractmethod
    def sick_heatmap(self) -> views.CalendarHeatmap:
        raise NotImplementedError

    #
    # settings
    #

    @abstractmethod
    def activity_types(self) -> settings.UserActivityTypes | None:
        raise NotImplementedError

    @abstractmethod
    def set_activity_types(
        self, activity_types: settings.UserActivityTypes
    ) -> settings.UserActivityTypes:
        raise NotImplementedError

    @abstractmethod
    def gear(self) -> settings.UserGear | None:
        raise NotImplementedError

    @abstractmethod
    def set_gear(self, gear: settings.UserGear) -> settings.UserGear:
        raise NotImplementedError

    @abstractmethod
    def strava_gear(self) -> settings.StravaUserGear | None:
        raise NotImplementedError

    @abstractmethod
    def set_strava_gear(
        self, strava_gear: settings.StravaUserGear
    ) -> settings.StravaUserGear:
        raise NotImplementedError

    @abstractmethod
    def outfits(self) -> settings.UserOutfits | None:
        raise NotImplementedError

    @abstractmethod
    def set_outfits(self, outfits: settings.UserOutfits) -> settings.UserOutfits:
        raise NotImplementedError

    @abstractmethod
    def component_templates(self) -> settings.UserComponentTemplates | None:
        raise NotImplementedError

    @abstractmethod
    def set_component_templates(
        self, templates: settings.UserComponentTemplates
    ) -> settings.UserComponentTemplates:
        raise NotImplementedError

    @abstractmethod
    def goals(self) -> settings.UserGoals | None:
        raise NotImplementedError

    @abstractmethod
    def set_goals(self, goals: settings.UserGoals) -> settings.UserGoals:
        raise NotImplementedError

    @abstractmethod
    def symptoms(self) -> settings.UserSymptoms:
        raise NotImplementedError

    @abstractmethod
    def set_symptoms(self, symptoms: settings.UserSymptoms) -> settings.UserSymptoms:
        raise NotImplementedError

    @abstractmethod
    def exercises(self) -> settings.UserExercises:
        raise NotImplementedError

    @abstractmethod
    def set_exercises(
        self, exercises: settings.UserExercises
    ) -> settings.UserExercises:
        raise NotImplementedError

    @abstractmethod
    def laps(self) -> settings.UserLaps:
        raise NotImplementedError

    @abstractmethod
    def set_laps(self, laps: settings.UserLaps) -> settings.UserLaps:
        raise NotImplementedError

    #
    # runtime
    #

    @abstractmethod
    def evict_settings(self):
        raise NotImplementedError

    @abstractmethod
    def evict_indices(self):
        raise NotImplementedError

    @abstractmethod
    def evict_activities(self):
        raise NotImplementedError

    @abstractmethod
    def evict_on_activity_cud(self):
        raise NotImplementedError

    @abstractmethod
    def evict(self):
        raise NotImplementedError

    #
    # Banister / TRIMP Rocks
    #

    @abstractmethod
    def banister_rows(self) -> list | None:
        raise NotImplementedError

    @abstractmethod
    def set_banister_rows(self, rows: list) -> list:
        raise NotImplementedError

    @abstractmethod
    def memory_size(self) -> int:
        raise NotImplementedError


class MytralCache(abc.ABC):
    def __init__(self, logger: loggers.MytralLogger) -> None:
        self.logger = logger

    @abc.abstractmethod
    def user(self, user_id: str) -> MytralUserCache:
        """Get user cache for given user ID."""
        raise NotImplementedError

    @abc.abstractmethod
    def evict(self, user_id: str) -> None:
        """Evict user cache for given user ID."""
        raise NotImplementedError

    @abc.abstractmethod
    def memory_size(self) -> int:
        """Return size of the user cache in bytes - performs deep walk through cache
        entries.

        Returns
        -------
        int :
            Cache size in bytes.

        """
        raise NotImplementedError


class MytralCacheInitializer(abc.ABC):
    """Interface which is implemented by persistence do so that
    the desired data can be loaded to the cache on user login.

    """

    @abc.abstractmethod
    def init_user_cache(self, user_cache: MytralUserCache, user_id: str):
        raise NotImplementedError
