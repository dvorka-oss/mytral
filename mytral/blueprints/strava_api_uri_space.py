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
import datetime
import uuid

import flask

from mytral import app_config
from mytral import app_logger
from mytral import app_user_ds as ds
from mytral import ff
from mytral import forms
from mytral import persistences
from mytral import plugins
from mytral import security
from mytral import tasks
from mytral.integrations import strava
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app


def _build_strava_task_params(
    user_id: str, dataset_name: str, after_ts: int = 0
) -> dict | None:
    """Build encrypted task parameters for Strava sync.

    Parameters
    ----------
    user_id : str
        User identifier.
    dataset_name : str
        Target dataset name.
    after_ts : int
        Unix timestamp - activities after this will be fetched; 0=all.

    Returns
    -------
    dict | None
        Task parameters dict, or None if user is not authenticated with Strava.
    """
    user_profile = ds.profile(user_id)
    is_auth, is_auth_valid = strava.is_access_token_valid(user_profile)
    if not is_auth or not is_auth_valid:
        # try silent refresh
        if strava.is_refresh_token_valid(user_profile):
            try:
                strava.auth_get_access_for_refresh_token(user_profile, app_logger)
                ds.update_profile(user_profile)
                is_auth, is_auth_valid = strava.is_access_token_valid(user_profile)
            except Exception:
                return None
        if not is_auth or not is_auth_valid:
            return None

    enc_key = app_config.encryption_key
    return {
        "user_id": user_id,
        "dataset_name": dataset_name,
        "after_ts": after_ts,
        "access_token": security.encrypt(
            user_profile.strava_access_token or "", enc_key
        ),
        "refresh_token": security.encrypt(
            user_profile.strava_refresh_token or "", enc_key
        ),
        "client_id": user_profile.strava_client_id or "",
        "client_secret": security.encrypt(
            user_profile.strava_client_secret or "", enc_key
        ),
        "strava_url": user_profile.strava_url or "",
        "auth_until": user_profile.strava_auth_until or 0,
    }


@flask_app.route("/strava/api-developer")
def strava_api_developer():
    """Strava home page with authentication data and/or Strava profile.

    Control flow:

    * home page is rendered:
      - UNKNOWN whether user is authenticated with Strava
        - visible buttons: Edit (to set client ID and secret), Authenticate
        - hidden buttons: Synchronize, Sync Last
        - https://www.strava.com/api/v3/athlete
          - try to get athlete profile to find out whether user is authenticated
            - profile image
            - ...
      - KNOWN that user is authenticated with Strava (timeout did not expire)
        - ...

    """
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    # TODO improve: get epoch time, normalize it to Strava epoch time and compare
    is_auth, is_auth_valid = strava.is_access_token_valid(user_profile=user_profile)

    # TODO check whether access token is valid, if not use REFRESH token to get
    #   it automatically

    return flask.render_template(
        "strava-api-developer.html",
        ff=ff,
        user_profile=user_profile,
        is_auth=is_auth,
        is_auth_valid=is_auth_valid,
        sync_locked=False,
    )


@flask_app.route("/strava/api-secrets", methods=["GET", "POST"])
def strava_api_secrets():
    """Page to set (or clear) the encrypted Strava API client credentials."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    form = forms.StravaSecretsForm()

    if flask.request.method == "POST":
        if form.validate_on_submit():
            user_profile.strava_client_id = form.client_id.data.strip()
            user_profile.strava_client_secret = form.client_secret.data.strip()
            ds.update_profile(user_profile)
            flask.flash(
                message="Strava API secrets saved successfully.", category="success"
            )
            return flask.redirect(flask.url_for("strava_api_developer"))

        flask.flash(
            message="Strava secrets error - check the form fields.", category="error"
        )
        return flask.render_template(
            "strava-api-secrets.html",
            user_profile=user_profile,
            form=form,
        )

    # GET - never pre-fill form with secret values
    return flask.render_template(
        "strava-api-secrets.html",
        user_profile=user_profile,
        form=form,
    )


@flask_app.route("/strava/api-secrets/reset")
def strava_api_secrets_reset():
    """Clear both Strava API client credentials."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    user_profile.strava_client_id = ""
    user_profile.strava_client_secret = ""
    ds.update_profile(user_profile)

    flask.flash(message="Strava API secrets cleared.", category="success")
    return flask.redirect(flask.url_for("strava_api_developer"))


