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

"""Parquet conversion layer for FIT, GPX, TCX, Polar HRM, and GoldenCheetah CSV files.

All recording formats are converted to a canonical Parquet schema that is
format-agnostic and loaded at analysis time by the chart rendering code.

Schema
------
ts_unix_ms : Int64        — Unix epoch milliseconds (timezone-agnostic)
hr         : Int32 (null) — heart rate (bpm)
speed      : Float64 (null) — speed (km/h)
cadence    : Int32 (null) — cadence (rpm/spm)
altitude   : Float64 (null) — altitude (metres)
lat        : Float64 (null) — latitude (degrees)
lon        : Float64 (null) — longitude (degrees)
power      : Float64 (null) — power (W)
has_speed  : Boolean — file-level flag stored on every row
has_cadence : Boolean
has_altitude : Boolean
has_gps    : Boolean
has_power  : Boolean
source_format : Utf8 — "fit" / "gpx" / "tcx" / "hrm"
"""

import datetime
import io

import defusedxml.ElementTree
import polars

from mytral.recordings import tcx_extractor
from mytral.recordings.models import RecordingData


def fit_to_parquet(fit_data: bytes) -> bytes:
    """Parse FIT bytes and return canonical Parquet bytes.

    Parameters
    ----------
    fit_data : bytes
        Raw FIT file content.

    Returns
    -------
    bytes
        Parquet-encoded bytes using the canonical schema.
    """
    from fit_tool.fit_file import FitFile
    from fit_tool.profile.messages.record_message import RecordMessage

    ts_unix_ms_list: list[int] = []
    hr_list: list[int | None] = []
    speed_list: list[float | None] = []
    cadence_list: list[int | None] = []
    altitude_list: list[float | None] = []
    power_list: list[float | None] = []
    has_speed = False
    has_cadence = False
    has_altitude = False
    has_power = False

    try:
        fit = FitFile.from_bytes(fit_data, check_crc=False)
    except Exception:
        # return empty parquet on parse failure
        fit = None

    if fit is not None:
        for record in fit.records:
            message = record.message
            if not isinstance(message, RecordMessage):
                continue
            ts_ms = message.timestamp
            if ts_ms is None:
                continue
            ts_unix_ms_list.append(int(ts_ms))

            hr = message.heart_rate
            hr_list.append(int(hr) if hr is not None else None)

            speed_ms = message.speed
            if speed_ms is not None and speed_ms > 0:
                speed_list.append(round(float(speed_ms) * 3.6, 2))
                has_speed = True
            else:
                speed_list.append(None)

            cad = message.cadence
            if cad is not None and cad > 0:
                cadence_list.append(int(cad))
                has_cadence = True
            else:
                cadence_list.append(None)

            alt = message.altitude
            if alt is not None:
                altitude_list.append(float(alt))
                has_altitude = True
            else:
                altitude_list.append(None)

            pwr = message.power
            if pwr is not None and pwr > 0:
                power_list.append(float(pwr))
                has_power = True
            else:
                power_list.append(None)

    n = len(ts_unix_ms_list)
    lat_list: list[float | None] = [None] * n
    lon_list: list[float | None] = [None] * n

    df = polars.DataFrame(
        {
            "ts_unix_ms": polars.Series(ts_unix_ms_list, dtype=polars.Int64),
            "hr": polars.Series(hr_list, dtype=polars.Int32),
            "speed": polars.Series(speed_list, dtype=polars.Float64),
            "cadence": polars.Series(cadence_list, dtype=polars.Int32),
            "altitude": polars.Series(altitude_list, dtype=polars.Float64),
            "lat": polars.Series(lat_list, dtype=polars.Float64),
            "lon": polars.Series(lon_list, dtype=polars.Float64),
            "power": polars.Series(power_list, dtype=polars.Float64),
            "has_speed": polars.Series([has_speed] * n, dtype=polars.Boolean),
            "has_cadence": polars.Series([has_cadence] * n, dtype=polars.Boolean),
            "has_altitude": polars.Series([has_altitude] * n, dtype=polars.Boolean),
            "has_gps": polars.Series([False] * n, dtype=polars.Boolean),
            "has_power": polars.Series([has_power] * n, dtype=polars.Boolean),
            "source_format": polars.Series(["fit"] * n, dtype=polars.Utf8),
        }
    )

    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


