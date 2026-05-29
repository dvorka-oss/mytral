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

"""Strava gear sync task - smart merges Strava gear into MyTraL gear registry.

The module-level :func:`run_gear_sync_and_relink` function contains the full
sync logic and can be called directly from activity sync tasks so that no
separate manual gear sync step is required after an activity import.
"""

import uuid

from mytral import commons
from mytral import security
from mytral import settings
from mytral import tasks
from mytral.integrations import icommons
from mytral.integrations import strava


def _normalize(s: str) -> str:
    """Normalize string for fuzzy matching.

    Parameters
    ----------
    s : str
        Input string.

    Returns
    -------
    str
        Lowercase stripped string.
    """
    return (s or "").strip().lower()


def _score_match(strava_item: dict, gear: settings.Gear) -> int:
    """Score how well a Strava gear item matches a MyTraL Gear entry.

    Parameters
    ----------
    strava_item : dict
        Strava gear JSON dict.
    gear : Gear
        MyTraL gear entry.

    Returns
    -------
    int
        Match score (higher = better match; 0 = no match).
    """
    score = 0
    s_brand = _normalize(strava_item.get("brand_name", ""))
    s_model = _normalize(strava_item.get("model_name", ""))
    s_nick = _normalize(strava_item.get("nickname", ""))

    g_vendor = _normalize(gear.vendor if hasattr(gear, "vendor") else "")
    g_model = _normalize(gear.model if hasattr(gear, "model") else "")
    g_name = _normalize(gear.name)

    if s_brand and g_vendor and s_brand == g_vendor:
        score += 3
    if s_model and g_model and s_model == g_model:
        score += 2
    if s_model and s_model in g_name:
        score += 1
    if s_nick and s_nick in g_name:
        score += 1

    return score


class StravaGearSyncTask(tasks.TaskBase):
    """Smart-merges Strava gear into the MyTraL gear registry.

    Match priority:

    1. Exact external ID match -> update distance/retired/description
    2. Fuzzy match by brand+model+name (score >= 3) -> update + set external ID
    3. No match -> create new gear entry with external ID set

    Gear is never deleted. Retired gear is marked as retired.
    """

    TASK_TYPE = "strava_sync_gear"
    TASK_DISPLAY_NAME = "Strava — Gear Sync"
    ENCRYPTED_PARAM_KEYS = ["access_token", "client_secret"]

    def __init__(
        self,
        task_entity: tasks.TaskEntity,
        logger,
        log_callback,
        config=None,
        dataset=None,
        blobstore=None,
        enc_key="",
    ):
        super().__init__(
            task_entity=task_entity,
            logger=logger,
            log_callback=log_callback,
            config=config,
            dataset=dataset,
            blobstore=blobstore,
            enc_key=enc_key,
        )

    def execute(self) -> None:
        """Execute smart gear sync from Strava."""
        params = self.task_entity.parameters
        user_id = params["user_id"]
        dataset_name = params.get("dataset_name", "")

        self.check_cancellation()

        class _StravaCredentials:
            pass

        creds = _StravaCredentials()
        creds.strava_access_token = security.decrypt(
            params["access_token"], self._enc_key
        )
        creds.strava_client_id = params["client_id"]
        creds.strava_client_secret = security.decrypt(
            params["client_secret"], self._enc_key
        )
        creds.strava_url = params.get("strava_url", "https://www.strava.com/api/v3")

        self.check_cancellation()

        run_gear_sync_and_relink(
            creds=creds,
            dataset=self._dataset,
            user_id=user_id,
            dataset_name=dataset_name,
            log_fn=self.log,
            logger=self.logger,
        )

        # evict gear cache
        try:
            self._dataset.cache_evict(user_id)
        except Exception as exc:
            self.log(f"Cache eviction warning (non-fatal): {exc}")

        self.update_progress(100)

    def _relink_activities(
        self,
        user_id: str,
        dataset_name: str,
        strava_id_to_gear: dict[str, settings.Gear],
    ) -> int:
        return _relink_activities(
            dataset=self._dataset,
            user_id=user_id,
            dataset_name=dataset_name,
            strava_id_to_gear=strava_id_to_gear,
            log_fn=self.log,
        )

    @staticmethod
    def _update_gear_from_strava(gear: settings.Gear, strava_item: dict) -> None:
        _update_gear_from_strava(gear, strava_item)

    @staticmethod
    def _create_gear_from_strava(strava_item: dict, strava_id: str) -> settings.Gear:
        return _create_gear_from_strava(strava_item, strava_id)


#
# Module-level helpers — shared between StravaGearSyncTask and run_gear_sync_and_relink
#


def _update_gear_from_strava(gear: settings.Gear, strava_item: dict) -> None:
    """Update mutable fields on a Gear entry from a Strava API response.

    Parameters
    ----------
    gear : settings.Gear
        MyTraL gear entry to update in place.
    strava_item : dict
        Strava gear JSON dict.
    """
    gear.comment = strava_item.get("description") or gear.comment
    gear.retired = bool(strava_item.get("retired", False))


