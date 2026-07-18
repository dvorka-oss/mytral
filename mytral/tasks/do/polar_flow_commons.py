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

"""Shared utilities for Polar Flow integration tasks."""

import datetime
import typing

from mytral import plugins
from mytral import security
from mytral.blobstore import activity_service as blob_svc_module
from mytral.integrations import gpx_recording
from mytral.integrations import polar_flow
from mytral.integrations import tcx_recording

# cross-channel dedup tolerances (GDPR-export session vs AccessLink API exercise)
START_TOLERANCE_S = 120
DURATION_TOLERANCE_S = 60


def to_bool(value) -> bool:
    """Convert a form/task parameter value to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(value)


def build_polar_credentials(params: dict, enc_key: str) -> typing.Any:
    """Build a lightweight credentials object from encrypted task parameters.

    Polar access tokens do not expire and there is no refresh token, so only the
    access token and Polar user id are needed (no client id/secret).

    Parameters
    ----------
    params : dict
        Task parameters with the encrypted Polar Flow access token.
    enc_key : str
        Encryption key for decrypting the access token.

    Returns
    -------
    object
        Namespace with ``access_token`` and ``polar_user_id``.
    """
    creds = type("_PolarFlowCredentials", (), {})()
    creds.access_token = security.decrypt(params["access_token"], enc_key)
    creds.polar_user_id = params.get("polar_user_id", "")
    return creds


def _activity_start_seconds(entity) -> int | None:
    """Return the activity start time as epoch-like seconds, or None if incomplete."""
    if not (entity.when_year and entity.when_month and entity.when_day):
        return None
    try:
        return int(
            datetime.datetime(
                entity.when_year,
                entity.when_month,
                entity.when_day,
                entity.when_hour,
                entity.when_minute,
                entity.when_second,
            ).timestamp()
        )
    except (ValueError, OverflowError):
        return None


def find_existing_polar_flow_activity(
    dataset,
    user_id: str,
    dataset_name: str,
    candidate,
    *,
    start_tolerance_s: int = START_TOLERANCE_S,
    duration_tolerance_s: int = DURATION_TOLERANCE_S,
):
    """Find an existing Polar Flow activity matching *candidate* by natural key.

    Because Polar exercise ids are not guaranteed to match between the GDPR export
    and the AccessLink API, an exact ``src_key`` match is tried first and then a
    natural-key match: same ``src == polar-flow``, same activity type, start time
    within *start_tolerance_s*, and duration within *duration_tolerance_s*.

    Parameters
    ----------
    dataset :
        Dataset backend exposing ``all_activities(user_id, dataset_name)``.
    user_id : str
        User identifier.
    dataset_name : str
        Dataset to search.
    candidate :
        The imported ``ActivityEntity`` to look for.

    Returns
    -------
    str | None
        The matching existing activity key, or ``None`` when there is no duplicate.
    """
    existing = dataset.all_activities(user_id, dataset_name)
    if not existing:
        return None

    candidate_start = _activity_start_seconds(candidate)
    for key, act in existing.items():
        if act.src != polar_flow.SRC_POLAR_FLOW:
            continue
        # 1) exact source-key match
        if candidate.src_key and act.src_key == candidate.src_key:
            return key
        # 2) natural-key match
        if (
            candidate_start is None
            or act.activity_type_key != candidate.activity_type_key
        ):
            continue
        act_start = _activity_start_seconds(act)
        if act_start is None:
            continue
        if abs(act_start - candidate_start) > start_tolerance_s:
            continue
        if (
            abs(act.duration_seconds - candidate.duration_seconds)
            > duration_tolerance_s
        ):
            continue
        return key
    return None


def import_exercise_recording(
    access_token: str,
    exercise_url: str,
    activity,
    user_id: str,
    blob_svc,
    logger,
) -> bool:
    """Fetch and store the GPX (fallback TCX) recording for one exercise.

    AccessLink recording endpoints are transaction-scoped, so this must be called
    while the exercise's transaction is still open (i.e. from the sync loop).

    Returns
    -------
    bool
        ``True`` if a recording was stored, else ``False``.
    """
    src_key = activity.src_key or "polar"
    gpx_bytes = polar_flow.fetch_exercise_gpx(
        access_token=access_token, exercise_url=exercise_url, logger=logger
    )
    if gpx_bytes:
        gpx_recording.import_gpx_recording_bytes(
            user_id=user_id,
            activity_key=activity.key,
            gpx_data=gpx_bytes,
            original_filename=f"polar-{src_key}.gpx",
            blob_svc=blob_svc,
            extract_summary=False,
            log=logger,
        )
        return True

    tcx_bytes = polar_flow.fetch_exercise_tcx(
        access_token=access_token, exercise_url=exercise_url, logger=logger
    )
    if tcx_bytes:
        tcx_recording.import_tcx_recording_bytes(
            user_id=user_id,
            activity_key=activity.key,
            tcx_data=tcx_bytes,
            original_filename=f"polar-{src_key}.tcx",
            blob_svc=blob_svc,
            extract_summary=False,
            log=logger,
        )
        return True

    return False


def pull_new_exercises(
    creds: typing.Any,
    *,
    dataset,
    blobstore,
    config,
    user_id: str,
    dataset_name: str,
    import_recordings: bool,
    log_fn: typing.Callable[[str], None],
    logger,
    check_cancellation: typing.Callable[[], None],
    update_progress: typing.Callable[[int], None],
) -> tuple[int, int, int]:
    """Pull new exercises via the AccessLink transaction model.

    Runs the full create -> list -> fetch -> dedup -> create -> commit cycle. Shared by
    the incremental sync and the full re-sync tasks (DRY).

    Returns
    -------
    tuple[int, int, int]
        ``(imported, skipped, recordings)`` counts.
    """
    check_cancellation()
    update_progress(5)

    transaction_id = polar_flow.create_transaction(
        access_token=creds.access_token,
        polar_user_id=creds.polar_user_id,
        logger=logger,
    )
    if not transaction_id:
        log_fn(
            "No new activities to import. Polar's AccessLink API only delivers "
            "activities uploaded to Flow AFTER you connected this client, and only "
            "from the last 30 days. To import older history, use the Polar export "
            "(GDPR ZIP) import on the Tools > Import > Polar page."
        )
        update_progress(100)
        return 0, 0, 0

    exercise_urls = polar_flow.list_transaction_exercises(
        access_token=creds.access_token,
        polar_user_id=creds.polar_user_id,
        transaction_id=transaction_id,
        logger=logger,
    )
    total = len(exercise_urls)
    log_fn(f"Transaction {transaction_id}: {total} new exercise(s)")
    check_cancellation()

    activity_plugin = plugins.registry.get_plugin(
        polar_flow.PolarFlowActivityImportPlugin.NAME
    )
    user_profile = dataset.profile(user_id)
    valid_activity_type_ids = list(
        dataset.list_activity_types(user_id=user_id).activity_types_by_key.keys()
    )
    blob_svc = blob_svc_module.ActivityBlobService(
        store=blobstore, dataset=dataset, config=config
    )

    imported = 0
    skipped = 0
    recordings = 0
    fetch_failures = 0
    for i, exercise_url in enumerate(exercise_urls):
        check_cancellation()
        summary = polar_flow.fetch_exercise_summary(
            access_token=creds.access_token, exercise_url=exercise_url, logger=logger
        )
        if not summary:
            # a failed fetch must NOT be committed away - leave the transaction open
            fetch_failures += 1
            continue

        activity = activity_plugin.import_activity(
            dataset_item=summary,
            user_profile=user_profile,
            valid_activity_type_ids=valid_activity_type_ids,
            correlation_id=transaction_id,
        )

        # cross-channel dedup: skip if the same session already exists
        if find_existing_polar_flow_activity(
            dataset=dataset,
            user_id=user_id,
            dataset_name=dataset_name,
            candidate=activity,
        ):
            skipped += 1
            continue

        dataset.create_activity(
            user_id=user_id, dataset_name=dataset_name, entity=activity
        )
        imported += 1

        if import_recordings:
            try:
                if import_exercise_recording(
                    access_token=creds.access_token,
                    exercise_url=exercise_url,
                    activity=activity,
                    user_id=user_id,
                    blob_svc=blob_svc,
                    logger=logger,
                ):
                    recordings += 1
            except Exception as exc:
                log_fn(f"Recording import failed for {activity.src_key}: {exc}")

        if total:
            update_progress(5 + int(90 * (i + 1) / total))

    # commit ONLY when every summary was fetched. If any fetch failed, leave the
    # transaction open so Polar re-serves its exercises next run; the src_key dedup
    # then skips the already-imported ones and retries the failed ones (no data loss,
    # no duplicates). A committed transaction is never re-served by Polar.
    if fetch_failures:
        log_fn(
            f"{fetch_failures} exercise summary fetch(es) failed - NOT committing the "
            "transaction; it will be retried on the next sync"
        )
    else:
        polar_flow.commit_transaction(
            access_token=creds.access_token,
            polar_user_id=creds.polar_user_id,
            transaction_id=transaction_id,
            logger=logger,
        )

    log_fn(
        f"Polar Flow pull complete: {imported} imported, {skipped} skipped "
        f"(duplicates), {recordings} recordings"
    )
    update_progress(100)
    return imported, skipped, recordings
