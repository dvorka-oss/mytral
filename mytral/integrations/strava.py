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

"""Strava API import plugin."""

import enum
import json
import pathlib
import uuid
from datetime import datetime

import requests

from mytral import app_logger
from mytral import app_user_ds
from mytral import commons
from mytral import loggers
from mytral import persistences
from mytral import plugins
from mytral import settings
from mytral.backends import dataset
from mytral.backends import entities
from mytral.integrations import icommons

# URLs
URL_OAUTH_AUTH = "https://www.strava.com/oauth/authorize"
URL_OAUTH_TOKEN = "https://www.strava.com/oauth/token"
URL_AUTH_CALLBACK = "strava/auth-callback"
URL_ACTIVITIES = "https://www.strava.com/api/v3/activities"
URL_GEARS = "https://www.strava.com/api/v3/gear"
# entity sources
SRC_STRAVA = "strava"
SRC_STRAVA_BASE_URL = "https://www.strava.com/activities/"

#
# PLUGIN: Strava JSON data import from raw to MyTraL format
#


class StravaActivityImportPlugin(plugins.ActivityImportPlugin):
    NAME = "Strava API activity import"
    DESCRIPTION = (
        "Imports activity from the proprietary strava.com JSON format. "
        "See: https://developers.strava.com/"
    )

    def __init__(
        self,
        logger: loggers.MytralLogger | None = None,
    ):
        """Constructor."""
        plugins.ActivityImportPlugin.__init__(
            self,
            name=StravaActivityImportPlugin.NAME,
            description=StravaActivityImportPlugin.DESCRIPTION,
        )

        self.log_name = f"[{self.name}]"
        self.logger = logger or app_logger

    def parse_strava_timestamp(self, ts: str) -> tuple[int, int, int, int, int, int]:
        def ts_fragment_to_int(fragment: str) -> int:
            if fragment and len(fragment):
                try:
                    return int(fragment)
                except Exception as ex:
                    self.logger.warning(f"Unable to parse Strava timestamp: '{ex}'")
                    pass
            return 0

        year = 0
        month = 0
        day = 0
        hour = 0
        minute = 0
        second = 0
        if ts and isinstance(ts, str) and len(ts) == len("2022-12-24T08:57:55Z"):
            year = ts_fragment_to_int(ts[:4])
            month = ts_fragment_to_int(ts[5:7])
            day = ts_fragment_to_int(ts[8:10])
            hour = ts_fragment_to_int(ts[11:13])
            minute = ts_fragment_to_int(ts[14:16])
            second = ts_fragment_to_int(ts[17:19])

        return year, month, day, hour, minute, second

    @staticmethod
    def _strava_activity_type_key(dataset_item: dict) -> str:
        """Get normalized Strava activity type key from known API fields."""
        for field in ("activity_type", "sport_type", "type"):
            value = dataset_item.get(field)
            if isinstance(value, str) and value:
                return value.lower()
        return ""

    def import_activity(
        self,
        dataset_item: list[tuple[str, pathlib.Path | str | dict]],
        user_profile: settings.UserProfile,
        **kwargs,
    ) -> entities.ActivityEntity:
        correlation_id: str = kwargs.get("correlation_id", str(uuid.uuid4()))

        self.logger.debug(
            f"{self.log_name} importing Strava activity type '{type(dataset_item)}' ..."
        )

        if not isinstance(dataset_item, dict):
            raise ValueError(
                f"{self.log_name} only dict supported as the import format"
            )

        # Strava 2 MyTraL mapping

        # activity types: Strava -> MyTraL mapping - LIST
        valid_activity_type_ids = kwargs.get("valid_activity_type_ids")
        if not valid_activity_type_ids:
            valid_activity_type_ids = list(
                app_user_ds.list_activity_types(
                    user_id=user_profile.user_id
                ).activity_types_by_key.keys()
            )

        # gear: Strava -> MyTraL mapping - map: strava ID -> MyTraL ID
        strava_gear_dict = kwargs.get("strava_gear_dict")
        if not strava_gear_dict:
            strava_gear_dict = app_user_ds.list_gear(
                user_id=user_profile.user_id
            ).to_dict_by_external_id("strava")

        # - safely handle Unicode chars in activity data to prevent UnicodeEncodeError
        activity_str = str(dataset_item)[:110]
        safe_activity_str = (
            activity_str.encode("ascii", errors="replace").decode("ascii")
            if activity_str
            else ""
        )
        self.logger.info(
            f"{self.log_name} importing Strava activity: '{safe_activity_str}...'"
        )

        entity = entities.ActivityEntity()
        entity.key = app_user_ds.create_key()

        (
            entity.when_year,
            entity.when_month,
            entity.when_day,
            entity.when_hour,
            entity.when_minute,
            entity.when_second,
        ) = self.parse_strava_timestamp(dataset_item.get("start_date_local", ""))

        entity.name = dataset_item.get("name", "")
        entity.description = ""

        entity.sort_code = 1
        entity.workout_sort_code = 1

        entity.where = dataset_item.get("location_country", "")

        strava_sport = self._strava_activity_type_key(dataset_item)
        if strava_sport not in valid_activity_type_ids:
            entity.activity_type_key = icommons.STRAVA_TO_MYTRAL_AT.get(
                strava_sport, strava_sport
            )
        else:
            entity.activity_type_key = strava_sport

        # TODO suffer score to easy/medium/hard
        entity.intensity = commons.INTENSITY_EASY
        strava_gear_id = dataset_item.get("gear_id", "")
        if strava_gear_id:
            if strava_gear_id in strava_gear_dict:
                entity.gears = [strava_gear_dict[strava_gear_id].key]
            else:
                # gear not yet in MyTraL - store the raw Strava ID with the
                # canonical prefix so the gear sync task can discover it later
                entity.gears = [f"{icommons.STRAVA_GEAR_PREFIX_ID}{strava_gear_id}"]
        entity.formula = ""

        # duration
        strava_elapsed_seconds = dataset_item.get("moving_time", 0)
        if strava_elapsed_seconds:
            entity.hours = int(strava_elapsed_seconds / 3600)
            if entity.hours:
                strava_elapsed_seconds -= entity.hours * 3600
            entity.minutes = int(strava_elapsed_seconds / 60)
            entity.seconds = int(strava_elapsed_seconds % 60)
        else:
            entity.hours = entity.minutes = entity.seconds = 0

        entity.distance = int(dataset_item.get("distance", 0))

        entity.warm_up = False
        entity.cool_down = False
        entity.commute = bool(dataset_item.get("commute", False))
        entity.ranked = False
        entity.race = False

        entity.kcal = 0
        entity.max_speed = dataset_item.get("max_speed", 0.0) * 3.6
        entity.elevation_gain = int(dataset_item.get("total_elevation_gain", 0))
        entity.elevation_min = int(dataset_item.get("elev_low", 0))
        entity.elevation_max = int(dataset_item.get("elev_high", 0))
        entity.avg_watts = float(dataset_item.get("average_watts", 0))
        entity.max_watts = 0.0

        entity.avg_cadence = int(dataset_item.get("average_cadence", 0))
        entity.max_cadence = 0

        entity.avg_hr = int(dataset_item.get("average_heartrate", 0))
        entity.max_hr = int(dataset_item.get("max_heartrate", 0))
        entity.min_hr = 0

        entity.weight = 0.0

        entity.weather = ""
        entity.temperature = 0

        entity.suffer_score = float(dataset_item.get("suffer_score", 0.0))
        entity.fitness_score = 0.0

        # src ~ import
        entity.src = SRC_STRAVA
        entity.src_key = str(dataset_item.get("id", ""))
        entity.src_descriptor = f"api:{correlation_id}"
        entity.src_url = f"{SRC_STRAVA_BASE_URL}{entity.src_key}"

        # entity creation & validation
        imported_entity = entities.evaluate_activity(entity)
        # the following metrics are calculated from the input values from above:
        # - duration
        # - duration_seconds
        # - avg_speed
        # - bmi
        # - burnt_fat
        entities.evaluate_activity(entity=imported_entity, user_profile=user_profile)

        return imported_entity


