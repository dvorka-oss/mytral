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
"""FIT file activity-level summary extractor."""

import datetime

from fit_tool.fit_file import FitFile
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.session_message import SessionMessage

from mytral import commons
from mytral.integrations import icommons
from mytral.recordings.models import RecordingSummary

# FIT protocol sentinel values: the maximum unsigned integer for a given
# width signals "invalid / not set".  The fit_tool library returns these raw
# values; the application must filter them out.
#
# Ref: FIT SDK Profile.xlsx / FIT Protocol Specification
_FIT_UINT8_INVALID = 0xFF  # 255
_FIT_UINT16_INVALID = 0xFFFF  # 65,535
_FIT_UINT32_INVALID = 0xFFFFFFFF  # 4,294,967,295


def _fit_sport_id(raw_sport: object) -> int | None:
    """Resolve FIT sport enum/int value to integer ID when possible."""
    if isinstance(raw_sport, int):
        return raw_sport

    enum_value = getattr(raw_sport, "value", None)
    if isinstance(enum_value, int):
        return enum_value
    if isinstance(enum_value, str) and enum_value.isdigit():
        return int(enum_value)

    raw_sport_str = str(raw_sport).strip().lower()
    if raw_sport_str.startswith("sport."):
        raw_sport_str = raw_sport_str.split(".", 1)[1]
    if raw_sport_str.isdigit():
        return int(raw_sport_str)

    return None


def _fit_sport_name(raw_sport: object) -> str:
    """Resolve FIT sport enum/int value to canonical FIT sport name."""
    sport_id = _fit_sport_id(raw_sport)
    if sport_id is not None:
        return icommons.FIT_INT_SPORT_TO_STR.get(sport_id, "")

    sport_name = str(raw_sport).strip().lower()
    if sport_name.startswith("sport."):
        sport_name = sport_name.split(".", 1)[1]

    return sport_name


def _fit_sport_to_activity_type_key(raw_sport: object) -> str:
    """Map FIT sport enum/int value to MyTraL activity type key."""
    sport_name = _fit_sport_name(raw_sport)
    if not sport_name:
        return ""

    return icommons.FIT_INT_SPORT_TO_MYTRAL_AT.get(sport_name, commons.AT_WORKOUT)


def _integrate_distance_from_records(fit: FitFile) -> int | None:
    """Estimate total distance in metres by integrating speed over time.

    Parameters
    ----------
    fit : FitFile
        Parsed FIT file.

    Returns
    -------
    int | None
        Total distance in metres, or None when no usable speed/timestamp
        records are found.
    """
    total_m = 0.0
    prev_ts = None
    found = False
    for record in fit.records:
        msg = record.message
        if not isinstance(msg, RecordMessage):
            continue
        ts = msg.timestamp
        spd = msg.speed
        if ts is None or spd is None:
            prev_ts = ts if ts is not None else prev_ts
            continue
        if prev_ts is not None:
            dt = (ts - prev_ts) / 1000.0  # ms → seconds
            if dt > 0:
                total_m += float(spd) * dt
                found = True
        prev_ts = ts
    return int(round(total_m)) if found else None


def extract_fit_summary(fit_data: bytes) -> RecordingSummary:
    """Parse a FIT file session message and return activity-level summary fields.

    Parameters
    ----------
    fit_data : bytes
        Raw FIT file content.

    Returns
    -------
    RecordingSummary
        Summary with whatever fields the FIT session message provides.
        All fields remain None when parsing fails or the session message
        is absent.
    """
    summary = RecordingSummary()

    try:
        fit = FitFile.from_bytes(fit_data, check_crc=False)
    except Exception:
        return summary

    for record in fit.records:
        message = record.message
        if not isinstance(message, SessionMessage):
            continue

        # activity type
        activity_type_raw = message.sport
        if activity_type_raw is not None:
            summary.activity_type_key = _fit_sport_to_activity_type_key(
                activity_type_raw
            )

        # start time (FIT timestamp, uint32 — sentinel 0xFFFFFFFF)
        start_ts = message.start_time
        if start_ts is not None and start_ts != _FIT_UINT32_INVALID:
            try:
                summary.when = datetime.datetime.fromtimestamp(
                    start_ts / 1000.0, tz=datetime.timezone.utc
                )
            except (ValueError, OSError):
                pass

        # duration (uint32 — sentinel 0xFFFFFFFF)
        elapsed = message.total_elapsed_time
        if elapsed is not None and elapsed != _FIT_UINT32_INVALID:
            total_s = int(elapsed)
            summary.hours = total_s // 3600
            summary.minutes = (total_s % 3600) // 60
            summary.seconds = total_s % 60

        # distance in metres (uint32 — sentinel 0xFFFFFFFF)
        dist = message.total_distance
        if dist is not None and dist != _FIT_UINT32_INVALID:
            summary.distance = int(dist)

        # kcal (uint16 — sentinel 0xFFFF / 65535)
        kcal = message.total_calories
        if kcal is not None and kcal != _FIT_UINT16_INVALID:
            summary.kcal = int(kcal)

        # HR (uint8 — sentinel 0xFF / 255)
        avg_hr = message.avg_heart_rate
        if avg_hr is not None and avg_hr != _FIT_UINT8_INVALID and avg_hr > 0:
            summary.avg_hr = int(avg_hr)
        max_hr = message.max_heart_rate
        if max_hr is not None and max_hr != _FIT_UINT8_INVALID and max_hr > 0:
            summary.max_hr = int(max_hr)

        # cadence (uint8 — sentinel 0xFF / 255)
        avg_cad = message.avg_cadence
        if avg_cad is not None and avg_cad != _FIT_UINT8_INVALID and avg_cad > 0:
            summary.avg_cadence = int(avg_cad)
        max_cad = message.max_cadence
        if max_cad is not None and max_cad != _FIT_UINT8_INVALID and max_cad > 0:
            summary.max_cadence = int(max_cad)

        # speed in m/s (uint16 — sentinel 0xFFFF / 65535), convert to km/h
        avg_spd = message.avg_speed
        if avg_spd is not None and avg_spd != _FIT_UINT16_INVALID and avg_spd > 0:
            summary.avg_speed = round(float(avg_spd) * 3.6, 2)
        max_spd = message.max_speed
        if max_spd is not None and max_spd != _FIT_UINT16_INVALID and max_spd > 0:
            summary.max_speed = round(float(max_spd) * 3.6, 2)

        # power in watts (uint16 — sentinel 0xFFFF / 65535)
        avg_pwr = message.avg_power
        if avg_pwr is not None and avg_pwr != _FIT_UINT16_INVALID and avg_pwr > 0:
            summary.avg_watts = float(avg_pwr)
        max_pwr = message.max_power
        if max_pwr is not None and max_pwr != _FIT_UINT16_INVALID and max_pwr > 0:
            summary.max_watts = float(max_pwr)

        # elevation gain in metres (uint16 — sentinel 0xFFFF / 65535)
        ascent = message.total_ascent
        if ascent is not None and ascent != _FIT_UINT16_INVALID:
            summary.elevation_gain = int(ascent)

        # take the first session only
        break

    # fallback: derive distance by integrating speed over record messages
    if summary.distance is None:
        summary.distance = _integrate_distance_from_records(fit)

    # fallback: derive avg_speed from distance and elapsed time
    if summary.avg_speed is None and summary.distance and summary.distance > 0:
        duration_s = (
            (summary.hours or 0) * 3600
            + (summary.minutes or 0) * 60
            + (summary.seconds or 0)
        )
        if duration_s > 0:
            summary.avg_speed = round((summary.distance / duration_s) * 3.6, 2)

    return summary