def gpx_to_parquet(gpx_data: bytes) -> bytes:
    """Parse GPX bytes and return canonical Parquet bytes.

    Parameters
    ----------
    gpx_data : bytes
        Raw GPX file content.

    Returns
    -------
    bytes
        Parquet-encoded bytes using the canonical schema.
    """
    _NS_TPX = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"

    ts_unix_ms_list: list[int] = []
    hr_list: list[int | None] = []
    cadence_list: list[int | None] = []
    altitude_list: list[float | None] = []
    lat_list: list[float | None] = []
    lon_list: list[float | None] = []
    has_cadence = False
    has_altitude = False
    has_hr = False

    try:
        # strip BOM if present
        cleaned = gpx_data.lstrip(b"\xef\xbb\xbf")
        root = defusedxml.ElementTree.fromstring(cleaned)
    except Exception:
        root = None

    if root is not None:
        # resolve namespace
        tag = root.tag
        ns = ""
        if "}" in tag:
            ns = tag.split("}")[0] + "}"

        for trkpt in root.iter(f"{ns}trkpt"):
            lat_s = trkpt.get("lat")
            lon_s = trkpt.get("lon")
            if lat_s is None or lon_s is None:
                continue

            lat_val = float(lat_s)
            lon_val = float(lon_s)

            # timestamp
            time_el = trkpt.find(f"{ns}time")
            if time_el is None or not time_el.text:
                continue
            try:
                dt = datetime.datetime.fromisoformat(
                    time_el.text.replace("Z", "+00:00")
                )
                ts_ms = int(dt.timestamp() * 1000)
            except ValueError:
                continue

            ts_unix_ms_list.append(ts_ms)
            lat_list.append(lat_val)
            lon_list.append(lon_val)

            # elevation
            ele_el = trkpt.find(f"{ns}ele")
            if ele_el is not None and ele_el.text:
                try:
                    altitude_list.append(float(ele_el.text))
                    has_altitude = True
                except ValueError:
                    altitude_list.append(None)
            else:
                altitude_list.append(None)

            # HR and cadence from TrackPointExtension
            hr_val: int | None = None
            cad_val: int | None = None
            ext_el = trkpt.find(f"{ns}extensions")
            if ext_el is not None:
                hr_el = ext_el.find(f".//{{{_NS_TPX}}}hr")
                if hr_el is not None and hr_el.text:
                    try:
                        hr_val = int(hr_el.text)
                        has_hr = True
                    except ValueError:
                        pass
                cad_el = ext_el.find(f".//{{{_NS_TPX}}}cad")
                if cad_el is not None and cad_el.text:
                    try:
                        cad_val = int(cad_el.text)
                        has_cadence = True
                    except ValueError:
                        pass
            hr_list.append(hr_val)
            cadence_list.append(cad_val)

    n = len(ts_unix_ms_list)
    speed_list: list[float | None] = [None] * n
    power_list: list[float | None] = [None] * n
    has_gps = n > 0
    _ = has_hr  # used implicitly via hr_list content

    df = polars.DataFrame(
        {
            "ts_unix_ms": polars.Series(ts_unix_ms_list, dtype=polars.Int64),
            "hr": polars.Series(hr_list, dtype=polars.Int32),
            "speed": polars.Series(speed_list, dtype=polars.Float64),
            "cadence": polars.Series(cadence_list, dtype=polars.Int32),
            "altitude": polars.Series(altitude_list, dtype=polars.Float64),
            "lat": polars.Series(lat_list, dtype=polars.Float64),
            "lon": polars.Series(lon_list, dtype=polars.Float64),
            "power": polars.Series(power_list, dtype=polars.Float64),
            "has_speed": polars.Series([False] * n, dtype=polars.Boolean),
            "has_cadence": polars.Series([has_cadence] * n, dtype=polars.Boolean),
            "has_altitude": polars.Series([has_altitude] * n, dtype=polars.Boolean),
            "has_gps": polars.Series([has_gps] * n, dtype=polars.Boolean),
            "has_power": polars.Series([False] * n, dtype=polars.Boolean),
            "source_format": polars.Series(["gpx"] * n, dtype=polars.Utf8),
        }
    )

    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


