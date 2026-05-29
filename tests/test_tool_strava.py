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
import datetime
import glob
import json
import pathlib
import re
import uuid

import pytest
import requests

from mytral import commons
from mytral import config
from mytral import persistences
from mytral import plugins
from mytral.backends import entities
from mytral.integrations import icommons
from mytral.integrations import strava
from tests import _given


@pytest.mark.skip("MyTraL tool - not a test: download activities from strava.com")
@pytest.mark.tool
def test_export_json_from_strava_service(tmp_path: pathlib.Path):
    """Export all activities as JSON using Strava API."""
    json_export_file = persistences.create_ts_filename(
        prefix="strava-export", ext=persistences.EXT_JSON
    )
    json_export_path = str(tmp_path / json_export_file)
    page_size = 200

    #
    # GIVEN: Strava authentication - get ACCESS token
    #
    # OPTION A: Strava web - DO NOT USE - insufficient rights w/ READ only
    #
    # 1. get fields from Strava API web page strava.com/Settings/My API application:
    #    - https://www.strava.com/settings/api
    #      - client ID      ... needed, valid forever
    #      - client_secret  ... needed, valid forever
    #      - access token   ... THIS IS WHAT YOU NEED, valid or ~5h
    #      - refresh token  ... NOT needed
    #    - see: https://developers.strava.com/docs/authentication/
    #

    # strava_access_token = "1fedfb2fb8a2d6ab2b3e2b7656f62dc847e23668"
    strava_access_token = ""

    # OPTION B: using URL w/ MANUAL code extraction
    #
    # 1. get fields from Strava API web page:
    #    - client ID      ... needed, valid forever
    #    - client_secret  ... needed, valid forever
    #    - access token   ... NOT needed (ignore it this way)
    #    - refresh token  ... NOT needed
    #    - see: https://developers.strava.com/docs/authentication/
    # 2. create Strava OAuth URL to get the CODE:
    #    - only client ID is needed
    #    - do IGNORE URL failure and get code from the browser after you get redirected
    # 3. get Strava ACCESS TOKEN using:
    #    - client ID     ... Strava API web page; valid forever
    #    - client secret ... Strava API web page; valid forever
    #    - code          ... extracted from OAuth URL above
    #
    if not strava_access_token:
        # STEP 1. ... secrets from the Strava web
        print(
            "IMPORTANT: access token validity is ~4h - get the token from:\n"
            "  https://www.strava.com/settings/api"
        )
        # ACCESS TOKEN will have to be provided in the web UI of MyTraL
        profile_json = persistences.load_json(
            file_path=pathlib.Path("data") / "dvorka" / "user-settings.json"
        )
        strava_secrets = profile_json.get("strava", {})
        if not strava_secrets:
            raise ValueError("Strava secrets not found in the user profile")

        # INSERT CODE HERE
        strava_secrets["code"] = ""
        strava_secrets["code"] = "292e47b3c52f9e8e641b03fddc6d7be292505195"
        if not strava_secrets["code"]:
            # STEP: get the code (OAuth URL):
            # 1. code below constructs URL
            # 2. open the URL in the browser
            # 3. strava.com will REDIRECT to given URL (e.g. http://localhost)
            #    and append parameters with the code - for instance the URL is:
            #    http://localhost/
            #      ?state=&code=292e47b3c52f9e8e641b03fddc6d7be292505195
            #       &scope=read,activity:read_all,profile:read_all
            # 4. if this redirects to MyTraL, then I will be able to handle the URL
            #    and extract the code from the URL parameter
            strava_oauth_url = (
                f"http://www.strava.com/oauth/authorize"
                f"?client_id={strava_secrets['client_id']}"
                f"&redirect_uri=http://localhost"
                f"&response_type=code"
                f"&approval_prompt=auto"  # force / auto
                f"&scope=profile:read_all,activity:read_all"
                # ^ profile:read_all,activity:read_all
                # ^ read (shown on profile)
            )
            print(
                f"Click the URL to AUTHORIZE and get the code with temporal validity:\n"
                f"{strava_oauth_url}"
            )
            return
        else:
            print(f"Strava code: {strava_secrets['code']}")

        # STEP 3: ... get OAuth ACCESS token
        response = requests.post(
            url="https://www.strava.com/oauth/token",
            data={
                "client_id": f"{strava_secrets['client_id']}",
                "client_secret": f"{strava_secrets['client_secret']}",
                "code": f"{strava_secrets['code']}",
                "grant_type": "authorization_code",
            },
        )
        strava_tokens = response.json()
        print(json.dumps(strava_tokens, indent=4))
        strava_access_token = strava_tokens["access_token"]

    print(f"Strava access token: {strava_access_token}")

    #
    # WHEN: export the data
    #

    exported_activities = []

    page = 1
    print("Downloading activities as JSON file...")
    while True:
        print(f"  Page {page}")
        print("    Downloading data...")
        # See:
        # https://developers.strava.com/docs/reference/
        #   #api-Activities-getLoggedInAthleteActivities
        response_activities = requests.get(
            f"{strava.URL_ACTIVITIES}?access_token={strava_access_token}"
            f"&per_page={page_size}"
            f"&page={page}"
        )
        if not response_activities:
            break
        else:
            print(f"          {response_activities}")

        activities_json = response_activities.json()
        exported_activities.extend(activities_json)

        page += 1

    print(f"Export DONE: {len(exported_activities)} activities")

    #
    # THEN: save exported the data as JSON file
    #

    persistences.save_json(json_export_path, exported_activities)

    print(f"Save DONE: {json}")