class StravaActivitiesImportPlugin(plugins.ActivitiesImportPlugin):
    NAME = "Strava API activities import"
    DESCRIPTION = (
        "Imports activities from the proprietary strava.com JSON format."
        "See: https://developers.strava.com/"
    )

    # raw Strava JSON
    USE_TYPE_STRAVA_JSON = "USE_TYPE_STRAVA_JSON"
    # raw Strava list loaded from Strava JSON
    USE_TYPE_STRAVA_LIST = "USE_TYPE_STRAVA_LIST"

    def __init__(
        self,
        logger: loggers.MytralLogger | None = None,
    ):
        """Constructor."""
        plugins.ActivitiesImportPlugin.__init__(
            self,
            name=StravaActivitiesImportPlugin.NAME,
            description=StravaActivityImportPlugin.DESCRIPTION,
        )

        self.log_name = f"[{self.name}]"
        self.logger = logger or app_logger

        self.activity_import_plugin = plugins.registry.get_plugin(
            StravaActivityImportPlugin.NAME
        )

    def import_activities(
        self,
        datasets: dict[str, pathlib.Path | str | list],
        user_profile: settings.UserProfile,
        output_path: pathlib.Path | None = None,
        **kwargs,
    ) -> list[entities.ActivityEntity]:
        """Import Strava activities.

        Parameters
        ----------
        datasets: dict[str, list[pathlib.Path | pathlib.Path | str | list[dict]]]
            Dataset might be:
            - dict[str, Path] ... use type to file specified as Path
            - dict[str, str] ... use type to file specified as string
            - dict[str, list] ... use type to the list of dictionaries in Strava format
        user_profile: settings.UserProfile
            User profile.
        output_path: pathlib.Path | None
            Optional path where to write imported MyTraL JSON activities.
        kwargs: dict
            Extra parameters:
            `year` ... import activities from given year only (by default are imported
            all the activities), `gear` ... Strava to MyTraL gear mapping.

        """
        self.logger.debug(f"{self.log_name} importing raw Strava activities...")
        # list of raw Strava activities
        raw_activities: list[dict] = []

        correlation_id: str = kwargs.get("correlation_id", str(uuid.uuid4()))

        strava_json_path = datasets.get(self.USE_TYPE_STRAVA_JSON)
        if not strava_json_path:
            raw_activities: list[dict] = datasets.get(self.USE_TYPE_STRAVA_LIST, [])
            if not raw_activities:
                raise ValueError(
                    f"{self.log_name} neither Strava activities as JSON file nor as "
                    f"list of dictionaries provided - nothing to import"
                )
            if not isinstance(raw_activities, list):
                raise ValueError(
                    f"{self.log_name} raw Strava activities must be either a list or a "
                    f"path to a JSON file, but the type is {type(raw_activities)}"
                )
        elif not pathlib.Path(strava_json_path).exists():
            raise ValueError(
                f"{self.log_name} unable to find Strava activities JSON file: "
                f"{strava_json_path}"
            )
        else:
            with open(strava_json_path, "r") as f:
                raw_activities = json.load(f)

        year_str = str(kwargs.get("year", ""))

        # MAPPING: Strava 2 MyTraL

        # activity types: Strava -> MyTraL mapping - LIST
        valid_activity_type_ids = list(
            app_user_ds.list_activity_types(
                user_id=user_profile.user_id
            ).activity_types_by_key.keys()
        )

        # gear: Strava -> MyTraL mapping - map: strava ID -> MyTraL ID
        strava_gear_dict = app_user_ds.list_gear(
            user_id=user_profile.user_id
        ).to_dict_by_external_id("strava")

        self.logger.info(
            f"{self.log_name} importing {len(raw_activities)} Strava activities..."
        )
        activities = []
        for e, strava_item in enumerate(raw_activities):
            if year_str and not strava_item.get("start_date", "").startswith(year_str):
                self.logger.info(
                    f"{self.log_name} SKIPPING Strava activity (year filter) #{e}"
                )
                continue

            self.logger.info(f"{self.log_name} importing Strava activity #{e}")
            activity_entity = self.activity_import_plugin.import_activity(
                dataset_item=strava_item,
                user_profile=user_profile,
                valid_activity_type_ids=valid_activity_type_ids,
                strava_gear_dict=strava_gear_dict,
                correlation_id=correlation_id,
            )

            activities.append(activity_entity)

        if output_path:
            persistences.save_json(
                file_path=output_path, data_dict=[a.to_dict() for a in activities]
            )

        return activities


