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

"""Polar Flow (AccessLink API) import plugin and client.

Imports the athlete's own training data from Polar Flow (flow.polar.com) using the
official Polar AccessLink API (https://www.polar.com/accesslink-api/). The exercise
transaction model (create -> list -> fetch -> commit) prevents duplicate delivery.

Access tokens do not expire unless revoked and there is no refresh token, so the
credential handling is simpler than the Strava integration. See ``POLAR_FLOW.md``.
"""

import enum
import re
import time
import uuid

import requests

from mytral import app_logger
from mytral import app_user_ds
from mytral import commons
from mytral import loggers
from mytral import plugins
from mytral import settings
from mytral.backends import entities
from mytral.integrations import icommons

# URLs
URL_API_BASE = "https://www.polaraccesslink.com"
URL_OAUTH_AUTH = "https://flow.polar.com/oauth2/authorization"
URL_OAUTH_TOKEN = "https://polarremote.com/v2/oauth2/token"
URL_AUTH_CALLBACK = "polar/auth-callback"
URL_FLOW_TRAINING_BASE = "https://flow.polar.com/training/analysis/"
OAUTH_SCOPE = "accesslink.read_all"

# max number of characters of an error response body written to the log
VALUE_LOG_BODY_LIMIT = 500

# entity source (BOTH the API and the GDPR export normalize to this src)
SRC_POLAR_FLOW = "polar-flow"

# HTTP retry handling for the AccessLink rate limit (HTTP 429)
_MAX_RETRIES = 3
_DEFAULT_BACKOFF_S = 2


#
# HTTP: authenticated requests with bounded 429/Retry-After backoff
#