@flask_app.route("/strava/auth-start")
def strava_auth_start():
    """Start the Strava API authentication."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    # ask mentor for guidance what to do
    advice, msg = strava.ask_mentor(user_profile)
    if strava.AuthMentorAdvice.CONFIGURE == advice:
        flask.flash(
            message="Configure Strava - set client ID and client secret",
            category="info",
        )
        return flask.redirect(flask.url_for("strava_api_secrets"))

    match advice:
        case strava.AuthMentorAdvice.GET_REFRESH_TOKEN:
            # get URL from Strava service to be used for auth (includes auth token)
            flask.flash(message=msg, category="info")
            url = strava.auth_get_auth_code_url(
                user_profile=user_profile,
                mytral_url=f"{flask.request.host_url}{strava.URL_AUTH_CALLBACK}",
            )
            return flask.redirect(url)
        case strava.AuthMentorAdvice.USE_REFRESH_TOKEN:
            flask.flash(message=msg, category="info")
            # user refresh token to get access token
            updated_user_profile = strava.auth_get_access_for_refresh_token(
                user_profile=user_profile, logger=app_logger
            )
            ds.update_profile(updated_user_profile)
            return flask.redirect(flask.url_for("strava_api_developer"))
        case strava.AuthMentorAdvice.NO_OP_AUTHENTICATED:
            # nothing to do > return back to home
            return flask.redirect(flask.url_for("strava_api_developer"))

    # else fail
    flask.flash(
        message=f"Strava authentication error: unknown mentor advice '{advice}'",
        category="error",
    )
    return flask.redirect(flask.url_for("strava_api_developer"))


@flask_app.route("/strava/auth-reset")
def strava_auth_reset():
    """Reset access and refresh tokens."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    # purge Strava tokens
    user_profile.strava_access_token = ""
    user_profile.strava_auth_until = 0
    user_profile.strava_auth_until_str = ""
    user_profile.strava_refresh_token = ""
    user_profile.strava_code = ""

    ds.update_profile(user_profile)

    return flask.redirect(flask.url_for("strava_api_developer"))


# TODO callback for ALL vs. LAST synchronization
@flask_app.route(f"/{strava.URL_AUTH_CALLBACK}")
def strava_auth_redirect():
    """Strava OAuth2 redirect which has authentication token in the parameters."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    auth_code = flask.request.args.get("code")
    if not auth_code:
        flask.flash(
            message="Strava authentication error: authentication code is missing",
            category="error",
        )
        return flask.redirect(flask.url_for("strava_api_developer"))

    user_profile = ds.profile(user_id)
    user_profile.strava_code = str(auth_code)

    auth_scope = flask.request.args.get("scope")
    if not auth_scope:
        flask.flash(
            message="Strava authentication error: auth scope is missing",
            category="error",
        )
        return flask.redirect(flask.url_for("strava_api_developer"))
    user_profile.strava_scope = str(auth_scope)
    ds.update_profile(user_profile)

    strava.auth_get_n_set_auth_token(
        user_profile=user_profile, ds=ds, logger=app_logger
    )

    #
    # SYNCHRONIZE
    #

    # TODO start the synchronization process: last vs. all is differentiated by
    #  CALLBACK passed in the previous call

    # TODO strava.export_json_from_strava_service(user_profile=user_profile)

    return flask.redirect(flask.url_for("strava_api_developer"))


@flask_app.route("/strava/synchronization/new/new")
def strava_sync_new_to_new():
    """Synchronize ONLY NEW activities from Strava service."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)

    ds.cache_evict(user_id)

    # find out the timestamp of the last activity
    ds_stats = ds.activities_stats(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
    )
    last_activity_ts = ds_stats.ts_max

    # export activities in Strava's JSON format
    strava_activities: list = strava.export_json_from_strava_service(
        user_profile=user_profile,
        after_timestamp=last_activity_ts,
        logger=app_logger,
    )

    # concert Strava JSON to MyTraL JSON
    if strava_activities:
        t_plugin = strava.StravaActivitiesImportPlugin
        activities_plugin: t_plugin = plugins.registry.get_plugin(t_plugin.NAME)
        new_activities = activities_plugin.import_activities(
            datasets={t_plugin.USE_TYPE_STRAVA_LIST: strava_activities},
            user_profile=user_profile,
            gear=ds.list_gear(user_id=user_id, dataset_name=user_profile.dataset_name),
        )
        # create new dataset
        new_dataset_name = persistences.create_ts_filename(prefix="strava-export")
        ds.create_activities_dataset(user_id=user_id, dataset_name=new_dataset_name)
        ds.update_activities(
            user_id=user_id, dataset_name=new_dataset_name, activities=new_activities
        )
        # switch to the new dataset
        user_profile.add_dataset(new_dataset_name)
        user_profile.dataset_name = new_dataset_name
        ds.update_profile(user_id)

    return flask.redirect(flask.url_for("home"))