def tcx_to_parquet(tcx_data: bytes) -> bytes:
    """Parse TCX bytes and return canonical Parquet bytes."""
    ts_unix_ms_list: list[int] = []
    hr_list: list[int | None] = []
    speed_list: list[float | None] = []
    cadence_list: list[int | None] = []
    altitude_list: list[float | None] = []
    lat_list: list[float | None] = []
    lon_list: list[float | None] = []
    power_list: list[float | None] = []
    has_cadence = False
    has_altitude = False
    has_gps = False
    has_speed = False
    has_power = False

    try:
        cleaned = tcx_data.lstrip(b"\xef\xbb\xbf")
        root = defusedxml.ElementTree.fromstring(cleaned)
    except Exception:
        root = None

    if root is not None:
        tag = root.tag
        ns = ""
        if "}" in tag:
            ns = tag.split("}")[0] + "}"

        for trackpoint in root.iter(f"{ns}Trackpoint"):
            time_el = trackpoint.find(f"{ns}Time")
            if time_el is None or not time_el.text:
                continue
            try:
                dt = datetime.datetime.fromisoformat(
                    time_el.text.replace("Z", "+00:00")
                )
            except ValueError:
                continue

            ts_unix_ms_list.append(int(dt.timestamp() * 1000))

            hr_el = trackpoint.find(f"{ns}HeartRateBpm/{ns}Value")
            if hr_el is not None and hr_el.text:
                try:
                    hr_list.append(int(hr_el.text))
                except ValueError:
                    hr_list.append(None)
            else:
                hr_list.append(None)

            cadence_el = trackpoint.find(f"{ns}Cadence")
            if cadence_el is not None and cadence_el.text:
                try:
                    cadence_list.append(int(float(cadence_el.text)))
                    has_cadence = True
                except ValueError:
                    cadence_list.append(None)
            else:
                cadence_list.append(None)

            altitude_el = trackpoint.find(f"{ns}AltitudeMeters")
            if altitude_el is not None and altitude_el.text:
                try:
                    altitude_list.append(float(altitude_el.text))
                    has_altitude = True
                except ValueError:
                    altitude_list.append(None)
            else:
                altitude_list.append(None)

            pos_lat_el = trackpoint.find(f"{ns}Position/{ns}LatitudeDegrees")
            pos_lon_el = trackpoint.find(f"{ns}Position/{ns}LongitudeDegrees")
            if (
                pos_lat_el is not None
                and pos_lon_el is not None
                and pos_lat_el.text
                and pos_lon_el.text
            ):
                try:
                    lat_list.append(float(pos_lat_el.text))
                    lon_list.append(float(pos_lon_el.text))
                    has_gps = True
                except ValueError:
                    lat_list.append(None)
                    lon_list.append(None)
            else:
                lat_list.append(None)
                lon_list.append(None)

            speed_el = trackpoint.find(f".//{{{tcx_extractor._NS_TPX}}}Speed")
            if speed_el is not None and speed_el.text:
                try:
                    speed_list.append(round(float(speed_el.text) * 3.6, 2))
                    has_speed = True
                except ValueError:
                    speed_list.append(None)
            else:
                speed_list.append(None)

            power_el = trackpoint.find(f".//{{{tcx_extractor._NS_TPX}}}Watts")
            if power_el is not None and power_el.text:
                try:
                    power_list.append(float(power_el.text))
                    has_power = True
                except ValueError:
                    power_list.append(None)
            else:
                power_list.append(None)

    n = len(ts_unix_ms_list)
    df = polars.DataFrame(
        {
            "ts_unix_ms": polars.Series(ts_unix_ms_list, dtype=polars.Int64),
            "hr": polars.Series(hr_list, dtype=polars.Int32),
            "speed": polars.Series(speed_list, dtype=polars.Float64),
            "cadence": polars.Series(cadence_list, dtype=polars.Int32),
            "altitude": polars.Series(altitude_list, dtype=polars.Float64),
            "lat": polars.Series(lat_list, dtype=polars.Float64),
            "lon": polars.Series(lon_list, dtype=polars.Float64),
            "power": polars.Series(power_list, dtype=polars.Float64),
            "has_speed": polars.Series([has_speed] * n, dtype=polars.Boolean),
            "has_cadence": polars.Series([has_cadence] * n, dtype=polars.Boolean),
            "has_altitude": polars.Series([has_altitude] * n, dtype=polars.Boolean),
            "has_gps": polars.Series([has_gps] * n, dtype=polars.Boolean),
            "has_power": polars.Series([has_power] * n, dtype=polars.Boolean),
            "source_format": polars.Series(["tcx"] * n, dtype=polars.Utf8),
        }
    )

    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


