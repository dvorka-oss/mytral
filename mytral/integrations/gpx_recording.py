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
"""GPX recording import plugin."""

import io
import typing

from mytral import app_logger as logger
from mytral import app_user_ds
from mytral import plugins
from mytral.backends import dataset
from mytral.backends import entities
from mytral.blobstore.activity_service import ActivityBlobService
from mytral.config import MytralConfig
from mytral.recordings import gpx_extractor
from mytral.recordings import parquet_converter
from mytral.recordings.models import RecordingSummary

GPX_IMPORT_SRC = "gpx-import"
GPX_TASK_TYPE = "gpx_import"


class GpxImportPlugin(plugins.ActivitiesImportPlugin):
    """Import a GPX recording file and attach it to an existing activity.

    The plugin uploads the GPX blob, converts it to Parquet, and optionally
    extracts summary fields into the activity entity.
    """

    name = "GPX Recording Import"
    src = GPX_IMPORT_SRC

    def __init__(self, config: MytralConfig) -> None:
        self._config = config

    def import_recording(
        self,
        user_id: str,
        activity_key: str,
        gpx_data: bytes,
        original_filename: str,
        blob_svc: ActivityBlobService,
        *,
        extract_summary: bool = False,
    ) -> str:
        """Upload a GPX file, convert to Parquet, and optionally update summary.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        activity_key : str
            Target activity key.
        gpx_data : bytes
            Raw GPX file bytes.
        original_filename : str
            Original filename for metadata.
        blob_svc : ActivityBlobService
            Blob service instance to use.
        extract_summary : bool
            When True, extract fields and update the activity entity.

        Returns
        -------
        str
            Blob UUID of the newly stored GPX recording.
        """

        def _persist_summary(summary: gpx_extractor.RecordingSummary) -> None:
            ds: dataset.UserDataset = app_user_ds.get_user_ds(user_id)
            activity: entities.ActivityEntity = ds.activities.by_key[activity_key]
            apply_gpx_summary(activity, summary)
            ds.save_activity(activity)

        return import_gpx_recording_bytes(
            user_id=user_id,
            activity_key=activity_key,
            gpx_data=gpx_data,
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


def import_gpx_recording_bytes(
    user_id: str,
    activity_key: str,
    gpx_data: bytes,
    original_filename: str,
    blob_svc: ActivityBlobService,
    *,
    extract_summary: bool = False,
    summary_handler: typing.Callable[[RecordingSummary], None] | None = None,
    polyline_method: str = gpx_extractor.GPX_POLYLINE_METHOD,
    log=logger,
) -> str:
    """Store a GPX recording and optionally enrich the owning activity.

    Parameters
    ----------
    user_id : str
        Owning user identifier.
    activity_key : str
        Target activity key.
    gpx_data : bytes
        Raw GPX payload.
    original_filename : str
        Original filename for metadata and validation.
    blob_svc : ActivityBlobService
        Blob service instance used for persistence.
    extract_summary : bool
        When True, extract a summary and pass it to *summary_handler*.
    summary_handler : Callable[[RecordingSummary], None] | None
        Callback used to persist GPX summary fields.
    log :
        Logger used for warnings.

    Returns
    -------
    str
        Blob UUID of the stored GPX recording.
    """
    meta = blob_svc.upload_recording(
        user_id=user_id,
        activity_key=activity_key,
        uploaded_file=io.BytesIO(gpx_data),
        original_filename=original_filename,
        content_type="application/gpx+xml",
    )
    blob_key = meta.blob_key

    try:
        parquet_bytes = parquet_converter.gpx_to_parquet(gpx_data)
        blob_svc.save_parquet(
            user_id=user_id,
            activity_key=activity_key,
            source_blob_key=blob_key,
            parquet_data=parquet_bytes,
        )
    except Exception as exc:
        log.warning(f"GPX→Parquet conversion failed for {blob_key}: {exc}")

    if extract_summary:
        try:
            summary = gpx_extractor.extract_gpx_summary(gpx_data)
            if summary is not None and summary_handler is not None:
                summary_handler(summary)
        except Exception as exc:
            log.warning(f"GPX summary extraction failed for {blob_key}: {exc}")

    try:
        blob_svc.ensure_gpx_map_data(
            user_id=user_id,
            activity_key=activity_key,
            blob_key=blob_key,
            polyline_method=polyline_method,
        )
    except Exception as exc:
        log.warning(f"GPX map generation failed for {blob_key}: {exc}")

    return blob_key


def apply_gpx_summary(
    activity: entities.ActivityEntity,
    summary: RecordingSummary,
) -> None:
    """Write non-None fields from *summary* into *activity* (in-place).

    Parameters
    ----------
    activity : entities.ActivityEntity
        Activity to update.
    summary : RecordingSummary
        Extracted summary values.
    """
    if not isinstance(summary, RecordingSummary):
        return
    if summary.activity_type_key and not activity.activity_type_key:
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
    if summary.avg_hr and activity.avg_hr == 0:
        activity.avg_hr = summary.avg_hr
    if summary.max_hr and activity.max_hr == 0:
        activity.max_hr = summary.max_hr
    if summary.elevation_gain and activity.elevation_gain == 0:
        activity.elevation_gain = summary.elevation_gain
    if summary.name_hint and not activity.name:
        activity.name = summary.name_hint


def get_plugin(
    user_id: str,
    config: MytralConfig,
    *,
    params: typing.Any = None,
) -> GpxImportPlugin:
    """Construct a GpxImportPlugin.

    Parameters
    ----------
    user_id : str
        User identifier (unused, retained for plugin interface compatibility).
    config : MytralConfig
        Application configuration.
    params : typing.Any
        Optional extra parameters (unused).

    Returns
    -------
    GpxImportPlugin
    """
    return GpxImportPlugin(config)