def _create_gear_from_strava(strava_item: dict, strava_id: str) -> settings.Gear:
    """Create a new Gear entity from a Strava API response.

    Parameters
    ----------
    strava_item : dict
        Strava gear JSON dict.
    strava_id : str
        Strava gear ID (raw form, without ``strava-gear-id:`` prefix).

    Returns
    -------
    settings.Gear
        New MyTraL Gear entity.
    """
    return settings.Gear(
        key=str(uuid.uuid4()),
        activity_type_key="",
        name=strava_item.get("name", "Unknown"),
        vendor=strava_item.get("brand_name", ""),
        model=strava_item.get("model_name", ""),
        comment=strava_item.get("description", ""),
        retired=bool(strava_item.get("retired", False)),
        external_id_map={"strava": strava_id},
    )


def _relink_activities(
    dataset,
    user_id: str,
    dataset_name: str,
    strava_id_to_gear: dict[str, settings.Gear],
    log_fn,
) -> int:
    """Replace ``strava-gear-id:X`` placeholders in activities with MyTraL UUIDs.

    Scans every Strava activity, replaces any remaining gear reference that
    now has a matching MyTraL gear entry with the gear's real UUID, and saves
    only the year files that actually changed.

    Parameters
    ----------
    dataset
        User dataset instance.
    user_id : str
        User ID.
    dataset_name : str
        Dataset name used to load all activities (usually DS_LIFELONG).
    strava_id_to_gear : dict[str, settings.Gear]
        Map of Strava ID to Gear, as built during sync.
        Retains *all* keys seen during the run, including overwritten ones.
    log_fn : callable
        Logging callback ``log_fn(message: str)``.

    Returns
    -------
    int
        Number of activities whose gear list was updated.
    """
    # build a fast lookup: both prefixed and unprefixed forms -> MyTraL UUID
    strava_id_to_uuid: dict[str, str] = {}
    for sk, gear in strava_id_to_gear.items():
        strava_id_to_uuid[sk] = gear.key
        if sk.startswith(icommons.STRAVA_GEAR_PREFIX_ID):
            raw = sk[len(icommons.STRAVA_GEAR_PREFIX_ID) :]
            strava_id_to_uuid[raw] = gear.key

    try:
        all_acts = dataset.all_activities(user_id, dataset_name)
    except Exception as exc:
        log_fn(f"Warning: could not load activities for re-link: {exc}")
        return 0

    # group modified activities by year for one save-per-year-file
    modified_by_year: dict[int, list] = {}
    total_relinked = 0

    for act in all_acts.values():
        if act.src != strava.SRC_STRAVA or not act.gears:
            continue
        new_gears = []
        changed = False
        for gear_id in act.gears:
            act_uuid = strava_id_to_uuid.get(gear_id)
            if act_uuid:
                new_gears.append(act_uuid)
                changed = True
            else:
                new_gears.append(gear_id)
        if changed:
            act.gears = new_gears
            modified_by_year.setdefault(act.when_year, []).append(act)
            total_relinked += 1

    for year, changed_acts in modified_by_year.items():
        year_ds_name = f"activities-{year}"
        changed_keys = {a.key for a in changed_acts}
        year_acts = [a for a in all_acts.values() if a.when_year == year]
        # merge: replace the stale version with the updated one
        year_acts = [
            next((c for c in changed_acts if c.key == a.key), a) for a in year_acts
        ]
        try:
            dataset.update_activities(
                user_id=user_id,
                dataset_name=year_ds_name,
                activities=year_acts,
            )
            log_fn(f"Relinked {len(changed_keys)} activities in {year_ds_name}")
        except Exception as exc:
            log_fn(f"Warning: could not save relinked activities for {year}: {exc}")

    return total_relinked