def _request(
    method: str,
    url: str,
    access_token: str,
    logger: loggers.MytralLogger,
    accept: str = "application/json",
    json_body: dict | None = None,
) -> requests.Response | None:
    """Make an authenticated AccessLink request, retrying on HTTP 429.

    Parameters
    ----------
    method : str
        HTTP method (``GET``, ``POST`` or ``PUT``).
    url : str
        Full request URL.
    access_token : str
        Valid AccessLink access token.
    logger : loggers.MytralLogger
        Logger instance.
    accept : str
        Value of the ``Accept`` header (JSON for summaries, GPX/TCX for recordings).
    json_body : dict | None
        Optional JSON request body.

    Returns
    -------
    requests.Response | None
        The response, or ``None`` if the request kept failing.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": accept,
    }
    for attempt in range(_MAX_RETRIES + 1):
        response = requests.request(
            method=method, url=url, headers=headers, json=json_body
        )
        # HTTP-level trace of every AccessLink call - never logs the token, only
        # the method, path and status, so the whole sync is diagnosable
        logger.debug(
            "Polar AccessLink request",
            method=method,
            url=url,
            status=response.status_code if response is not None else None,
            attempt=attempt + 1,
        )
        if response is not None and response.status_code == 429:
            if attempt >= _MAX_RETRIES:
                logger.warning("Polar AccessLink rate limit hit - giving up")
                return response
            retry_after = response.headers.get("Retry-After")
            delay = (
                int(retry_after)
                if retry_after and retry_after.isdigit()
                else _DEFAULT_BACKOFF_S * (attempt + 1)
            )
            logger.warning(
                f"Polar AccessLink rate limit hit - retrying in {delay}s "
                f"(attempt {attempt + 1}/{_MAX_RETRIES})"
            )
            time.sleep(delay)
            continue
        return response
    return None


#
# OAuth2 (authorization_code grant) - tokens do not expire unless revoked
#


class AuthMentorAdvice(enum.Enum):
    """Guides the auth controller to the next action to take."""

    # client ID / secret missing - configure them first
    CONFIGURE = enum.auto()
    # configured but no access token - start OAuth to authenticate
    AUTHENTICATE = enum.auto()
    # token present but the user is not registered/linked yet
    REGISTER_USER = enum.auto()
    # fully authenticated - nothing to do
    AUTHENTICATED = enum.auto()


def is_authenticated(user_profile: settings.UserProfile) -> bool:
    """Return ``True`` when both an access token and a Polar user id are present."""
    return bool(
        user_profile.polar_flow_access_token and user_profile.polar_flow_user_id
    )


def ask_mentor(user_profile: settings.UserProfile) -> tuple[AuthMentorAdvice, str]:
    """Suggest the next authentication action based on available credentials.

    Parameters
    ----------
    user_profile : settings.UserProfile
        User profile with Polar Flow credentials.

    Returns
    -------
    tuple[AuthMentorAdvice, str]
        Advice and a human-readable message.
    """
    if (
        not user_profile.polar_flow_client_id
        or not user_profile.polar_flow_client_secret
    ):
        return (
            AuthMentorAdvice.CONFIGURE,
            "Polar Flow client ID and client secret must be configured...",
        )
    if not user_profile.polar_flow_access_token:
        return (
            AuthMentorAdvice.AUTHENTICATE,
            "Authenticate with Polar Flow to obtain an access token...",
        )
    if not user_profile.polar_flow_user_id:
        return (
            AuthMentorAdvice.REGISTER_USER,
            "Registering (linking) your Polar user with the client...",
        )
    return (
        AuthMentorAdvice.AUTHENTICATED,
        "Access token is valid - using it to access the Polar AccessLink API...",
    )


def auth_get_auth_code_url(
    user_profile: settings.UserProfile,
    mytral_url: str = f"http://127.0.0.1:5000/{URL_AUTH_CALLBACK}",
) -> str:
    """Build the Polar OAuth2 authorization URL.

    Parameters
    ----------
    user_profile : settings.UserProfile
        User profile with the Polar Flow client ID.
    mytral_url : str
        Redirect URL registered for the client at admin.polaraccesslink.com.

    Returns
    -------
    str
        URL to open so Polar redirects back with an authorization ``code``.
    """
    polar_oauth_url = (
        f"{URL_OAUTH_AUTH}"
        f"?client_id={user_profile.polar_flow_client_id}"
        f"&response_type=code"
        f"&scope={OAUTH_SCOPE}"
        f"&redirect_uri={mytral_url}"
    )
    app_logger.info(f"URL to AUTHORIZE with Polar Flow:\n{polar_oauth_url}")
    return polar_oauth_url


def auth_exchange_code_for_token(
    user_profile: settings.UserProfile,
    code: str,
    mytral_url: str,
    ds,
    logger: loggers.MytralLogger,
) -> str:
    """Exchange an authorization code for a Polar AccessLink access token.

    The token endpoint authenticates the client with HTTP Basic auth and returns a
    long-lived access token plus Polar's numeric ``x_user_id``. Both are persisted.

    Parameters
    ----------
    user_profile : settings.UserProfile
        User profile with Polar client credentials and the authorization code.
    code : str
        OAuth2 authorization code from the redirect.
    mytral_url : str
        Redirect URL that was passed to the authorization endpoint. Polar requires
        the very same value here, otherwise it rejects the exchange.
    ds :
        User dataset (to persist the updated profile).
    logger : loggers.MytralLogger
        Logger instance.

    Returns
    -------
    str
        The obtained access token.
    """
    response = requests.post(
        url=URL_OAUTH_TOKEN,
        auth=(
            user_profile.polar_flow_client_id,
            user_profile.polar_flow_client_secret,
        ),
        headers={"Accept": "application/json"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": mytral_url,
        },
    )
    try:
        tokens = response.json()
    except ValueError:
        # Polar answered with a non-JSON body (gateway error, empty response, ...)
        tokens = {}

    if not isinstance(tokens, dict) or "access_token" not in tokens:
        # only reached when no token was issued - the body carries Polar's
        # error / error_description, never an access token
        logger.error(
            "Polar auth-code exchange failed: no access_token returned",
            status=response.status_code,
            response=response.text[:VALUE_LOG_BODY_LIMIT],
        )
        raise ValueError(
            "Failed to get Polar Flow access token from auth code. "
            "Check the Polar client credentials and authorization code validity."
        )

    logger.debug("Polar auth-code exchange succeeded")
    user_profile.polar_flow_access_token = str(tokens["access_token"])
    if tokens.get("x_user_id"):
        user_profile.polar_flow_user_id = str(tokens["x_user_id"])
    ds.update_profile(user_profile)

    return user_profile.polar_flow_access_token


def register_user(
    user_profile: settings.UserProfile,
    ds,
    logger: loggers.MytralLogger,
) -> str:
    """Register (link) the authenticated user with the AccessLink client.

    Idempotent: a ``409 Conflict`` (already registered) is treated as success. The
    Polar user id is stored on the profile for use in transaction URLs.

    Parameters
    ----------
    user_profile : settings.UserProfile
        User profile with a valid access token.
    ds :
        User dataset (to persist the updated profile).
    logger : loggers.MytralLogger
        Logger instance.

    Returns
    -------
    str
        The Polar user id.
    """
    member_id = user_profile.polar_flow_member_id or str(uuid.uuid4())
    user_profile.polar_flow_member_id = member_id

    response = _request(
        method="POST",
        url=f"{URL_API_BASE}/v3/users",
        access_token=user_profile.polar_flow_access_token,
        logger=logger,
        json_body={"member-id": member_id},
    )
    status = response.status_code if response is not None else None
    if status in (200, 201):
        body = response.json() or {}
        polar_user_id = body.get("polar-user-id") or body.get("polar_user_id")
        if polar_user_id:
            user_profile.polar_flow_user_id = str(polar_user_id)
        # the registration moment is the delivery boundary: only exercises
        # uploaded to Flow from now on are returned by the transaction API
        logger.info(
            "Polar user registered - AccessLink now delivers only exercises "
            "uploaded to Flow after this moment",
            polar_user_id=user_profile.polar_flow_user_id,
            member_id=member_id,
            status=status,
        )
    elif status == 409:
        # already registered - keep whatever polar_flow_user_id we already have
        logger.info(
            "Polar user already registered - continuing",
            polar_user_id=user_profile.polar_flow_user_id,
            status=status,
        )
    else:
        logger.error(f"Polar user registration failed: status={status}")
        raise ValueError(
            f"Failed to register Polar user (status={status}). "
            "Check the access token and client configuration."
        )

    ds.update_profile(user_profile)

    # without a Polar user id no transaction URL can be built - fail loudly instead
    # of leaving the account silently stuck as "not authenticated"
    if not user_profile.polar_flow_user_id:
        raise ValueError(
            "Polar registration did not yield a user id. Reset the Polar Flow "
            "authentication and authenticate again."
        )

    return user_profile.polar_flow_user_id


#
# Transaction-based pull (create -> list -> fetch -> commit)
#


def create_transaction(
    access_token: str,
    polar_user_id: str,
    logger: loggers.MytralLogger,
) -> str | None:
    """Create an exercise transaction.

    Returns
    -------
    str | None
        The transaction id, or ``None`` when there is no new data (HTTP 204).
    """
    url = f"{URL_API_BASE}/v3/users/{polar_user_id}/exercise-transactions"
    response = _request("POST", url, access_token=access_token, logger=logger)
    if response is None:
        return None
    if response.status_code == 204:
        logger.info(
            "Polar: no new exercises to transact",
            hint=(
                "AccessLink delivers only exercises uploaded to Flow AFTER this "
                "client registered the user and within the last 30 days; older "
                "activities must be imported from the Polar 'Download your data' "
                "(GDPR) export ZIP"
            ),
        )
        return None
    if response.status_code not in (200, 201):
        logger.warning(f"Polar create-transaction failed: {response.status_code}")
        return None
    body = response.json() or {}
    transaction_id = body.get("transaction-id")
    return str(transaction_id) if transaction_id is not None else None


def list_transaction_exercises(
    access_token: str,
    polar_user_id: str,
    transaction_id: str,
    logger: loggers.MytralLogger,
) -> list[str]:
    """List the exercise resource URLs contained in a transaction."""
    url = (
        f"{URL_API_BASE}/v3/users/{polar_user_id}"
        f"/exercise-transactions/{transaction_id}"
    )
    response = _request("GET", url, access_token=access_token, logger=logger)
    if response is None or response.status_code != 200:
        return []
    body = response.json() or {}
    return list(body.get("exercises", []))


def fetch_exercise_summary(
    access_token: str,
    exercise_url: str,
    logger: loggers.MytralLogger,
) -> dict | None:
    """Fetch a single exercise summary (JSON) by its transaction-scoped URL."""
    response = _request("GET", exercise_url, access_token=access_token, logger=logger)
    if response is None or response.status_code != 200:
        logger.warning(
            f"Polar exercise summary fetch failed: "
            f"{response.status_code if response is not None else 'no response'}"
        )
        return None
    return response.json()


def fetch_exercise_gpx(
    access_token: str,
    exercise_url: str,
    logger: loggers.MytralLogger,
) -> bytes | None:
    """Fetch the GPX recording for an exercise (``None`` when no route)."""
    response = _request(
        "GET",
        f"{exercise_url}/gpx",
        access_token=access_token,
        logger=logger,
        accept="application/gpx+xml",
    )
    if response is None or response.status_code != 200 or not response.content:
        return None
    return response.content


def fetch_exercise_tcx(
    access_token: str,
    exercise_url: str,
    logger: loggers.MytralLogger,
) -> bytes | None:
    """Fetch the TCX recording for an exercise (``None`` when unavailable)."""
    response = _request(
        "GET",
        f"{exercise_url}/tcx",
        access_token=access_token,
        logger=logger,
        accept="application/vnd.garmin.tcx+xml",
    )
    if response is None or response.status_code != 200 or not response.content:
        return None
    return response.content


def commit_transaction(
    access_token: str,
    polar_user_id: str,
    transaction_id: str,
    logger: loggers.MytralLogger,
) -> bool:
    """Commit (finalize) a transaction so its exercises are not delivered again."""
    url = (
        f"{URL_API_BASE}/v3/users/{polar_user_id}"
        f"/exercise-transactions/{transaction_id}"
    )
    response = _request("PUT", url, access_token=access_token, logger=logger)
    ok = response is not None and response.status_code in (200, 204)
    if not ok:
        logger.warning(
            f"Polar commit-transaction failed: "
            f"{response.status_code if response is not None else 'no response'}"
        )
    return ok


#
# Parsing helpers (shared by the API and GDPR-export mappings)
#

_ISO_DURATION_RE = re.compile(
    r"^PT"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?$"
)


def parse_iso_duration(duration: str) -> tuple[int, int, int]:
    """Parse an ISO-8601 duration like ``PT1H2M3S`` into (hours, minutes, seconds)."""
    if not duration:
        return 0, 0, 0
    match = _ISO_DURATION_RE.match(duration.strip())
    if not match:
        return 0, 0, 0
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(float(match.group("seconds") or 0))
    return hours, minutes, seconds


def parse_start_time(start_time: str) -> tuple[int, int, int, int, int, int]:
    """Parse ``YYYY-MM-DDTHH:MM:SS`` (Polar local start time) into date/time parts."""
    if (
        start_time
        and isinstance(start_time, str)
        and len(start_time) >= len("2022-12-24T08:57:55")
    ):
        try:
            return (
                int(start_time[0:4]),
                int(start_time[5:7]),
                int(start_time[8:10]),
                int(start_time[11:13]),
                int(start_time[14:16]),
                int(start_time[17:19]),
            )
        except ValueError:
            pass
    return 0, 0, 0, 0, 0, 0


#
# PLUGIN: Polar Flow exercise summary -> MyTraL activity
#


class PolarFlowActivityImportPlugin(plugins.ActivityImportPlugin):
    NAME = "Polar Flow activity import"
    DESCRIPTION = (
        "Imports a single activity from a Polar AccessLink exercise summary. "
        "See: https://www.polar.com/accesslink-api/"
    )

    def __init__(self, logger: loggers.MytralLogger | None = None):
        plugins.ActivityImportPlugin.__init__(
            self,
            name=PolarFlowActivityImportPlugin.NAME,
            description=PolarFlowActivityImportPlugin.DESCRIPTION,
        )
        self.log_name = f"[{self.name}]"
        self.logger = logger or app_logger

    def import_activity(
        self,
        dataset_item: dict,
        user_profile: settings.UserProfile,
        **kwargs,
    ) -> entities.ActivityEntity:
        """Map one Polar exercise summary dict to a MyTraL ``ActivityEntity``."""
        if not isinstance(dataset_item, dict):
            raise ValueError(f"{self.log_name} only dict supported as import format")

        correlation_id: str = kwargs.get("correlation_id", str(uuid.uuid4()))
        valid_activity_type_ids = kwargs.get("valid_activity_type_ids")
        if not valid_activity_type_ids:
            valid_activity_type_ids = list(
                app_user_ds.list_activity_types(
                    user_id=user_profile.user_id
                ).activity_types_by_key.keys()
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
        ) = parse_start_time(dataset_item.get("start-time", ""))

        entity.name = dataset_item.get("name", "") or ""
        entity.description = ""
        entity.sort_code = 1
        entity.workout_sort_code = 1

        sport = dataset_item.get("detailed-sport-info") or dataset_item.get("sport", "")
        entity.activity_type_key = icommons.polar_flow_activity_type(
            sport=sport, valid_activity_type_ids=valid_activity_type_ids
        )

        entity.intensity = commons.INTENSITY_EASY
        entity.formula = ""

        entity.hours, entity.minutes, entity.seconds = parse_iso_duration(
            dataset_item.get("duration", "")
        )

        entity.distance = int(dataset_item.get("distance", 0) or 0)

        entity.warm_up = False
        entity.cool_down = False
        entity.commute = False
        entity.ranked = False
        entity.race = False

        entity.kcal = int(dataset_item.get("calories", 0) or 0)

        heart_rate = dataset_item.get("heart-rate", {}) or {}
        entity.avg_hr = int(heart_rate.get("average", 0) or 0)
        entity.max_hr = int(heart_rate.get("maximum", 0) or 0)
        entity.min_hr = 0

        entity.max_speed = 0.0
        entity.elevation_gain = int(dataset_item.get("elevation-gain", 0) or 0)
        entity.elevation_min = 0
        entity.elevation_max = 0
        entity.avg_watts = 0.0
        entity.max_watts = 0.0
        entity.avg_cadence = 0
        entity.max_cadence = 0
        entity.weight = 0.0
        entity.weather = ""
        entity.temperature = 0
        entity.fitness_score = 0.0

        entity.src = SRC_POLAR_FLOW
        entity.src_key = str(dataset_item.get("id", ""))
        entity.src_descriptor = f"api:{correlation_id}"
        entity.src_url = (
            f"{URL_FLOW_TRAINING_BASE}{entity.src_key}" if entity.src_key else ""
        )

        imported_entity = entities.evaluate_activity(entity)
        entities.evaluate_activity(entity=imported_entity, user_profile=user_profile)
        return imported_entity


class PolarFlowActivitiesImportPlugin(plugins.ActivitiesImportPlugin):
    NAME = "Polar Flow activities import"
    DESCRIPTION = (
        "Imports activities from Polar AccessLink exercise summaries (list). "
        "See: https://www.polar.com/accesslink-api/"
    )

    # list of Polar exercise summary dicts (AccessLink shape; the GDPR export
    # parser normalizes its sessions into this same shape)
    USE_TYPE_POLAR_FLOW_LIST = "USE_TYPE_POLAR_FLOW_LIST"

    def __init__(self, logger: loggers.MytralLogger | None = None):
        plugins.ActivitiesImportPlugin.__init__(
            self,
            name=PolarFlowActivitiesImportPlugin.NAME,
            description=PolarFlowActivitiesImportPlugin.DESCRIPTION,
        )
        self.log_name = f"[{self.name}]"
        self.logger = logger or app_logger
        self.activity_import_plugin = plugins.registry.get_plugin(
            PolarFlowActivityImportPlugin.NAME
        )

    def import_activities(
        self,
        datasets: dict,
        user_profile: settings.UserProfile,
        output_path=None,
        **kwargs,
    ) -> list[entities.ActivityEntity]:
        """Map a list of Polar exercise summaries to MyTraL activities."""
        raw_activities = datasets.get(self.USE_TYPE_POLAR_FLOW_LIST, [])
        if not isinstance(raw_activities, list):
            raise ValueError(
                f"{self.log_name} expected a list of Polar exercise summaries, "
                f"got {type(raw_activities)}"
            )

        correlation_id: str = kwargs.get("correlation_id", str(uuid.uuid4()))
        valid_activity_type_ids = list(
            app_user_ds.list_activity_types(
                user_id=user_profile.user_id
            ).activity_types_by_key.keys()
        )

        self.logger.info(
            f"{self.log_name} importing {len(raw_activities)} Polar exercises..."
        )
        activities = []
        for polar_item in raw_activities:
            activities.append(
                self.activity_import_plugin.import_activity(
                    dataset_item=polar_item,
                    user_profile=user_profile,
                    valid_activity_type_ids=valid_activity_type_ids,
                    correlation_id=correlation_id,
                )
            )
        return activities


# PLUGINS REGISTRY: register Polar Flow activity + activities import plugins
plugins.registry.register(PolarFlowActivityImportPlugin())
plugins.registry.register(PolarFlowActivitiesImportPlugin())