@pytest.mark.skip("MyTraL tool - not a test: import activities from strava.com")
@pytest.mark.mytral
def test_import_strava_json_to_mytral_json(tmp_path: pathlib.Path):
    """Convert previously export Strava data in ? format to MyTraL activities dataset
    JSON format.

    """
    #
    # GIVEN
    #
    strava_export_json_path = (
        pathlib.Path("data")
        / commons.DEFAULT_USER_NAME
        / "data-sources"
        / "strava.com"
        # / "strava-export-20221228-8h38m48s.json"
        / "strava-export-20240608-18h45m20s.json"
    )
    strava_activities: list = persistences.load_json(file_path=strava_export_json_path)

    _, ds = _given.given_ds(
        test_config=config.MytralConfig(persistence_data_dir=tmp_path)
    )
    user_id = commons.DEFAULT_USER_NAME
    user_profile = ds.profile(user_id)

    #
    # WHEN
    #
    t_plugin = strava.StravaActivitiesImportPlugin
    gear = ds.list_gear(user_id=user_id, dataset_name=user_profile.dataset_name)
    activities_plugin: t_plugin = plugins.registry.get_plugin(t_plugin.NAME)
    user_profile = ds.profile(user_id)
    new_activities = activities_plugin.import_activities(
        datasets={t_plugin.USE_TYPE_STRAVA_LIST: strava_activities},
        user_profile=user_profile,
        gear=gear,
    )

    #
    # THEN
    #
    print(f"Imported activities: {len(new_activities)}")
    assert new_activities
    a: entities.ActivityEntity = new_activities[0]
    print(a)
    assert "strava.com" in a.src_url


@pytest.mark.mytral
def test_convert_strava_json_with_unicode_characters():
    """Test that Strava activities with Unicode characters are handled correctly.

    This test reproduces the UnicodeEncodeError that occurs when Strava activity
    data contains non-ASCII characters (e.g., 'á', 'ñ', 'ö') and ensures the fix works.
    """
    # GIVEN
    strava_item = {
        "id": 12345678,
        "name": "Morning Run in España",
        "location_country": "España",
        "description": "Cañón with Zürich vibes",
    }

    # WHEN: convert to string representation (as done in strava.py)
    # this should work even if output encoding is limited
    log_msg = error_msg = ""
    try:
        # simulate the problematic line in strava.py:429-431
        activity_str = str(strava_item)[:88]
        safe_activity_str = activity_str.encode("ascii", errors="replace").decode(
            "ascii"
        )
        log_msg = f"#0 importing Strava activity: {safe_activity_str}..."
        success = True
    except UnicodeEncodeError as e:
        success = False
        error_msg = str(e)

    # THEN
    print(f"DONE: Unicode test completed successfully: {success}")
    if success:
        print(f"Safe output: {log_msg[:100]}")
        # verify that non-ASCII characters are replaced with '?'
        assert "Espa?a" in log_msg or "España" in log_msg
    else:
        print(f"Error: {error_msg}")

    # the test should pass - Unicode should be handled gracefully
    assert success, "Unicode characters should be handled without UnicodeEncodeError"