def hrm_to_parquet(hrm_data: dict) -> bytes:
    """Convert a parsed Polar HRM data dict to canonical Parquet bytes.

    Parameters
    ----------
    hrm_data : dict
        Dict as returned by ``polar_hrm.parse_hrm()``.  Expected keys:
        ``rows``, ``has_speed``, ``has_cadence``, ``has_altitude``,
        ``interval_s``, ``start_hour``, ``start_minute``, ``start_second``,
        ``date`` (YYYYMMDD int).

    Returns
    -------
    bytes
        Parquet-encoded bytes using the canonical schema.
    """
    rows: list[dict] = hrm_data.get("rows", [])
    has_speed: bool = bool(hrm_data.get("has_speed", False))
    has_cadence: bool = bool(hrm_data.get("has_cadence", False))
    has_altitude: bool = bool(hrm_data.get("has_altitude", False))
    interval_s: int = int(hrm_data.get("interval_s", 5))
    start_hour: int = int(hrm_data.get("start_hour", 0))
    start_minute: int = int(hrm_data.get("start_minute", 0))
    start_second: int = int(hrm_data.get("start_second", 0))
    date_int: int = int(hrm_data.get("date", 0))

    # parse start date
    year = date_int // 10000
    month = (date_int % 10000) // 100
    day = date_int % 100
    if year == 0:
        year, month, day = 2000, 1, 1

    try:
        start_dt = datetime.datetime(
            year, month, day, start_hour, start_minute, start_second
        )
    except ValueError:
        start_dt = datetime.datetime(2000, 1, 1)

    ts_unix_ms_list: list[int] = []
    hr_list: list[int | None] = []
    speed_list: list[float | None] = []
    cadence_list: list[int | None] = []
    altitude_list: list[float | None] = []

    for i, row in enumerate(rows):
        dt = start_dt + datetime.timedelta(seconds=i * interval_s)
        ts_unix_ms_list.append(int(dt.timestamp() * 1000))
        hr_list.append(row.get("hr"))
        # speed_01kmh is in 0.1 km/h units
        if has_speed and "speed_01kmh" in row:
            speed_list.append(round(row["speed_01kmh"] / 10.0, 2))
        else:
            speed_list.append(None)
        if has_cadence and "cadence_rpm" in row:
            cadence_list.append(row["cadence_rpm"])
        else:
            cadence_list.append(None)
        if has_altitude and "altitude_m" in row:
            altitude_list.append(float(row["altitude_m"]))
        else:
            altitude_list.append(None)

    n = len(ts_unix_ms_list)
    lat_list: list[float | None] = [None] * n
    lon_list: list[float | None] = [None] * n
    power_list: list[float | None] = [None] * n

    df = polars.DataFrame(
        {
            "ts_unix_ms": polars.Series(ts_unix_ms_list, dtype=polars.Int64),
            "hr": polars.Series(hr_list, dtype=polars.Int32),
            "speed": polars.Series(speed_list, dtype=polars.Float64),
            "cadence": polars.Series(cadence_list, dtype=polars.Int32),
            "altitude": polars.Series(altitude_list, dtype=polars.Float64),
            "lat": polars.Series(lat_list, dtype=polars.Float64),
            "lon": polars.Series(lon_list, dtype=polars.Float64),
            "power": polars.Series(power_list, dtype=polars.Float64),
            "has_speed": polars.Series([has_speed] * n, dtype=polars.Boolean),
            "has_cadence": polars.Series([has_cadence] * n, dtype=polars.Boolean),
            "has_altitude": polars.Series([has_altitude] * n, dtype=polars.Boolean),
            "has_gps": polars.Series([False] * n, dtype=polars.Boolean),
            "has_power": polars.Series([False] * n, dtype=polars.Boolean),
            "source_format": polars.Series(["hrm"] * n, dtype=polars.Utf8),
        }
    )

    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