# PLUGINS REGISTRY: register strava.com activity import plugin
plugins.registry.register(StravaActivityImportPlugin())
# PLUGINS REGISTRY: register strava.com activities import plugin
plugins.registry.register(StravaActivitiesImportPlugin())


#
# INTEGRATION: strava.com service
#


def is_refresh_token_valid(user_profile: settings.UserProfile) -> bool:
    """Check whether is the refresh token valid (do NOT know how to check actual
    token).

    Returns
    -------
    bool
        ``True`` if refresh token valid, else ``False``.

    """
    return bool(user_profile.strava_refresh_token)


def is_access_token_valid(user_profile: settings.UserProfile) -> tuple[bool, bool]:
    """Check whether is the user authenticated - access token is valid - with Strava.

    Returns
    -------
    tuple[bool,bool]
        Tuple of two booleans:
        - first boolean indicates whether is the access token set
        - second boolean indicates if the user's authentication token is still valid

    """
    did_authentication = bool(user_profile.strava_access_token)
    if did_authentication:
        if user_profile.strava_auth_until > 0:
            # check if the token is still valid
            now = int(datetime.now().timestamp())
            return True, bool(user_profile.strava_auth_until > now)
        else:
            return True, False
    else:
        return False, False


def auth_get_access_for_refresh_token(
    user_profile: settings.UserProfile,
    logger: loggers.MytralLogger,
):
    """Get Strava access token using the refresh token.

    Parameters
    ----------
    user_profile : UserProfile
        User profile.
    logger :
        Logger.

    """
    response = requests.post(
        url="https://www.strava.com/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": f"{user_profile.strava_client_id}",
            "client_secret": f"{user_profile.strava_client_secret}",
            "refresh_token": f"{user_profile.strava_refresh_token}",
        },
    )
    strava_tokens = response.json()

    if not strava_tokens or "access_token" not in strava_tokens:
        logger.error("Strava token refresh failed: server returned no access_token")
        raise ValueError(
            "Failed to get Strava access token during refresh. "
            "Check Strava API credentials and refresh token validity."
        )

    logger.debug("Strava token refresh succeeded")
    user_profile.strava_access_token = strava_tokens["access_token"]
    user_profile.strava_refresh_token = strava_tokens["refresh_token"]
    user_profile.strava_auth_until = int(strava_tokens["expires_at"])
    user_profile.refresh()  # update the user profile string representations

    return user_profile


