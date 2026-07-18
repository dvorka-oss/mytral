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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Shared bulldozer-parallelized GPS map precomputation for recording imports.

The activity feed renders a mini-map for every activity by calling
``ActivityBlobService.ensure_gpx_map_data`` synchronously. Generating a polyline
parses a whole GPX/TCX track and can take seconds per large recording, so any
import that stores recordings must precompute the map data up front - otherwise
the first feed load computes hundreds of maps at once and appears to hang.

Both the Strava archive import and the Polar Flow export import use
:func:`precompute_maps` for this (DRY).
"""

import json
import os
import pathlib
import traceback

from mytral.backends import entities
from mytral.blobstore.filesystem import FilesystemBlobStore
from mytral.recordings import gpx_extractor
from mytral.recordings import tcx_extractor
from mytral.tasks import bulldozer
from mytral.tasks.bulldozer._sandbox_utils import _split_evenly


def _map_job(job_key: int, job_dir: pathlib.Path) -> None:
    """Bulldozer job: precompute map data for a chunk of recording blobs.

    Reads ``job_dir/input/payload.json``, writes results to
    ``job_dir/output/payload.json``, and ``output/error.json`` on failure.
    """
    try:
        _map_job_impl(job_dir)
    except Exception:
        error_file = job_dir / "output" / "error.json"
        error_file.parent.mkdir(parents=True, exist_ok=True)
        with open(error_file, "w") as fh:
            json.dump(
                {
                    "job_key": job_key,
                    "job_dir": str(job_dir),
                    "traceback": traceback.format_exc(),
                },
                fh,
            )


def _map_job_impl(job_dir: pathlib.Path) -> None:
    """Compute polylines/elevation for each recording blob in the job payload."""
    input_file = job_dir / "input" / "payload.json"
    if not input_file.exists():
        return
    with open(input_file) as fh:
        payload = json.load(fh)
    entries = payload.get("entries", [])
    if not entries:
        return
    user_id = payload.get("user_id", "")
    main_store = FilesystemBlobStore(
        base_dir=pathlib.Path(payload.get("user_data_dir", "")),
        blobs_subdir="blobs",
    )

    results: dict[str, dict] = {}
    for entry in entries:
        blob_uuid = entry["blob_uuid"]
        extension = entry.get("extension", ".gpx")
        try:
            meta = main_store.get_blob_metadata(user_id, blob_uuid)
        except Exception:
            results[blob_uuid] = {"skipped": True, "error": "metadata not found"}
            continue
        if meta.summary_polyline and meta.summary_bbox:
            results[blob_uuid] = {"skipped": True, "reason": "already computed"}
            continue
        try:
            stream = main_store.open_blob(user_id, blob_uuid)
            try:
                recording_data = stream.read()
            finally:
                stream.close()
        except Exception:
            results[blob_uuid] = {"skipped": True, "error": "cannot read recording"}
            continue
        try:
            if extension == ".tcx":
                track_count, track_point_count, gps_points, raw_profile = (
                    tcx_extractor.extract_all_from_tcx(recording_data)
                )
            else:
                track_count, track_point_count, gps_points, raw_profile = (
                    gpx_extractor.extract_all_from_gpx(recording_data)
                )
            elevation_profile = gpx_extractor.simplify_elevation_profile(raw_profile)
        except Exception:
            results[blob_uuid] = {"skipped": True, "error": "parse/extract failed"}
            continue
        if gps_points:
            summary_polyline, summary_bbox, full_polyline = (
                gpx_extractor.encode_gps_polylines(points=gps_points)
            )
        else:
            summary_polyline, summary_bbox, full_polyline = "", None, ""
        results[blob_uuid] = {
            "skipped": False,
            "summary_polyline": summary_polyline,
            "summary_bbox": list(summary_bbox) if summary_bbox else None,
            "full_polyline": full_polyline,
            "elevation_profile": elevation_profile,
            "track_count": track_count,
            "track_point_count": track_point_count,
        }

    output_file = job_dir / "output" / "payload.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as fh:
        json.dump({"results": results}, fh)


def _recording_blob_entries(activities: list) -> list[dict]:
    """Collect ``{activity_key, blob_uuid, extension}`` for every recording blob."""
    entries: list[dict] = []
    for activity in activities:
        for entry in activity.recorded_blob_keys or []:
            blob_uuid = entities.recording_blob_uuid(entry)
            extension = "." + entry.rsplit(".", 1)[-1] if "." in entry else ".gpx"
            entries.append(
                {
                    "activity_key": activity.key,
                    "blob_uuid": blob_uuid,
                    "extension": extension,
                }
            )
    return entries


def precompute_maps(
    *,
    user_id: str,
    activities: list,
    blob_svc,
    usr_task_dir: pathlib.Path,
    config,
    logger,
    log,
    check_cancellation,
) -> int:
    """Precompute GPS map data for every recording blob, parallelized via bulldozer.

    Parameters
    ----------
    activities :
        Activities whose ``recorded_blob_keys`` should get map data.
    blob_svc :
        ``ActivityBlobService`` used to persist the computed metadata.
    usr_task_dir :
        The task's directory (bulldozer sandbox root).
    config :
        ``MytralConfig`` (provides the main blob store directory for workers).
    log, check_cancellation :
        Task callbacks for progress logging and cooperative cancellation.

    Returns
    -------
    int
        Number of recording blobs whose map data was computed.
    """
    entries = _recording_blob_entries(activities)
    if not entries:
        return 0

    workers = max(1, (os.cpu_count() or 1) // 2)
    chunks = _split_evenly(entries, min(workers, len(entries)))
    bzz = bulldozer.SubtaskBulldozer(
        usr_task_dir=usr_task_dir, subtask_key="recording-map", logger=logger
    )
    job_dirs = bzz.make_sandbox()[: len(chunks)]

    user_data_dir = str(config.user_data_dir)
    for i, chunk in enumerate(chunks):
        with open(job_dirs[i] / "input" / "payload.json", "w") as fh:
            json.dump(
                {"user_id": user_id, "user_data_dir": user_data_dir, "entries": chunk},
                fh,
            )

    log(
        f"Precomputing GPS maps for {len(entries)} recording(s) across "
        f"{len(job_dirs)} parallel workers (this is the longest step)..."
    )
    bzz.run(job_dirs=job_dirs, job_function=_map_job)

    for job_dir in job_dirs:
        error_file = job_dir / "output" / "error.json"
        if error_file.exists():
            with open(error_file) as fh:
                err = json.load(fh)
            log(f"WARNING: map job {err['job_key']} failed:\n{err['traceback']}")

    log("Collecting precomputed map data...")
    computed = 0
    for job_dir in job_dirs:
        check_cancellation()
        output_file = job_dir / "output" / "payload.json"
        if not output_file.exists():
            continue
        with open(output_file) as fh:
            chunk_result = json.load(fh)
        for blob_uuid, result in chunk_result.get("results", {}).items():
            if result.get("skipped"):
                continue
            try:
                cur_meta = blob_svc._store.get_blob_metadata(user_id, blob_uuid)
                bbox = result.get("summary_bbox")
                bbox = tuple(bbox) if bbox and len(bbox) == 4 else None
                blob_svc._store.update_blob_metadata(
                    user_id=user_id,
                    blob_key=blob_uuid,
                    name=cur_meta.name,
                    description=cur_meta.description,
                    keywords=cur_meta.keywords,
                    track_count=result.get("track_count"),
                    track_point_count=result.get("track_point_count"),
                    summary_polyline=result.get("summary_polyline"),
                    summary_bbox=bbox,
                    full_polyline=result.get("full_polyline"),
                    elevation_profile=result.get("elevation_profile"),
                )
                computed += 1
            except Exception as exc:
                log(f"  WARNING: map metadata update failed for {blob_uuid}: {exc}")

    log(f"Map data precomputed for {computed} recording(s)")
    return computed
