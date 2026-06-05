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
"""File-based cache for 3D IRM computation results.

Caches WorkoutStrainBreakdown, DailyStrainRow, Irm3dStateRow, and rendered
Bokeh chart output keyed by a hash of the power model parameters. When the
athlete's CP/W′/Pmax values change, the cache is automatically invalidated.

Cache file location: <user_data_dir>/blobs/irm3d_cache.json
"""

import dataclasses
import datetime
import hashlib
import json
import os

from mytral.metrics import irm3d

_IRM3D_CACHE_FILENAME = "irm3d_cache.json"


class Irm3dJsonEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles date and dataclass serialization."""

    def default(self, o):
        if isinstance(o, datetime.date):
            return {"__date__": True, "value": o.isoformat()}
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


def _json_hook(dct: dict) -> dict | datetime.date:
    """Custom JSON decoder hook for date and dataclass deserialization."""
    if dct.get("__date__") is True:
        return datetime.date.fromisoformat(dct["value"])
    return dct


def compute_model_params_hash(model_params: irm3d.PowerModelParams) -> str:
    """Compute a deterministic hash of the power model parameters.

    Parameters
    ----------
    model_params : PowerModelParams
        CP / W′ / Pmax values used for the 3D IRM computation.

    Returns
    -------
    str
        Hex-encoded SHA-256 hash of the serialized parameters.
    """
    key = (
        f"{model_params.cp_watts:.2f}"
        f"|{model_params.w_prime_joules:.2f}"
        f"|{model_params.pmax_watts:.2f}"
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _cache_file_path(user_data_dir: str) -> str:
    """Resolve the cache file path for a given user data directory."""
    return os.path.join(user_data_dir, "blobs", _IRM3D_CACHE_FILENAME)


class Irm3dFileCache:
    """File-backed cache for 3D IRM computation results.

    Parameters
    ----------
    user_data_dir : str
        Absolute path to the user's data directory (the directory containing
        ``activities-*.json``, ``blobs/``, etc.).
    """

    def __init__(self, user_data_dir: str) -> None:
        self._user_data_dir = user_data_dir

    def load(
        self,
    ) -> dict | None:
        """Load cached IRM3D data if the cache file exists.

        Returns
        -------
        dict or None
            The cached data dict, or None if the cache file does not exist
            or cannot be parsed.
        """
        cache_path = _cache_file_path(self._user_data_dir)
        if not os.path.isfile(cache_path):
            return None
        try:
            with open(cache_path, "r", encoding="utf-8") as fh:
                return json.load(fh, object_hook=_json_hook)
        except (json.JSONDecodeError, OSError):
            return None

    def save(self, cache_data: dict) -> None:
        """Persist IRM3D cache data to disk.

        Parameters
        ----------
        cache_data : dict
            Cache payload to persist. Must be JSON-serializable with the
            custom ``Irm3dJsonEncoder``.
        """
        cache_path = _cache_file_path(self._user_data_dir)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(cache_data, fh, cls=Irm3dJsonEncoder, indent=2)

    def invalidate(self) -> None:
        """Remove the cache file if it exists."""
        cache_path = _cache_file_path(self._user_data_dir)
        if os.path.isfile(cache_path):
            try:
                os.remove(cache_path)
            except OSError:
                pass