def auth_get_auth_code_url(
    user_profile: settings.UserProfile,
    mytral_url: str = f"http://127.0.0.1:5000/{URL_AUTH_CALLBACK}",
):
    """Get the Strava authentication code.

    Parameters
    ----------
    user_profile : UserProfile
        User profile.
    mytral_url : str
        URL where Strava should redirect after the authorization.
        IMPORTANT: domain must be allowed in Strava configuration:
        Strava > Settings > My API Application > Edit > Authorization Callback Domain
        Only 1 domain can be configured - either localhost OR deployment domain must be
        used.

    Returns
    -------
    str
        URL which can be used to get the access and refresh tokens.

    """

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
        f"{URL_OAUTH_AUTH}"
        f"?client_id={user_profile.strava_client_id}"
        f"&redirect_uri={mytral_url}"
        f"&response_type=code"
        f"&approval_prompt=auto"  # force / auto
        f"&scope=profile:read_all,activity:read_all"
        # ^ profile:read_all,activity:read_all
        # ^ read (shown on profile)
    )
    app_logger.info(
        f"URL to AUTHORIZE and get the code with temporal validity:\n{strava_oauth_url}"
    )
    return strava_oauth_url


def auth_get_n_set_auth_token(
    user_profile: settings.UserProfile,
    ds: dataset.UserDataset,
    logger: loggers.MytralLogger,
) -> str:
    """Get Strava access token.

    Parameters
    ----------
    user_profile : settings.UserProfile
        User profile with Strava authentication code.
    ds :
        User dataset.
    logger : loggers.MytralLogger
        logger.

    See also:
    * https://developers.strava.com/docs/authentication/

    """

    response = requests.post(
        url="https://www.strava.com/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": f"{user_profile.strava_client_id}",
            "client_secret": f"{user_profile.strava_client_secret}",
            "code": f"{user_profile.strava_code}",
        },
    )
    strava_tokens = response.json()

    if not strava_tokens or "access_token" not in strava_tokens:
        logger.error(
            "Strava auth-code exchange failed: server returned no access_token"
        )
        raise ValueError(
            "Failed to get Strava access token from auth code. "
            "Check Strava client credentials and authorization code validity."
        )

    logger.debug("Strava auth-code exchange succeeded")
    user_profile.strava_access_token = strava_tokens["access_token"]
    user_profile.strava_refresh_token = strava_tokens["refresh_token"]
    # expires_at ~ epoch timestamp e.g. 1718588142, 1719092090
    # - token expires in ~6h
    # - time zone for the timestamp is UTC
    user_profile.strava_auth_until = int(strava_tokens["expires_at"])
    user_profile.refresh()  # update the user profile string representations

    # persist the token
    ds.update_profile(user_profile)

    return user_profile.strava_access_token