def gc_csv_to_parquet(csv_data: bytes, start_dt: datetime.datetime) -> bytes:
    """Parse a GoldenCheetah OSF CSV and return canonical Parquet bytes.

    Parameters
    ----------
    csv_data : bytes
        Raw CSV content.  Fixed schema: secs,km,power,hr,cad,alt
        Values are empty strings when a sensor channel has no data.
    start_dt : datetime.datetime
        UTC start time of the activity; used to derive per-row timestamps.

    Returns
    -------
    bytes
        Parquet-encoded bytes using the canonical schema.
    """
    ts_unix_ms_list: list[int] = []
    hr_list: list[int | None] = []
    speed_list: list[float | None] = []
    cadence_list: list[int | None] = []
    altitude_list: list[float | None] = []
    power_list: list[float | None] = []
    has_hr = False
    has_speed = False
    has_cadence = False
    has_altitude = False
    has_power = False

    prev_km: float | None = None
    prev_secs: float | None = None

    try:
        lines = csv_data.decode("utf-8", errors="replace").splitlines()
    except Exception:
        lines = []

    if len(lines) >= 2:
        col = {name.strip(): idx for idx, name in enumerate(lines[0].split(","))}
        secs_idx = col.get("secs", 0)
        km_idx = col.get("km")
        power_idx = col.get("power")
        hr_idx = col.get("hr")
        cad_idx = col.get("cad")
        alt_idx = col.get("alt")

        for raw_line in lines[1:]:
            if not raw_line.strip():
                continue
            parts = raw_line.split(",")

            try:
                secs = float(parts[secs_idx])
            except (IndexError, ValueError):
                continue

            ts = start_dt + datetime.timedelta(seconds=secs)
            ts_unix_ms_list.append(int(ts.timestamp() * 1000))

            # HR (bpm)
            hr_val: int | None = None
            if hr_idx is not None and hr_idx < len(parts):
                raw = parts[hr_idx].strip()
                if raw:
                    try:
                        v = float(raw)
                        if v > 0:
                            hr_val = int(round(v))
                            has_hr = True
                    except ValueError:
                        pass
            hr_list.append(hr_val)

            # power (W)
            pwr_val: float | None = None
            if power_idx is not None and power_idx < len(parts):
                raw = parts[power_idx].strip()
                if raw:
                    try:
                        v = float(raw)
                        if v >= 0:
                            pwr_val = v
                            has_power = True
                    except ValueError:
                        pass
            power_list.append(pwr_val)

            # cadence (rpm)
            cad_val: int | None = None
            if cad_idx is not None and cad_idx < len(parts):
                raw = parts[cad_idx].strip()
                if raw:
                    try:
                        v = float(raw)
                        if v > 0:
                            cad_val = int(round(v))
                            has_cadence = True
                    except ValueError:
                        pass
            cadence_list.append(cad_val)

            # altitude (m)
            alt_val: float | None = None
            if alt_idx is not None and alt_idx < len(parts):
                raw = parts[alt_idx].strip()
                if raw:
                    try:
                        alt_val = float(raw)
                        has_altitude = True
                    except ValueError:
                        pass
            altitude_list.append(alt_val)

            # speed derived from consecutive km differences
            spd_val: float | None = None
            if km_idx is not None and km_idx < len(parts):
                raw = parts[km_idx].strip()
                if raw:
                    try:
                        km_val = float(raw)
                        if prev_km is not None and prev_secs is not None:
                            d_km = km_val - prev_km
                            d_secs = secs - prev_secs
                            if d_secs > 0 and d_km >= 0:
                                spd_val = round(d_km / d_secs * 3600, 2)
                                if spd_val > 0:
                                    has_speed = True
                        prev_km = km_val
                        prev_secs = secs
                    except ValueError:
                        pass
            speed_list.append(spd_val)

    n = len(ts_unix_ms_list)
    lat_list: list[float | None] = [None] * n
    lon_list: list[float | None] = [None] * n
    _ = has_hr  # implicit in hr_list content

    df = polars.DataFrame(
        {
            "ts_unix_ms": polars.Series(ts_unix_ms_list, dtype=polars.Int64),
            "hr": polars.Series(hr_list, dtype=polars.Int32),
            "speed": polars.Series(speed_list, dtype=polars.Float64),
            "cadence": polars.Series(cadence_list, dtype=polars.Int32),
            "altitude": polars.Series(altitude_list, dtype=polars.Float64),
            "lat": polars.Series(lat_list, dtype=polars.Float64),
            "lon": polars.Series(lon_list, dtype=polars.Float64),
            "power": polars.Series(power_list, dtype=polars.Float64),
            "has_speed": polars.Series([has_speed] * n, dtype=polars.Boolean),
            "has_cadence": polars.Series([has_cadence] * n, dtype=polars.Boolean),
            "has_altitude": polars.Series([has_altitude] * n, dtype=polars.Boolean),
            "has_gps": polars.Series([False] * n, dtype=polars.Boolean),
            "has_power": polars.Series([has_power] * n, dtype=polars.Boolean),
            "source_format": polars.Series(["gc_csv"] * n, dtype=polars.Utf8),
        }
    )

    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