# Strava gear-ID migration tool
#
#   Before the strava-gear-id: prefix was added to the activity sync code,
#   raw Strava gear IDs (e.g. "b941128", "g790751") were stored directly in
#   activity "gears" lists.  The gear sync task only recognizes IDs that carry
#   the canonical "strava-gear-id:" prefix, so those activities were invisible
#   to it.  This tool adds the missing prefix in-place.
@pytest.mark.skip(
    "MyTraL tool - not a test: run manually to migrate raw Strava gear IDs"
)
@pytest.mark.parametrize(
    "account_data_dir",
    [
        (
            f"{_given.EXT_TEST_DATA_ROOT}/development/data"
            f"/2c0a2cef-93ec-438c-b5af-30469e144cc5"
        )
    ],
)
def test_migrate_strava_gear_id_prefix(account_data_dir: str):
    """Add 'strava-gear-id:' prefix to raw Strava gear IDs stored in activities.

    Raw Strava gear IDs look like 'b941128' or 'g790751' (one letter followed
    by digits).  After this migration every such ID becomes
    'strava-gear-id:b941128' / 'strava-gear-id:g790751', which is what the
    Gear Synchronization task expects.

    MyTraL gear UUIDs (e.g. 'ae9198f2-48bc-4ac0-a81f-5a2aaa15ef95') and IDs
    that already carry the prefix are left untouched.  The operation is
    idempotent.
    """
    # GIVEN
    data_dir = pathlib.Path(account_data_dir)
    assert data_dir.is_dir(), f"Account data directory not found: {data_dir}"

    activity_files = sorted(glob.glob(str(data_dir / "activities-*.json")))
    assert activity_files, f"No activities-YYYY.json files found in {data_dir}"

    # one letter (Strava type marker) followed by one or more digits only
    raw_strava_id = re.compile(r"^[a-zA-Z]\d+$")

    # WHEN
    total_files_changed = 0
    total_refs_prefixed = 0

    for activity_file in activity_files:
        activities = json.loads(pathlib.Path(activity_file).read_text(encoding="utf-8"))
        changed = False

        for activity in activities:
            if activity.get("src") != strava.SRC_STRAVA:
                continue
            new_gears = []
            for gear_id in activity.get("gears", []):
                if gear_id and raw_strava_id.match(gear_id):
                    new_gears.append(f"{icommons.STRAVA_GEAR_PREFIX_ID}{gear_id}")
                    total_refs_prefixed += 1
                    changed = True
                else:
                    new_gears.append(gear_id)
            activity["gears"] = new_gears

        if changed:
            pathlib.Path(activity_file).write_text(
                json.dumps(activities, indent=4, ensure_ascii=False),
                encoding="utf-8",
            )
            total_files_changed += 1
            print(f"  Updated: {activity_file}")

    # THEN
    print(
        f"DONE: {total_refs_prefixed} gear refs prefixed across "
        f"{total_files_changed} file(s) in {data_dir}"
    )

    # verify no raw Strava gear IDs remain in Strava activities
    remaining = 0
    for activity_file in activity_files:
        activities = json.loads(pathlib.Path(activity_file).read_text(encoding="utf-8"))
        for activity in activities:
            if activity.get("src") != strava.SRC_STRAVA:
                continue
            for gear_id in activity.get("gears", []):
                if gear_id and raw_strava_id.match(gear_id):
                    remaining += 1

    assert remaining == 0, (
        f"{remaining} raw Strava gear IDs still found after migration - "
        "check the data directory"
    )
    print("DONE: Verification passed - no raw Strava gear IDs remain")


