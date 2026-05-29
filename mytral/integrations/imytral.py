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
import dataclasses
import json
import pathlib
import uuid

from mytral import app_logger
from mytral import loggers
from mytral import plugins
from mytral import settings
from mytral.backends import entities


class MyTraLImportPlugin(plugins.ImportPlugin):
    """Import MyTraL data in JSON format.

    File type detection
    -------------------
    The entity type is inferred from the keys present in the first list element.
    Each JSON export file must be a JSON **list** (``[{...}, ...]``).

    """

    NAME = "MyTraL import"
    DESCRIPTION = (
        "Imports MyTraL data in JSON format - activities, exercises, gear, components, "
        "goals, laps, outfits, and symptoms."
    )

    USE_TYPE_JSON = "USE_TYPE_JSON"

    def __init__(
        self,
        logger: loggers.MytralLogger | None = None,
    ):
        """Constructor."""
        plugins.ImportPlugin.__init__(
            self,
            name=MyTraLImportPlugin.NAME,
            description=MyTraLImportPlugin.DESCRIPTION,
        )

        self.log_name = f"[{self.name}]"
        self.logger = logger or app_logger

    def import_entities(
        self,
        datasets: dict[str, list[pathlib.Path] | pathlib.Path | str | list[dict]],
        user_profile: settings.UserProfile,
        output_path: pathlib.Path | None = None,
        **kwargs,
    ) -> dict[plugins.MytralEntityType, list]:
        """Import MyTraL entities from a JSON file.

        Parameters
        ----------
        datasets : dict
            Must contain the key ``USE_TYPE_JSON`` mapping to a
            :class:`pathlib.Path` pointing at the exported JSON file.
        user_profile : settings.UserProfile
            Profile of the user the entities will be imported for.
        output_path : pathlib.Path or None
            Unused; kept for interface symmetry.
        **kwargs
            Additional keyword arguments (ignored).

        Returns
        -------
        dict[plugins.MytralEntityType, list]
            Mapping of detected entity type to the list of deserialized objects.

        Raises
        ------
        ValueError
            When the required JSON dataset path is missing or the file type
            cannot be detected.
        FileNotFoundError
            When the JSON file does not exist.

        """
        _correlation_id: str = kwargs.get("correlation_id", str(uuid.uuid4()))

        json_path = datasets.get(MyTraLImportPlugin.USE_TYPE_JSON)
        if not json_path:
            raise ValueError(
                f"{self.log_name} MyTraL JSON file is required but was not provided."
            )
        json_path = pathlib.Path(json_path)
        if not json_path.exists():
            raise FileNotFoundError(
                f"{self.log_name} MyTraL JSON file not found: {json_path}"
            )

        self.logger.info(
            f"{self.log_name} Loading MyTraL JSON",
            json_path=str(json_path),
        )

        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        if not json_data:
            self.logger.warning(f"{self.log_name} JSON file is empty")
            return {}

        entity_type = self._detect_file_type(json_data)
        self.logger.info(
            f"{self.log_name} Detected entity type: {entity_type.value}",
            count=len(json_data),
        )

        result = self._deserialize(entity_type=entity_type, json_data=json_data)

        self.logger.info(
            f"{self.log_name} Imported entities",
            entity_type=entity_type.value,
            count=len(result),
        )

        return {entity_type: result}

    def _detect_file_type(self, json_data: list) -> plugins.MytralEntityType:
        """Detect the MyTraL entity type from the first item in the list.

        Parameters
        ----------
        json_data : list
            Parsed JSON data (must be a non-empty list of dicts).

        Returns
        -------
        plugins.MytralEntityType
            Detected entity type.

        Raises
        ------
        ValueError
            When the entity type cannot be determined.

        """
        if not isinstance(json_data, list) or not json_data:
            raise ValueError(
                f"{self.log_name} expected a non-empty JSON list, "
                f"got: {type(json_data)}"
            )

        first = json_data[0]

        if "when_year" in first and "activity_type_key" in first:
            return plugins.MytralEntityType.ACTIVITIES
        if "is_distance" in first:
            return plugins.MytralEntityType.ACTIVITY_TYPES
        # components before gear: both have vendor-like fields; components have
        # default_service_km while gear has ``retired`` + ``components``
        if "default_service_km" in first:
            return plugins.MytralEntityType.COMPONENTS
        if "muscle_groups" in first:
            return plugins.MytralEntityType.EXERCISES
        if "vendor" in first and "retired" in first and "components" in first:
            return plugins.MytralEntityType.GEARS
        if "urgency" in first and "importance" in first:
            return plugins.MytralEntityType.GOALS
        if "default_distance" in first and "default_duration" in first:
            return plugins.MytralEntityType.LAPS
        if "body_parts" in first:
            return plugins.MytralEntityType.SYMPTOMS
        if "activity_type" in first and "name" in first:
            return plugins.MytralEntityType.OUTFITS

        raise ValueError(
            f"{self.log_name} unable to determine MyTraL JSON file type "
            f"from keys: {list(first.keys())}"
        )

    def _deserialize(
        self,
        entity_type: plugins.MytralEntityType,
        json_data: list,
    ) -> list:
        """Deserialize JSON list into typed entity objects.

        Parameters
        ----------
        entity_type : plugins.MytralEntityType
            Target entity type.
        json_data : list
            Parsed JSON list of dicts.

        Returns
        -------
        list
            Deserialized entity objects.

        """
        if entity_type == plugins.MytralEntityType.ACTIVITIES:
            known_fields = {f.name for f in dataclasses.fields(entities.ActivityEntity)}
            return [
                entities.ActivityEntity(
                    **{k: v for k, v in item.items() if k in known_fields}
                )
                for item in json_data
            ]

        if entity_type == plugins.MytralEntityType.ACTIVITY_TYPES:
            return [settings.ActivityType.from_dict(item) for item in json_data]

        if entity_type == plugins.MytralEntityType.COMPONENTS:
            return [settings.ComponentTemplate.from_dict(item) for item in json_data]

        if entity_type == plugins.MytralEntityType.EXERCISES:
            return [settings.Exercise.from_dict(item) for item in json_data]

        if entity_type == plugins.MytralEntityType.GEARS:
            return [settings.Gear.from_dict(item) for item in json_data]

        if entity_type == plugins.MytralEntityType.GOALS:
            return [settings.Goal.from_dict(item) for item in json_data]

        if entity_type == plugins.MytralEntityType.LAPS:
            return [settings.Lap.from_dict(item) for item in json_data]

        if entity_type == plugins.MytralEntityType.OUTFITS:
            return [settings.Outfit.from_dict(item) for item in json_data]

        if entity_type == plugins.MytralEntityType.SYMPTOMS:
            return [settings.Symptom.from_dict(item) for item in json_data]

        raise ValueError(f"{self.log_name} unsupported entity type: {entity_type}")


# PLUGINS REGISTRY: register MyTraL import plugin
plugins.registry.register(MyTraLImportPlugin())