@flask_app.route("/strava/synchronization/new/current", methods=["GET", "POST"])
@flask_app.route("/strava/sync/new-to-current", methods=["POST"])
def strava_sync_new_to_current():
    """Start async task to synchronize new activities from Strava."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    user_profile = ds.profile(user_id)
    dataset_name = user_profile.dataset_name

    # get timestamp of last activity
    ds_stats = ds.activities_stats(
        user_id=user_id,
        dataset_name=dataset_name,
        activities=ds.list_activities(user_id=user_id, dataset_name=dataset_name),
        include_meta=False,
    )
    after_ts = ds_stats.ts_max if ds_stats else 0

    task_params = _build_strava_task_params(user_id, dataset_name, after_ts)
    if task_params is None:
        return flask.redirect(flask.url_for("strava_auth_start"))

    task = tasks.TaskEntity(
        key=str(uuid.uuid4()),
        user_id=str(user_id),
        task_type="strava_sync_new_to_current",
        status=tasks.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters=task_params,
    )

    try:
        flask_app.task_manager.executor.submit(task)
        flask.flash("Strava sync started - check Tasks for progress.", "success")
    except Exception as exc:
        flask.flash(f"Could not start sync: {exc}", "danger")

    return flask.redirect(flask.url_for("tasks_list"))


@flask_app.route("/strava/synchronization/gear", methods=["GET", "POST"])
@flask_app.route("/strava/sync/gear", methods=["POST"])
def strava_sync_gear():
    """Start async task to sync gear from Strava."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)
    dataset_name = user_profile.dataset_name

    enc_key = app_config.encryption_key
    is_auth, is_auth_valid = strava.is_access_token_valid(user_profile)
    if not is_auth or not is_auth_valid:
        return flask.redirect(flask.url_for("strava_auth_start"))

    task_params = {
        "user_id": user_id,
        "dataset_name": dataset_name,
        "access_token": security.encrypt(
            user_profile.strava_access_token or "", enc_key
        ),
        "client_id": user_profile.strava_client_id or "",
        "client_secret": security.encrypt(
            user_profile.strava_client_secret or "", enc_key
        ),
        "strava_url": user_profile.strava_url or "",
    }

    task = tasks.TaskEntity(
        key=str(uuid.uuid4()),
        user_id=str(user_id),
        task_type="strava_sync_gear",
        status=tasks.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters=task_params,
    )

    try:
        flask_app.task_manager.executor.submit(task)
        flask.flash("Gear sync started - check Tasks for progress.", "success")
    except Exception as exc:
        flask.flash(f"Could not start gear sync: {exc}", "danger")

    return flask.redirect(flask.url_for("tasks_list"))


@flask_app.route("/strava/synchronization/all", methods=["GET", "POST"])
@flask_app.route("/strava/sync/resync-all", methods=["POST"])
def strava_sync_all():
    """Start async task to re-sync all Strava activities (purge + reimport)."""
    user = flask.session.get(COOKIE_USER)
    if not user:
        return flask.redirect(flask.url_for("login"))

    # safety: require explicit confirmation
    purge_confirmed = flask.request.form.get("purge_confirmed", "0") == "1"
    if not purge_confirmed:
        flask.flash(
            "Re-sync requires explicit confirmation. "
            "Use the confirmation button on the Strava page.",
            "warning",
        )
        return flask.redirect(flask.url_for("strava_api_developer"))

    user_id = user
    user_profile = ds.profile(user_id)
    dataset_name = user_profile.dataset_name

    task_params = _build_strava_task_params(user_id, dataset_name, after_ts=0)
    if task_params is None:
        return flask.redirect(flask.url_for("strava_auth_start"))

    task_params["purge_confirmed"] = True

    task = tasks.TaskEntity(
        key=str(uuid.uuid4()),
        user_id=str(user_id),
        task_type="strava_resync_all",
        status=tasks.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters=task_params,
    )

    try:
        flask_app.task_manager.executor.submit(task)
        flask.flash("Full re-sync started - check Tasks for progress.", "success")
    except Exception as exc:
        flask.flash(f"Could not start re-sync: {exc}", "danger")

    return flask.redirect(flask.url_for("tasks_list"))
