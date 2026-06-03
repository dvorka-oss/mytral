# MyTraL: my trailing log
#
# Copyright (C) 2022-2026 Martin Dvorak <martin.dvorak@mindforger.com>
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

"""Shared utilities for Strava integration tasks."""

import io
import typing
import uuid

from mytral import security
from mytral.blobstore import activity_service as blob_svc_module
from mytral.integrations import gpx_recording
from mytral.integrations import strava


def _to_bool(value) -> bool:
    """Convert form/task parameter value to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(value)


def build_strava_credentials(
    params: dict,
    enc_key: str,
    *,
    with_refresh: bool = True,
) -> typing.Any:
    """Build a lightweight credentials object from encrypted task parameters.

    Parameters
    ----------
    params : dict
        Task parameters dict with encrypted Strava credentials.
    enc_key : str
        Encryption key for decrypting token fields.
    with_refresh : bool
        If True, also decrypt refresh_token and auth_until fields.

    Returns
    -------
    object
        Credentials object with strava_access_token, strava_client_id, etc.
    """
    # use a simple namespace object (no need for a formal class)
    creds = type("_StravaCredentials", (), {})()
    creds.strava_access_token = security.decrypt(params["access_token"], enc_key)
    creds.strava_client_id = params["client_id"]
    creds.strava_client_secret = security.decrypt(params["client_secret"], enc_key)
    creds.strava_url = params.get("strava_url", "https://www.strava.com/api/v3")
    if with_refresh:
        creds.strava_refresh_token = security.decrypt(
            params.get("refresh_token", ""), enc_key
        )
        creds.strava_auth_until = int(params.get("auth_until", 0))
    return creds


def enrich_strava_activities(
    activities: list,
    creds: typing.Any,
    user_id: str,
    dataset_name: str,
    *,
    import_recordings: bool = True,
    import_photos: bool = True,
    total: int = 0,
    dataset,
    blobstore,
    config,
    log_fn: typing.Callable[[str], None],
    logger,
    check_cancellation: typing.Callable[[], None],
    update_progress: typing.Callable[[int], None],
) -> None:
    """Fetch and import activity details, recordings, and photos from Strava.

    Parameters
    ----------
    activities : list
        List of ActivityEntity instances already persisted.
    creds :
        Credentials object with ``strava_access_token``.
    user_id : str
        User identifier.
    dataset_name : str
        Target dataset name.
    import_recordings : bool
        Whether to download and import GPX/TCX recordings.
    import_photos : bool
        Whether to download and import photos.
    total : int
        Total number of activities (for progress tracking).
    dataset :
        Dataset backend for updating activities.
    blobstore :
        Blob store backend for persisting recordings and photos.
    config :
        MyTraL config instance.
    log_fn : Callable[[str], None]
        Function to log progress messages.
    logger :
        Logger instance for warnings.
    check_cancellation : Callable[[], None]
        Function to check for task cancellation.
    update_progress : Callable[[int], None]
        Function to update task progress percentage.
    """
    access_token = creds.strava_access_token
    blob_svc = blob_svc_module.ActivityBlobService(
        store=blobstore,
        dataset=dataset,
        config=config,
    )

    desc_updated = 0
    calories_updated = 0
    recordings_imported = 0
    recordings_failed = 0
    photos_uploaded = 0
    photos_failed = 0

    for i, activity in enumerate(activities):
        check_cancellation()
        src_key = activity.src_key
        if not src_key:
            continue

        # fetch activity detail for description, calories
        detail = strava.fetch_activity_detail(
            activity_id=src_key,
            access_token=access_token,
            logger=logger,
        )
        needs_update = False

        if detail:
            desc = detail.get("description", "")
            if desc and not activity.description:
                activity.description = str(desc)
                desc_updated += 1
                needs_update = True

            detail_cal = detail.get("calories", 0)
            if detail_cal and activity.kcal == 0:
                activity.kcal = int(detail_cal)
                calories_updated += 1
                needs_update = True

        if needs_update:
            dataset.update_activity(
                user_id=user_id,
                dataset_name=dataset_name,
                entity=activity,
            )

        # import recording from streams
        if import_recordings:
            try:
                streams = strava.fetch_activity_streams(
                    activity_id=src_key,
                    access_token=access_token,
                    logger=logger,
                )
                if streams and streams.get("latlng", {}).get("data"):
                    gpx_bytes = strava.streams_to_gpx(
                        streams,
                        activity_name=activity.name,
                    )
                    gpx_recording.import_gpx_recording_bytes(
                        user_id=user_id,
                        activity_key=activity.key,
                        gpx_data=gpx_bytes,
                        original_filename=f"strava-{src_key}.gpx",
                        blob_svc=blob_svc,
                        extract_summary=False,
                        log=logger,
                    )
                    recordings_imported += 1
                else:
                    log_fn(
                        f"No GPS streams available for activity "
                        f"'{activity.name}' ({src_key})"
                    )
            except Exception as exc:
                log_fn(
                    f"Recording import failed for '{activity.name}' ({src_key}): {exc}"
                )
                recordings_failed += 1

        # import photos
        if import_photos:
            try:
                photo_meta_list = strava.fetch_activity_photos(
                    activity_id=src_key,
                    access_token=access_token,
                    logger=logger,
                )
                if photo_meta_list:
                    uploaded_files = []
                    for photo_meta in photo_meta_list:
                        urls = photo_meta.get("urls", {})
                        photo_url = urls.get("2048") or urls.get("1024")
                        if not photo_url:
                            continue
                        photo_data = strava.download_photo(
                            photo_url=photo_url,
                            logger=logger,
                        )
                        if photo_data:
                            photo_name = (
                                f"strava-{src_key}-"
                                f"{photo_meta.get('unique_id', uuid.uuid4())}"
                                f".jpg"
                            )
                            uploaded_files.append((io.BytesIO(photo_data), photo_name))

                    if uploaded_files:
                        try:
                            blob_svc.upload_photos(
                                user_id=user_id,
                                activity_key=activity.key,
                                uploaded_files=uploaded_files,
                                name="",
                                description="",
                                keywords="strava,api,import",
                            )
                            photos_uploaded += len(uploaded_files)
                        except Exception as exc:
                            log_fn(
                                f"Photo upload failed for "
                                f"'{activity.name}' ({src_key}): {exc}"
                            )
                            photos_failed += len(uploaded_files)
            except Exception as exc:
                log_fn(f"Photo fetch failed for '{activity.name}' ({src_key}): {exc}")
                photos_failed += 1

        # progress
        progress = 30 + int(65 * (i + 1) / total)
        update_progress(progress)

    log_fn(
        f"Media enrichment complete: "
        f"{desc_updated} descriptions updated, "
        f"{calories_updated} calories updated, "
        f"{recordings_imported} recordings imported, "
        f"{recordings_failed} recordings failed, "
        f"{photos_uploaded} photos uploaded, "
        f"{photos_failed} photos failed"
    )
