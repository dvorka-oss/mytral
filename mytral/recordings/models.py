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
"""Format-agnostic recording data models."""

import dataclasses
import datetime
import enum


@dataclasses.dataclass
class RecordingData:
    """Format-agnostic timeseries extracted from any recording file.

    Parameters
    ----------
    timestamps : list[datetime.datetime]
        Ordered list of sample timestamps.
    hr_values : list[int | None]
        Heart rate samples (bpm), nullable.
    speed_values : list[float | None]
        Speed samples (km/h), nullable.
    cadence_values : list[int | None]
        Cadence samples (rpm/spm), nullable.
    altitude_values : list[float | None]
        Altitude samples (metres), nullable.
    lat_values : list[float | None]
        Latitude samples (degrees), nullable.
    lon_values : list[float | None]
        Longitude samples (degrees), nullable.
    power_values : list[float | None]
        Power samples (W), nullable.
    has_speed : bool
        Whether speed channel has any non-null values.
    has_cadence : bool
        Whether cadence channel has any non-null values.
    has_altitude : bool
        Whether altitude channel has any non-null values.
    has_gps : bool
        Whether GPS (lat/lon) channel has any non-null values.
    has_power : bool
        Whether power channel has any non-null values.
    source_format : str
        Recording source format: "fit" | "gpx" | "hrm".
    """

    timestamps: list[datetime.datetime]
    hr_values: list[int | None]
    speed_values: list[float | None]
    cadence_values: list[int | None]
    altitude_values: list[float | None]
    lat_values: list[float | None]
    lon_values: list[float | None]
    power_values: list[float | None]
    has_speed: bool
    has_cadence: bool
    has_altitude: bool
    has_gps: bool
    has_power: bool
    source_format: str


@dataclasses.dataclass
class RecordingSummary:
    """Activity-level summary extracted from a recording file.

    All fields default to None; extractors populate what the format provides.

    Parameters
    ----------
    activity_type_key : str | None
        MyTraL activity type display name string (e.g. "run", "ride").
    when : datetime.datetime | None
        Activity start timestamp.
    hours : int | None
        Duration hours component.
    minutes : int | None
        Duration minutes component.
    seconds : int | None
        Duration seconds component.
    distance : int | None
        Total distance in metres.
    kcal : int | None
        Total energy expenditure in kilocalories.
    avg_hr : int | None
        Average heart rate (bpm).
    max_hr : int | None
        Maximum heart rate (bpm).
    avg_cadence : int | None
        Average cadence (rpm/spm).
    max_cadence : int | None
        Maximum cadence (rpm/spm).
    avg_speed : float | None
        Average speed (km/h).
    max_speed : float | None
        Maximum speed (km/h).
    avg_watts : float | None
        Average power (W).
    max_watts : float | None
        Maximum power (W).
    elevation_gain : int | None
        Total elevation gain (metres).
    name_hint : str | None
        Optional activity name from file metadata.
    """

    activity_type_key: str | None = None
    when: datetime.datetime | None = None
    hours: int | None = None
    minutes: int | None = None
    seconds: int | None = None
    distance: int | None = None
    kcal: int | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    avg_cadence: int | None = None
    max_cadence: int | None = None
    avg_speed: float | None = None
    max_speed: float | None = None
    avg_watts: float | None = None
    max_watts: float | None = None
    elevation_gain: int | None = None
    name_hint: str | None = None


class RecordingFmt(enum.Enum):
    """Supported recording file formats."""

    FIT = ".fit"
    GPX = ".gpx"
    HRM = ".hrm"
