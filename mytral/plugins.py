# MyTraL: my trailing log
#
# Copyright (C) 2022-2026 Martin Dvorak <martin.dvorak@mindforger.com>
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
import enum
import pathlib

from mytral import app_logger
from mytral import settings
from mytral.backends import entities


class PluginType(enum.Enum):
    ACTIVITIES_IMPORT = "ACTIVITIES_IMPORT"
    ACTIVITY_IMPORT = "ACTIVITY_IMPORT"
    ENTITIES_IMPORT = "ENTITIES_IMPORT"


class Plugin:
    """MyTraL plugins allow users to bring their own:

    - activities
      ... from other services and formats
    - activity metrics
      ... to be calculated on the activity detail page
    - profile entities
      like goals, exercises, symptoms and laps

    ... and more. After gathering wide variety of training related data MyTraL becomes
    more valuable and useful - from normalization, to holistic view which can be
    leveraged in analytics/ML/AI use cases (Jupyter, LLM/agents, ML models).

    """

    NAME = "ABC plugin"
    # IMPROVE: consider Aurium for the description to be used in UI
    DESCRIPTION = "This is a parent class of all plugins."

    def __init__(self, name: str, description: str, plugin_type: PluginType):
        self.name = name or Plugin.NAME
        self.description = description or Plugin.DESCRIPTION
        self.plugin_type = plugin_type

    def key(self) -> str:
        return self.name.lower().replace(" ", "-")


class MytralEntityType(enum.Enum):
    ACTIVITIES = "activities"
    ACTIVITY_TYPES = "activity_types"
    COMPONENTS = "components"
    EXERCISES = "exercises"
    GEARS = "gears"
    GOALS = "goals"
    LAPS = "laps"
    OUTFITS = "outfits"
    SYMPTOMS = "symptoms"


class ImportPlugin(abc.ABC, Plugin):
    def __init__(
        self,
        name: str,
        description: str,
    ):
        """Constructor for the import plugin.

        Parameters
        ----------
        name : str
            Importer name to be used in the runtime - UI, logging, documentation.
        description : str
           Importer description - UI, logging, documentation.

        """
        Plugin.__init__(
            self,
            name=name,
            description=description,
            plugin_type=PluginType.ENTITIES_IMPORT,
        )

    @abc.abstractmethod
    def import_entities(
        self,
        datasets: dict[str, list[pathlib.Path] | pathlib.Path | str | list[dict]],
        user_profile: settings.UserProfile,
        **kwargs,
    ) -> dict[MytralEntityType, list]:
        """Import any MyTraL entity - components, gear, exercises, symptoms or
        activities.

        Parameters
        ----------
        datasets: dict[str, pathlib.Path | str]
           Data to be imported. Dictionary is formed by the use type ~ what is
           the purpose of this dataset, and either path(s) to the dataset(s) or
           the dataset itself by value as string, or list of activities as dictionaries
           (typically from JSON in different format).
        user_profile : mytral.users.UserProfile
           User profile of the user who is importing activities to be aware of user
           specific customizations and definitions.
        **kwargs : dict
            Additional arguments for specific do (e.g., entity maps).

        """
        raise NotImplementedError


class ActivitiesImportPlugin(abc.ABC, Plugin):
    def __init__(
        self,
        name: str,
        description: str,
    ):
        """Constructor for activities import plugin.

        Parameters
        ----------
        name : str
            Importer name to be used in the runtime - UI, logging, documentation.
        description : str
           Importer description - UI, logging, documentation.

        """
        Plugin.__init__(
            self,
            name=name,
            description=description,
            plugin_type=PluginType.ACTIVITIES_IMPORT,
        )

    @abc.abstractmethod
    def import_activities(
        self,
        datasets: dict[str, list[pathlib.Path] | pathlib.Path | str | list[dict]],
        user_profile: settings.UserProfile,
        output_path: pathlib.Path | None = None,
        **kwargs,
    ) -> list[entities.ActivityEntity]:
        """Import activities.

        Parameters
        ----------
        datasets: dict[str, pathlib.Path | str]
           Data to be imported. Dictionary is formed by the use type ~ what is
           the purpose of this dataset, and either path(s) to the dataset(s) or
           the dataset itself by value as string, or list of activities as dictionaries
           (typically from JSON in different format).
        user_profile : mytral.users.UserProfile
           User profile of the user who is importing activities to be aware of user
           specific customizations and definitions.
        output_path: pathlib.Path | None
           Optionally store activities as JSON file to given path.
        **kwargs : dict
            Additional arguments for specific do (e.g., entity maps).

        """
        raise NotImplementedError


class ActivityImportPlugin(abc.ABC, Plugin):
    def __init__(
        self,
        name: str,
        description: str,
        **kwargs,
    ):
        """Constructor for activities import plugin.

        Parameters
        ----------
        name : str
            Importer name to be used in the runtime - UI, logging, documentation.
        description : str
           Importer description - UI, logging, documentation.

        """
        Plugin.__init__(
            self,
            name=name,
            description=description,
            plugin_type=PluginType.ACTIVITY_IMPORT,
        )

    @abc.abstractmethod
    def import_activity(
        self,
        dataset_item: list[tuple[str, pathlib.Path | str | dict]],
        user_profile: settings.UserProfile,
    ) -> entities.ActivityEntity:
        """Import activity.

        Parameters
        ----------
        dataset_item: list[pathlib.Path]
           Data to be imported. Every tuple is formed by the use type - which is
           the purpose of the dataset, and either path to the dataset or the dataset
           itself by value as string, or dictionary (typically from JSON in different
           format).
        user_profile : mytral.users.UserProfile
           User profile of the user who is importing activities to be aware of user
           specific customizations and definitions.
        **kwargs : dict
            Additional arguments for specific do (e.g., entity maps).

        """
        raise NotImplementedError


class ActivityMetricPlugin:
    """Custom user metric to be shown in activity with any/specific activity type."""

    pass


class PredictionPlugin(abc.ABC, Plugin):
    """Custom user prediction to be shown in the predictions page."""

    pass


#
# reflection: registry of available plugins
#


class PluginsRegistry:
    def __init__(self):
        self.plugins = {}
        self.logger = app_logger

    def _sanity_check(self, plugin: Plugin) -> bool:
        self.logger.debug(f"Checking plugin: {plugin}")
        # TODO verify it is child class
        # TODO run per-class sanity check
        # TODO run plugin self-check() method
        return isinstance(plugin, Plugin)

    def register(self, plugin: Plugin):
        self.plugins[plugin.name] = plugin

    def unregister(self, plugin: Plugin):
        del self.plugins[plugin.name]

    def get_plugin(self, name: str) -> Plugin:
        try:
            return self.plugins[name]
        except KeyError as e:
            raise KeyError(
                f"Plugin {name} not registered - valid keys are: "
                f"{list(self.plugins.keys())}"
            ) from e

    def __str__(self):
        s = "Plugins:"
        for name, plugin in self.plugins.items():
            s += f"\n{name}: {plugin}"
        return s


registry = PluginsRegistry()