def load_parquet(parquet_data: bytes) -> RecordingData:
    """Deserialise Parquet bytes into a RecordingData for chart rendering.

    Parameters
    ----------
    parquet_data : bytes
        Parquet-encoded bytes produced by any *_to_parquet() function.

    Returns
    -------
    RecordingData
        Format-agnostic recording data ready for chart rendering.
    """
    df = polars.read_parquet(io.BytesIO(parquet_data))

    if df.is_empty():
        return RecordingData(
            timestamps=[],
            hr_values=[],
            speed_values=[],
            cadence_values=[],
            altitude_values=[],
            lat_values=[],
            lon_values=[],
            power_values=[],
            has_speed=False,
            has_cadence=False,
            has_altitude=False,
            has_gps=False,
            has_power=False,
            source_format="",
        )

    timestamps: list[datetime.datetime] = [
        datetime.datetime.fromtimestamp(ts_ms / 1000.0, tz=datetime.timezone.utc)
        for ts_ms in df["ts_unix_ms"].to_list()
    ]

    has_speed = bool(df["has_speed"][0])
    has_cadence = bool(df["has_cadence"][0])
    has_altitude = bool(df["has_altitude"][0])
    has_gps = bool(df["has_gps"][0])
    has_power = bool(df["has_power"][0])
    source_format = str(df["source_format"][0]) if len(df) > 0 else ""

    return RecordingData(
        timestamps=timestamps,
        hr_values=df["hr"].to_list(),
        speed_values=df["speed"].to_list(),
        cadence_values=df["cadence"].to_list(),
        altitude_values=df["altitude"].to_list(),
        lat_values=df["lat"].to_list(),
        lon_values=df["lon"].to_list(),
        power_values=df["power"].to_list(),
        has_speed=has_speed,
        has_cadence=has_cadence,
        has_altitude=has_altitude,
        has_gps=has_gps,
        has_power=has_power,
        source_format=source_format,
    )
