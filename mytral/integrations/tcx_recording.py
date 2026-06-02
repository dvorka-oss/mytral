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
"""TCX recording import plugin."""

import io
import typing

from mytral import app_logger as logger
from mytral import app_user_ds
from mytral import commons
from mytral import plugins
from mytral.backends import dataset
from mytral.backends import entities
from mytral.blobstore.activity_service import ActivityBlobService
from mytral.config import MytralConfig
from mytral.recordings import gpx_extractor
from mytral.recordings import parquet_converter
from mytral.recordings import tcx_extractor
from mytral.recordings.models import RecordingSummary

TCX_IMPORT_SRC = "tcx-import"
TCX_TASK_TYPE = "tcx_import"


class TcxImportPlugin(plugins.ActivitiesImportPlugin):
    """Import a TCX recording file and attach it to an existing activity."""

    name = "TCX Recording Import"
    src = TCX_IMPORT_SRC

    def __init__(self, config: MytralConfig) -> None:
        self._config = config

    def import_recording(
        self,
        user_id: str,
        activity_key: str,
        tcx_data: bytes,
        original_filename: str,
        blob_svc: ActivityBlobService,
        *,
        extract_summary: bool = False,
    ) -> str:
        """Upload a TCX file, convert to Parquet, and optionally update summary."""

        def _persist_summary(summary: RecordingSummary) -> None:
            ds: dataset.UserDataset = app_user_ds.get_user_ds(user_id)
            activity: entities.ActivityEntity = ds.activities.by_key[activity_key]
            apply_tcx_summary(activity, summary)
            ds.save_activity(activity)

        return import_tcx_recording_bytes(
            user_id=user_id,
            activity_key=activity_key,
            tcx_data=tcx_data,
            original_filename=original_filename,
            blob_svc=blob_svc,
            extract_summary=extract_summary,
            summary_handler=_persist_summary if extract_summary else None,
            polyline_method=getattr(
                self._config,
                "gpx_polyline_method",
                gpx_extractor.GPX_POLYLINE_METHOD,
            ),
            log=logger,
        )


def import_tcx_recording_bytes(
    user_id: str,
    activity_key: str,
    tcx_data: bytes,
    original_filename: str,
    blob_svc: ActivityBlobService,
    *,
    extract_summary: bool = False,
    summary_handler: typing.Callable[[RecordingSummary], None] | None = None,
    polyline_method: str = gpx_extractor.GPX_POLYLINE_METHOD,
    log=logger,
) -> str:
    """Store a TCX recording and optionally enrich the owning activity."""
    meta = blob_svc.upload_recording(
        user_id=user_id,
        activity_key=activity_key,
        uploaded_file=io.BytesIO(tcx_data),
        original_filename=original_filename,
        content_type="application/xml",
    )
    blob_key = meta.blob_key

    try:
        parquet_bytes = parquet_converter.tcx_to_parquet(tcx_data)
        blob_svc.save_parquet(
            user_id=user_id,
            activity_key=activity_key,
            source_blob_key=blob_key,
            parquet_data=parquet_bytes,
        )
    except Exception as exc:
        log.warning(f"TCX→Parquet conversion failed for {blob_key}: {exc}")

    if extract_summary:
        try:
            summary = tcx_extractor.extract_tcx_summary(tcx_data)
            if summary is not None and summary_handler is not None:
                summary_handler(summary)
        except Exception as exc:
            log.warning(f"TCX summary extraction failed for {blob_key}: {exc}")

    try:
        blob_svc.ensure_gpx_map_data(
            user_id=user_id,
            activity_key=activity_key,
            blob_key=blob_key,
            polyline_method=polyline_method,
        )
    except Exception as exc:
        log.warning(f"TCX map generation failed for {blob_key}: {exc}")

    return blob_key


def apply_tcx_summary(
    activity: entities.ActivityEntity,
    summary: RecordingSummary,
) -> None:
    """Write non-None fields from *summary* into *activity* (in-place)."""
    if not isinstance(summary, RecordingSummary):
        return
    if summary.activity_type_key and (
        not activity.activity_type_key
        or activity.activity_type_key == commons.AT_WORKOUT
    ):
        activity.activity_type_key = summary.activity_type_key
    if summary.when:
        activity.when_year = summary.when.year
        activity.when_month = summary.when.month
        activity.when_day = summary.when.day
        activity.when_hour = summary.when.hour
        activity.when_minute = summary.when.minute
        activity.when_second = summary.when.second
    if summary.hours is not None and activity.hours == 0:
        activity.hours = summary.hours
    if summary.minutes is not None and activity.minutes == 0:
        activity.minutes = summary.minutes
    if summary.seconds is not None and activity.seconds == 0:
        activity.seconds = summary.seconds
    if summary.distance and activity.distance == 0:
        activity.distance = summary.distance
    if summary.kcal and activity.kcal == 0:
        activity.kcal = summary.kcal
    if summary.avg_hr and activity.avg_hr == 0:
        activity.avg_hr = summary.avg_hr
    if summary.max_hr and activity.max_hr == 0:
        activity.max_hr = summary.max_hr
    if summary.avg_cadence and activity.avg_cadence == 0:
        activity.avg_cadence = summary.avg_cadence
    if summary.max_cadence and activity.max_cadence == 0:
        activity.max_cadence = summary.max_cadence
    if summary.avg_speed and activity.avg_speed == 0.0:
        activity.avg_speed = summary.avg_speed
    if summary.max_speed and activity.max_speed == 0.0:
        activity.max_speed = summary.max_speed
    if summary.elevation_gain and activity.elevation_gain == 0:
        activity.elevation_gain = summary.elevation_gain
    if summary.name_hint and not activity.name:
        activity.name = summary.name_hint


def get_plugin(
    user_id: str,
    config: MytralConfig,
    *,
    params: typing.Any = None,
) -> TcxImportPlugin:
    """Construct a TcxImportPlugin."""
    return TcxImportPlugin(config)