def run_gear_sync_and_relink(
    creds,
    dataset,
    user_id: str,
    dataset_name: str,
    log_fn,
    logger,
) -> None:
    """Sync Strava gear and relink activity gear references to MyTraL UUIDs.

    Intended to be called at the end of activity sync tasks so that no
    separate manual gear sync step is needed.  The function:

    1. Scans existing gear entries and activities for known Strava gear IDs.
    2. Fetches each gear from the Strava API.
    3. Creates new or updates existing MyTraL gear entries (fuzzy-match merge).
    4. Replaces ``strava-gear-id:X`` placeholders in all Strava activities
       with the resolved MyTraL gear UUIDs.

    Parameters
    ----------
    creds
        Object with Strava credentials: ``strava_access_token``,
        ``strava_client_id``, ``strava_client_secret``, ``strava_url``.
    dataset
        User dataset instance for gear and activity operations.
    user_id : str
        User ID.
    dataset_name : str
        Dataset name for gear operations (e.g. ``DS_LIFELONG``).
    log_fn : callable
        Logging callback ``log_fn(message: str)``.
    logger
        Logger instance forwarded to Strava API helpers.
    """
    log_fn("Gear sync started")

    strava_user_gear = settings.StravaUserGear(
        user_profile=creds,
        logger=logger,
    )

    # load current MyTraL gear registry
    user_gear = dataset.list_gear(user_id=user_id, dataset_name=dataset_name)
    mytral_gears = list(user_gear.gear_by_key.values())

    known_strava_ids = user_gear.external_ids("strava")
    log_fn(f"Known Strava external gear IDs in MyTraL: {len(known_strava_ids)}")

    # also collect strava-gear-id:X placeholders from activities
    activity_strava_gear_ids: set[str] = set()
    try:
        activities = dataset.all_activities(user_id, commons.DS_LIFELONG)
        for act in activities.values():
            if act.src == strava.SRC_STRAVA and act.gears:
                for gear_id in act.gears:
                    if gear_id and gear_id.startswith(icommons.STRAVA_GEAR_PREFIX_ID):
                        activity_strava_gear_ids.add(gear_id)
    except Exception as exc:
        log_fn(f"Warning: could not scan activities for gear IDs: {exc}")

    all_strava_ids = list(set(known_strava_ids) | activity_strava_gear_ids)
    log_fn(f"Total unique Strava gear IDs to sync: {len(all_strava_ids)}")

    if not all_strava_ids:
        log_fn("No Strava gear IDs found - skipping gear sync")
        return

    # fetch each gear from Strava API
    strava_gear_data: list[dict] = []
    for gear_id in all_strava_ids:
        try:
            raw_id = gear_id
            if raw_id.startswith(icommons.STRAVA_GEAR_PREFIX_ID):
                raw_id = raw_id[len(icommons.STRAVA_GEAR_PREFIX_ID) :]
            gear_dict = strava._sync_gear(
                strava_user_gear=strava_user_gear,
                gear_id=raw_id,
            )
            if gear_dict:
                strava_gear_data.append(gear_dict)
        except Exception as exc:
            log_fn(f"Warning: could not fetch gear {gear_id}: {exc}")

    log_fn(f"Fetched {len(strava_gear_data)} gear items from Strava")

    # build lookup by external ID for quick exact-match
    strava_id_to_gear = user_gear.to_dict_by_external_id("strava")

    updated = 0
    created = 0
    ambiguous = 0

    for strava_item in strava_gear_data:
        strava_id = str(strava_item.get("id", "")).strip()
        if not strava_id:
            continue

        # phase 1: exact external ID match
        matched_gear = strava_id_to_gear.get(strava_id)
        if matched_gear:
            _update_gear_from_strava(matched_gear, strava_item)
            dataset.update_gear(
                user_id=user_id,
                gear=matched_gear,
                dataset_name=dataset_name,
            )
            updated += 1
            log_fn(f"Updated gear '{matched_gear.name}' (strava_id={strava_id})")
            continue

        # phase 2: fuzzy match by brand+model+name
        scores = [(g, _score_match(strava_item, g)) for g in mytral_gears]
        candidates = [(g, s) for g, s in scores if s >= 3]

        if len(candidates) == 1:
            matched_gear = candidates[0][0]
            matched_gear.set_external_id("strava", strava_id)
            _update_gear_from_strava(matched_gear, strava_item)
            dataset.update_gear(
                user_id=user_id,
                gear=matched_gear,
                dataset_name=dataset_name,
            )
            strava_id_to_gear[strava_id] = matched_gear
            strava_id_to_gear[f"{icommons.STRAVA_GEAR_PREFIX_ID}{strava_id}"] = (
                matched_gear
            )
            updated += 1
            log_fn(
                f"Fuzzy-matched and updated gear '{matched_gear.name}' "
                f"(score={candidates[0][1]}, strava_id={strava_id})"
            )
        elif len(candidates) > 1:
            names = [g.name for g, _ in candidates]
            log_fn(
                f"Ambiguous match for Strava gear '{strava_item.get('name')}' "
                f"(id={strava_id}) - {len(candidates)} candidates: {names}. "
                "Manual resolution required - skipping."
            )
            ambiguous += 1
        else:
            # phase 3: create new gear
            new_gear = _create_gear_from_strava(strava_item, strava_id)
            dataset.create_gear(
                user_id=user_id,
                gear=new_gear,
                dataset_name=dataset_name,
            )
            mytral_gears.append(new_gear)
            strava_id_to_gear[strava_id] = new_gear
            strava_id_to_gear[f"{icommons.STRAVA_GEAR_PREFIX_ID}{strava_id}"] = new_gear
            created += 1
            log_fn(f"Created new gear '{new_gear.name}' (strava_id={strava_id})")

    log_fn(
        f"Gear sync complete: {updated} updated, {created} created, "
        f"{ambiguous} ambiguous"
    )

    # relink activities: replace strava-gear-id:X refs with MyTraL UUIDs
    relinked = _relink_activities(
        dataset=dataset,
        user_id=user_id,
        dataset_name=dataset_name,
        strava_id_to_gear=strava_id_to_gear,
        log_fn=log_fn,
    )
    log_fn(f"Activity re-link complete: {relinked} activities updated")


tasks.tasks_registry.register_task(StravaGearSyncTask)