def auth_get_access_using_refresh_token(
    user_profile: settings.UserProfile,
    ds: dataset.UserDataset,
    logger: loggers.MytralLogger,
) -> str:
    """Get Strava access token using refresh token.

    Parameters
    ----------
    user_profile : settings.UserProfile
        User profile.
    ds :
        User dataset.
    logger : loggers.MytralLogger
        logger.

    See also:
    * https://developers.strava.com/docs/authentication/

    """

    response = requests.post(
        url="https://www.strava.com/oauth/token",
        data={
            "client_id": f"{user_profile.strava_client_id}",
            "client_secret": f"{user_profile.strava_client_secret}",
            "refresh_token": f"{user_profile.strava_refresh_token}",
            "grant_type": "refresh_token",
        },
    )
    strava_tokens = response.json()

    if not strava_tokens or "access_token" not in strava_tokens:
        logger.error(
            "Strava refresh-token exchange failed: server returned no access_token"
        )
        raise ValueError(
            "Failed to get Strava access token using refresh token. "
            "Check Strava client credentials and refresh token validity."
        )

    logger.debug("Strava refresh-token exchange succeeded")
    user_profile.strava_access_token = strava_tokens["access_token"]
    user_profile.strava_refresh_token = strava_tokens["refresh_token"]
    user_profile.strava_auth_until = int(strava_tokens["expires_at"])
    user_profile.refresh()  # update the user profile string representations

    # persist the token
    ds.update_profile(user_profile)

    return user_profile.strava_access_token


def export_json_from_strava_service(
    user_profile: settings.UserProfile,
    logger: loggers.MytralLogger,
    after_timestamp: int | None = None,
    days_back: int = 0,
    page_size: int = 200,
) -> list:
    """Export all/new activities as "Strava JSON" using Strava API.

    Parameters
    ----------
    user_profile : settings.UserProfile
        User profile.
    logger :
        logger.
    page_size : int
        Number of activities per page.
    after_timestamp : int, optional
        An epoch timestamp to use for filtering activities that have taken place after
        a certain time - typically timestamp of the last activity (end time).
        Pass ``0`` to fetch all activities since the Unix epoch. If ``None`` (default),
        falls back to ``days_back`` or a 1-day window.
    days_back: int
        Number of days to sync. Used only if non-zero. If both ``after_timestamp``
        and `days` are set, the ``after_timestamp`` is used.

    Returns
    -------
    list :
        Exported activities as Strava JSON list (Strava format).

    """
    import datetime as true_datetime

    logger.info("Syncing Strava activities...")
    exported_activities = []

    if after_timestamp is not None:
        after_ts_int = after_timestamp
    elif days_back:
        after_ts_obj = true_datetime.date.today() - true_datetime.timedelta(days_back)
        after_ts_int = int(after_ts_obj.strftime("%s"))
    else:
        # sync 1 day by default
        after_ts_obj = true_datetime.date.today() - true_datetime.timedelta(1)
        after_ts_int = int(after_ts_obj.strftime("%s"))

    after_ts_html_param = f"&after={after_ts_int}" if after_ts_int else ""
    logger.info(f"  After timestamp: {after_ts_int}")

    page = 1
    logger.info("Downloading activities as JSON file...")
    while True:
        logger.info(f"  Page {page}")
        logger.info("    Downloading data...")
        # See:
        #   https://developers.strava.com/docs/reference/
        #     #api-Activities-getLoggedInAthleteActivities
        # Epoch ~ seconds from 1970-01-01T00:00:00Z
        #   https://www.epochconverter.com/
        request_url = (
            f"{URL_ACTIVITIES}?per_page={page_size}&page={page}{after_ts_html_param}"
        )
        logger.info(f"      GET {URL_ACTIVITIES} page={page}")
        response_activities = requests.get(
            request_url,
            headers={"Authorization": f"Bearer {user_profile.strava_access_token}"},
        )
        if not response_activities:
            break
        else:
            logger.info(f"      {response_activities}")

        activities_json = response_activities.json()
        if activities_json:
            logger.info(f"    Downloaded {len(activities_json)} activities")
        else:
            logger.info(f"    No more activities ({activities_json})")
            break
        exported_activities.extend(activities_json)

        page += 1

    logger.info(f"Export DONE: {len(exported_activities)} activities")

    return exported_activities