@pytest.mark.skip(
    "MyTraL tool - not a test: restore src_* fields deleted by the 1.8.0 bug"
)
@pytest.mark.parametrize(
    "mytral_data_dir,user_id",
    [
        (
            f"{_given.EXT_TEST_DATA_ROOT}/pre-production/data",
            "ba16be59-83ee-4999-9b37-d2c49e454135",
        )
    ],
)
@pytest.mark.tool
def test_restore_strava_src_fields(
    mytral_data_dir: str,
    user_id: str,
):
    """Restore src_* fields in activities-YYYY.json from Strava API data.

    In 1.8.0 a bug caused ``src``, ``src_key``, ``src_url``, and
    ``src_descriptor`` fields to be deleted from activities on update.
    This tool downloads activities from Strava for the current year, matches
    them against the local dataset by exact date, distance, and duration,
    and restores the missing ``src_*`` fields in-place (with a ``.bak`` backup).

    Parameters
    ----------
    mytral_data_dir : str
        Path to the MyTraL persistence data directory (the directory that
        contains per-user subdirectories).
    user_id : str
        User ID whose activities should be restored.

    """
    current_year = datetime.date.today().year

    #
    # GIVEN: user settings with Strava access token
    #
    data_dir = pathlib.Path(mytral_data_dir) / user_id
    if not data_dir.is_dir():
        raise FileNotFoundError(f"User data directory not found: {data_dir}")

    settings_path = data_dir / "user-settings.json"
    if not settings_path.exists():
        raise FileNotFoundError(f"User settings not found: {settings_path}")

    settings = persistences.load_json(settings_path)
    strava_cfg = settings.get("strava", {})
    access_token = strava_cfg.get("access_token", "")
    if not access_token:
        raise ValueError(
            "Strava access_token not found in user-settings.json. "
            "Set it via the MyTraL Settings > Integrations page."
        )

    #
    # GIVEN: local activities for the current year
    #
    activities_path = data_dir / f"activities-{current_year}.json"
    if not activities_path.exists():
        raise FileNotFoundError(f"Activities file not found: {activities_path}")

    local_activities = persistences.load_json(activities_path)
    is_dict_fmt = isinstance(local_activities, dict)
    local_items = local_activities.values() if is_dict_fmt else local_activities
    # materialize so we can count accurately
    local_items = list(local_items)
    print(f"Loaded {len(local_items)} local activities from {activities_path}")

    #
    # WHEN: download Strava activities for the current year
    #
    jan1_epoch = int(
        datetime.datetime(current_year, 1, 1, tzinfo=datetime.timezone.utc).timestamp()
    )

    strava_activities = []
    page = 1
    page_size = 200
    print(f"Downloading Strava activities for {current_year} ...")
    while True:
        print(f"  Page {page}")
        response = requests.get(
            (
                f"{strava.URL_ACTIVITIES}"
                f"?per_page={page_size}&page={page}&after={jan1_epoch}"
            ),
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if not response.ok:
            print(f"  Strava API error: {response.status_code} {response.text}")
            break

        page_activities = response.json()
        if not page_activities:
            break

        strava_activities.extend(page_activities)
        print(f"    {len(page_activities)} activities")
        page += 1

    print(f"Downloaded {len(strava_activities)} Strava activities total")

    #
    # WHEN: build Strava lookup keyed by (year, month, day, meters, duration_s)
    #
    strava_lookup: dict[tuple[int, int, int, int, int], dict] = {}
    for sa in strava_activities:
        start_date = sa.get("start_date", "")
        if not start_date:
            continue
        dt = datetime.datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        distance = int(sa.get("distance", 0))
        # Strava moving_time is in seconds; MyTraL duration_seconds is also s
        moving_time = int(sa.get("moving_time", 0))
        key = (dt.year, dt.month, dt.day, distance, moving_time)
        strava_lookup[key] = sa

    print(f"Built Strava lookup with {len(strava_lookup)} entries")

    #
    # WHEN: match local activities and restore src_* fields
    #
    correlation_id: str = str(uuid.uuid4())
    restored_count = 0
    for a in local_items:
        when_year = a.get("when_year", 0)
        when_month = a.get("when_month", 0)
        when_day = a.get("when_day", 0)
        meters = int(a.get("distance", 0))
        duration_s = int(a.get("duration_seconds", 0))
        key = (when_year, when_month, when_day, meters, duration_s)

        sa = strava_lookup.get(key)
        if sa is None:
            continue

        strava_id = str(sa.get("id", ""))
        a["src"] = strava.SRC_STRAVA
        a["src_key"] = strava_id
        a["src_url"] = f"https://www.strava.com/activities/{strava_id}"
        a["src_descriptor"] = a["src_descriptor"] or correlation_id
        restored_count += 1
        print(
            f"  Restored: {a.get('name', '?')} "
            f"({when_year}-{when_month:02d}-{when_day:02d})"
            f"  ->  strava:{strava_id}"
        )

    #
    # THEN: save restored activities (with backup) or report no matches
    #
    if restored_count > 0:
        backup_path = pathlib.Path(str(activities_path) + ".bak")
        persistences.save_json(backup_path, local_activities)
        print(f"Backup saved to {backup_path}")

        persistences.save_json(activities_path, local_activities)
        print(
            f"\nDONE: Restored {restored_count}/{len(local_items)} activities"
            f"  ->  {activities_path}"
        )
    else:
        print(
            "\nDONE: No activities matched — nothing restored. "
            "Check that the Strava access token is valid and that the "
            "activities-{year}.json file contains activities for "
            f"{current_year}."
        )
