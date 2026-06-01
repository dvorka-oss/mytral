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
"""FIT recording import plugin."""

import io
import typing

from mytral import app_logger as logger
from mytral import app_user_ds
from mytral import plugins
from mytral.backends import dataset
from mytral.backends import entities
from mytral.blobstore.activity_service import ActivityBlobService
from mytral.config import MytralConfig
from mytral.recordings import fit_extractor
from mytral.recordings import parquet_converter
from mytral.recordings.models import RecordingSummary

FIT_IMPORT_SRC = "fit-import"
FIT_TASK_TYPE = "fit_import"


class FitImportPlugin(plugins.ActivitiesImportPlugin):
    """Import a FIT recording file and attach it to an existing activity.

    The plugin uploads the FIT blob, converts it to Parquet, and optionally
    extracts summary fields into the activity entity.
    """

    name = "FIT Recording Import"
    src = FIT_IMPORT_SRC

    def __init__(self, config: MytralConfig) -> None:
        self._config = config

    def import_recording(
        self,
        user_id: str,
        activity_key: str,
        fit_data: bytes,
        original_filename: str,
        blob_svc: ActivityBlobService,
        *,
        extract_summary: bool = False,
    ) -> str:
        """Upload a FIT file, convert to Parquet, and optionally update summary.

        Parameters
        ----------
        user_id : str
            Owning user identifier.
        activity_key : str
            Target activity key.
        fit_data : bytes
            Raw FIT file bytes.
        original_filename : str
            Original filename for metadata.
        blob_svc : ActivityBlobService
            Blob service instance to use.
        extract_summary : bool
            When True, extract session fields and update the activity entity.

        Returns
        -------
        str
            Blob UUID of the newly stored FIT recording.
        """
        meta = blob_svc.upload_recording(
            user_id=user_id,
            activity_key=activity_key,
            uploaded_file=io.BytesIO(fit_data),
            original_filename=original_filename,
            content_type="application/octet-stream",
        )
        blob_key = meta.blob_key

        try:
            parquet_bytes = parquet_converter.fit_to_parquet(fit_data)
            blob_svc.save_parquet(
                user_id=user_id,
                activity_key=activity_key,
                source_blob_key=blob_key,
                parquet_data=parquet_bytes,
            )
        except Exception as exc:
            logger.warning("FIT→Parquet conversion failed for %s: %s", blob_key, exc)

        if extract_summary:
            try:
                summary = fit_extractor.extract_fit_summary(fit_data)
                ds: dataset.UserDataset = app_user_ds.get_user_ds(user_id)
                activity: entities.ActivityEntity = ds.activities.by_key[activity_key]
                _apply_summary(activity, summary)
                ds.save_activity(activity)
            except Exception as exc:
                logger.warning(
                    "FIT summary extraction failed for %s: %s", blob_key, exc
                )

        return blob_key


def _apply_summary(
    activity: entities.ActivityEntity,
    summary: "fit_extractor.RecordingSummary",
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
    if summary.when and not activity.when:
        activity.when = summary.when.strftime("%Y-%m-%d %H:%M")
    if summary.hours is not None and activity.h == 0:
        activity.h = summary.hours
    if summary.minutes is not None and activity.m == 0:
        activity.m = summary.minutes
    if summary.seconds is not None and activity.s == 0:
        activity.s = summary.seconds
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
    if summary.avg_speed and activity.avg_speed == 0.0:
        activity.avg_speed = summary.avg_speed


def get_plugin(
    user_id: str,
    config: MytralConfig,
    *,
    params: typing.Any = None,
) -> FitImportPlugin:
    """Construct a FitImportPlugin.

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
    FitImportPlugin
    """
    return FitImportPlugin(config)