def _strava_get(url: str, access_token: str, logger) -> dict | list | None:
    """Make an authenticated GET request to the Strava API.

    Parameters
    ----------
    url : str
        Full Strava API URL.
    access_token : str
        Valid Strava access token.
    logger :
        Logger instance.

    Returns
    -------
    dict | list | None
        Parsed JSON response, or None on failure.
    """
    logger.info(f"  GET {url}")
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if not response or response.status_code != 200:
        logger.warning(
            f"  Strava API returned "
            f"{response.status_code if response else 'no response'}"
        )
        return None
    return response.json()


def fetch_activity_detail(
    activity_id: int | str,
    access_token: str,
    logger,
) -> dict | None:
    """Fetch detailed activity metadata from Strava.

    Calls ``GET /api/v3/activities/{id}`` which returns the full activity
    object including ``description``, ``calories``, and other fields not
    present in the list endpoint response.

    Parameters
    ----------
    activity_id : int | str
        Strava activity identifier.
    access_token : str
        Valid Strava access token.
    logger :
        Logger instance.

    Returns
    -------
    dict | None
        Activity detail dict, or None on failure.
    """
    url = f"{URL_ACTIVITIES}/{activity_id}"
    return _strava_get(url, access_token, logger)


def fetch_activity_streams(
    activity_id: int | str,
    access_token: str,
    logger,
) -> dict | None:
    """Fetch time-series stream data for a Strava activity.

    Calls ``GET /api/v3/activities/{id}/streams`` with keys: time, latlng,
    distance, altitude, velocity_smooth, heartrate, cadence, watts, temp,
    moving, grade_smooth.

    Parameters
    ----------
    activity_id : int | str
        Strava activity identifier.
    access_token : str
        Valid Strava access token.
    logger :
        Logger instance.

    Returns
    -------
    dict | None
        Stream dict keyed by stream type, or None on failure.
    """
    stream_keys = (
        "time,latlng,distance,altitude,velocity_smooth,"
        "heartrate,cadence,watts,temp,moving,grade_smooth"
    )
    url = f"{URL_ACTIVITIES}/{activity_id}/streams?keys={stream_keys}&key_by_type=true"
    return _strava_get(url, access_token, logger)


def streams_to_gpx(
    streams: dict,
    activity_name: str = "",
) -> bytes:
    """Convert Strava stream data to a GPX XML payload.

    Parameters
    ----------
    streams : dict
        Strava stream dict keyed by stream type (e.g. ``latlng``, ``time``,
        ``altitude``, ``heartrate``, ``cadence``).
    activity_name : str
        Activity name for the GPX track name.

    Returns
    -------
    bytes
        GPX XML as UTF-8 bytes.
    """
    latlng_stream = streams.get("latlng", {})
    time_stream = streams.get("time", {})
    altitude_stream = streams.get("altitude", {})
    hr_stream = streams.get("heartrate", {})
    cadence_stream = streams.get("cadence", {})

    latlng_data = latlng_stream.get("data") if latlng_stream else None
    if not latlng_data:
        raise ValueError("Strava streams contain no latlng data")

    time_data = time_stream.get("data") if time_stream else None
    alt_data = altitude_stream.get("data") if altitude_stream else None
    hr_data = hr_stream.get("data") if hr_stream else None
    cad_data = cadence_stream.get("data") if cadence_stream else None

    import xml.etree.ElementTree as ET
    from xml.dom import minidom

    gpx_ns = "http://www.topografix.com/GPX/1/1"
    gpxtpx_ns = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"

    ET.register_namespace("", gpx_ns)
    ET.register_namespace("gpxtpx", gpxtpx_ns)

    gpx = ET.Element(
        "gpx",
        {
            "version": "1.1",
            "creator": "mytral-strava-import",
            "xmlns": gpx_ns,
            "xmlns:gpxtpx": gpxtpx_ns,
        },
    )

    if activity_name:
        metadata = ET.SubElement(gpx, "metadata")
        name_el = ET.SubElement(metadata, "name")
        name_el.text = activity_name

    trk = ET.SubElement(gpx, "trk")
    trk_name = ET.SubElement(trk, "name")
    trk_name.text = activity_name or "Strava Activity"
    trkseg = ET.SubElement(trk, "trkseg")

    for i, coord in enumerate(latlng_data):
        trkpt = ET.SubElement(
            trkseg,
            "trkpt",
            {"lat": str(coord[0]), "lon": str(coord[1])},
        )
        if alt_data and i < len(alt_data):
            ele = ET.SubElement(trkpt, "ele")
            ele.text = str(alt_data[i])
        if time_data and i < len(time_data):
            from datetime import datetime as _dt

            ts = _dt.utcfromtimestamp(time_data[i])
            time_el = ET.SubElement(trkpt, "time")
            time_el.text = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        if hr_data and i < len(hr_data) or cad_data and i < len(cad_data):
            extensions = ET.SubElement(trkpt, "extensions")
            tpe = ET.SubElement(extensions, f"{{{gpxtpx_ns}}}TrackPointExtension")
            if hr_data and i < len(hr_data):
                hr_el = ET.SubElement(tpe, f"{{{gpxtpx_ns}}}hr")
                hr_el.text = str(int(hr_data[i]))
            if cad_data and i < len(cad_data):
                cad_el = ET.SubElement(tpe, f"{{{gpxtpx_ns}}}cad")
                cad_el.text = str(int(cad_data[i]))

    rough_string = ET.tostring(gpx, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
    gpx_xml = declaration + reparsed.documentElement.toprettyxml(indent="  ")
    return gpx_xml.encode("utf-8")


def fetch_activity_photos(
    activity_id: int | str,
    access_token: str,
    logger,
) -> list[dict] | None:
    """Fetch photo metadata for a Strava activity.

    Calls ``GET /api/v3/activities/{id}/photos``. The ``urls`` field in each
    photo entry contains download links keyed by size (e.g. ``1024``, ``2048``).

    Parameters
    ----------
    activity_id : int | str
        Strava activity identifier.
    access_token : str
        Valid Strava access token.
    logger :
        Logger instance.

    Returns
    -------
    list[dict] | None
        List of photo metadata dicts, or None on failure.
    """
    url = f"{URL_ACTIVITIES}/{activity_id}/photos?size=2048"
    return _strava_get(url, access_token, logger)


def download_photo(
    photo_url: str,
    logger,
) -> bytes | None:
    """Download a photo from a Strava photo URL.

    Parameters
    ----------
    photo_url : str
        The photo download URL (e.g. ``1024``-size URL from photo metadata).
    logger :
        Logger instance.

    Returns
    -------
    bytes | None
        Photo data as bytes, or None on failure.
    """
    logger.info(f"  Downloading photo: {photo_url}")
    response = requests.get(photo_url)
    if not response or response.status_code != 200:
        logger.warning(
            f"  Photo download failed: "
            f"{response.status_code if response else 'no response'}"
        )
        return None
    return response.content


def _sync_gear(strava_user_gear: settings.StravaUserGear, gear_id: str) -> dict:
    """Sync gear details from Strava.

    {
      'id': 'g12229388',
      'primary': False,
      'name': 'Salomon Speedcross 5 blue/white',
      'nickname': 'blue/white',
      'resource_state': 3,
      'retired': False,
      'distance': 1474672,
      'converted_distance': 1474.7,
      'brand_name': 'Salomon',
      'model_name': 'Speedcross 5',
      'description': '',
      'notification_distance': 500
    }

    Strava IDs:

    "strava-gear-id:g12229388",
    "strava-gear-id:g13822170",
    "strava-gear-id:g17135873",

    """

    # http get "https://www.strava.com/api/v3/gear/{id}"
    # "Authorization: Bearer [[token]]"
    strava_user_gear.logger.info(
        f"Strava gear sync: downloading details of {gear_id}..."
    )
    request_url = f"{URL_GEARS}/{gear_id}"
    headers = {
        "Authorization": f"Bearer {strava_user_gear.user_profile.strava_access_token}"
    }
    strava_user_gear.logger.info(f"  {request_url}")
    strava_user_gear.logger.info(f"    {headers}")

    response_obj = requests.get(request_url, headers=headers)
    if not response_obj:
        raise ValueError(f"Failed to download Strava gear details of {gear_id}")
    else:
        strava_user_gear.logger.info(f"  {response_obj}")

    gear_json = response_obj.json()
    if gear_json:
        strava_user_gear.logger.info(f"    Downloaded\n{gear_json}")
    else:
        strava_user_gear.logger.info(f"    No more activities ({gear_json})")

    return gear_json or {}


def sync_strava_gear(
    strava_user_gear: settings.StravaUserGear, gear_ids: list[str]
) -> list[dict]:
    strava_user_gear.gears.clear()

    if gear_ids and isinstance(gear_ids, list):
        for gear_id in gear_ids:
            strava_user_gear.gears.append(
                _sync_gear(strava_user_gear=strava_user_gear, gear_id=gear_id)
            )

    return strava_user_gear.gears


class AuthMentorAdvice(enum.Enum):
    """Controller actions guide user to getting valid access token."""

    # user is authenticated > no operation/action needed
    NO_OP_AUTHENTICATED = enum.auto()
    # Strava not configured > configure it by getting client ID and client secret
    CONFIGURE = enum.auto()
    # get refresh token > use client ID and client secret to get refresh (and access) t.
    GET_REFRESH_TOKEN = enum.auto()
    # get access token using the refresh token (+ client ID and client secret)
    USE_REFRESH_TOKEN = enum.auto()


def ask_mentor(user_profile: settings.UserProfile) -> tuple[AuthMentorAdvice, str]:
    """Strava controller gets Strava artifacts (config, secrets, tokens) and based
    on their availability and validity it is able to suggest the next action to take.

    See ``UserProfile`` for detailed Strava API attributes documentation.

    Parameters
    ----------
    user_profile : UserProfile
        User profile with Strava secrets.

    Returns
    -------
    tuple[ControllerAction, string]
        Action to take and error message (if needed)

    """
    # CHECK whether Strava is configured
    if not user_profile.strava_client_id or not user_profile.strava_client_secret:
        return (
            AuthMentorAdvice.CONFIGURE,
            "Strava client ID and client secret must be configured...",
        )

    # CHECK whether ACCESS token is available and is valid
    _, access_token_valid = is_access_token_valid(user_profile)
    if access_token_valid:
        return (
            AuthMentorAdvice.NO_OP_AUTHENTICATED,
            "Access token is valid - using it to access Strava API...",
        )

    # CHECK whether REFRESH token is available and is valid
    if not is_refresh_token_valid(user_profile):
        return (
            AuthMentorAdvice.GET_REFRESH_TOKEN,
            "Using client ID and client secret to get refresh (and access) token...",
        )

    # client ID, client secret and refresh token can be used to get access token
    return (
        AuthMentorAdvice.USE_REFRESH_TOKEN,
        "Using refresh token, client ID and client secret to get access token...",
    )
