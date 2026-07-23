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

"""Polar Flow (AccessLink API + GDPR export) URI space."""

import datetime
import uuid

import flask

from mytral import app_config
from mytral import app_logger
from mytral import app_task_manager
from mytral import app_user_ds as ds
from mytral import ff
from mytral import forms
from mytral import persistences
from mytral import security
from mytral import tasks
from mytral.integrations import polar_flow
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app
from mytral.tasks.do import polar_flow_export_import
from mytral.tasks.do import polar_flow_resync_all
from mytral.tasks.do import polar_flow_sync


def _guard(user_id: str | None):
    """Return a redirect response when access is not allowed, else ``None``."""
    if not user_id:
        return flask.redirect(flask.url_for("login"))
    return None


def _auth_callback_url() -> str:
    """Return the OAuth2 redirect URL of this MyTraL instance.

    Single source of truth: Polar rejects the token exchange unless the redirect
    URL sent there is identical to the one sent to the authorization endpoint.
    """
    return f"{flask.request.host_url}{polar_flow.URL_AUTH_CALLBACK}"


def _build_polar_task_params(
    user_id: str,
    dataset_name: str,
    import_recordings: bool = True,
) -> dict | None:
    """Build encrypted Polar Flow sync task params, or None if unauthenticated."""
    user_profile = ds.profile(user_id)
    if not polar_flow.is_authenticated(user_profile):
        return None

    # Polar access tokens do not expire and there is no refresh token, so the task
    # only needs the token + user id (no client id/secret).
    enc_key = app_config.encryption_key
    return {
        "user_id": user_id,
        "dataset_name": dataset_name,
        "import_recordings": import_recordings,
        "access_token": security.encrypt(
            user_profile.polar_flow_access_token or "", enc_key
        ),
        "polar_user_id": user_profile.polar_flow_user_id or "",
    }


def _submit(task_entity: tasks.TaskEntity, ok_msg: str, err_msg: str):
    """Submit a task and flash the outcome; return a redirect to the task list."""
    try:
        app_task_manager.executor.submit(task_entity)
        flask.flash(ok_msg, "success")
    except Exception as exc:
        app_logger.exception(
            "Polar Flow task submit failed",
            exc_info=True,
            error=str(exc),
            task_key=task_entity.key,
            user_id=task_entity.user_id,
        )
        flask.flash(f"{err_msg}: {exc}", "danger")
    return flask.redirect(flask.url_for("tasks_list"))


@flask_app.route("/polar/api-developer")
def polar_flow_api_developer():
    """Polar Flow developer dashboard - auth state and sync actions."""
    user_id = flask.session.get(COOKIE_USER)
    guard = _guard(user_id)
    if guard:
        return guard
    user_profile = ds.profile(user_id)
    return flask.render_template(
        "polar-flow-developer.html",
        ff=ff,
        user_profile=user_profile,
        is_authenticated=polar_flow.is_authenticated(user_profile),
    )


@flask_app.route("/polar/api-secrets", methods=["GET", "POST"])
def polar_flow_api_secrets():
    """Set (or clear) the encrypted Polar Flow API client credentials."""
    user_id = flask.session.get(COOKIE_USER)
    guard = _guard(user_id)
    if guard:
        return guard
    user_profile = ds.profile(user_id)
    form = forms.PolarFlowSecretsForm()

    if flask.request.method == "POST" and form.validate_on_submit():
        user_profile.polar_flow_client_id = form.client_id.data.strip()
        user_profile.polar_flow_client_secret = form.client_secret.data.strip()
        ds.update_profile(user_profile)
        flask.flash("Polar Flow API secrets saved successfully.", "success")
        return flask.redirect(flask.url_for("polar_flow_api_developer"))

    if flask.request.method == "POST":
        flask.flash("Polar Flow secrets error - check the form fields.", "error")

    return flask.render_template(
        "polar-flow-secrets.html",
        user_profile=user_profile,
        form=form,
    )


@flask_app.route("/polar/api-secrets/reset", methods=["POST"])
def polar_flow_api_secrets_reset():
    """Clear the Polar Flow API client credentials."""
    user_id = flask.session.get(COOKIE_USER)
    guard = _guard(user_id)
    if guard:
        return guard
    user_profile = ds.profile(user_id)
    user_profile.polar_flow_client_id = ""
    user_profile.polar_flow_client_secret = ""
    ds.update_profile(user_profile)
    flask.flash("Polar Flow API secrets cleared.", "success")
    return flask.redirect(flask.url_for("polar_flow_api_developer"))


@flask_app.route("/polar/auth-start")
def polar_flow_auth_start():
    """Start the Polar Flow OAuth2 authentication."""
    user_id = flask.session.get(COOKIE_USER)
    guard = _guard(user_id)
    if guard:
        return guard
    user_profile = ds.profile(user_id)

    advice, msg = polar_flow.ask_mentor(user_profile)
    if advice == polar_flow.AuthMentorAdvice.CONFIGURE:
        flask.flash("Configure Polar Flow - set client ID and client secret", "info")
        return flask.redirect(flask.url_for("polar_flow_api_secrets"))
    if advice == polar_flow.AuthMentorAdvice.AUTHENTICATED:
        return flask.redirect(flask.url_for("polar_flow_api_developer"))
    if advice == polar_flow.AuthMentorAdvice.REGISTER_USER:
        # token present but the user is not linked yet - just register, no re-OAuth
        try:
            polar_flow.register_user(
                user_profile=user_profile, ds=ds, logger=app_logger
            )
            flask.flash("Polar Flow account linked.", "success")
        except Exception as exc:
            app_logger.exception(
                "Polar Flow user registration failed",
                exc_info=True,
                error=str(exc),
                user_id=user_id,
            )
            flask.flash(f"Polar Flow registration failed: {exc}", "danger")
        return flask.redirect(flask.url_for("polar_flow_api_developer"))

    # advice == AUTHENTICATE: no token yet - start the OAuth2 flow
    flask.flash(msg, "info")
    url = polar_flow.auth_get_auth_code_url(
        user_profile=user_profile,
        mytral_url=_auth_callback_url(),
    )
    return flask.redirect(url)


@flask_app.route(f"/{polar_flow.URL_AUTH_CALLBACK}")
def polar_flow_auth_redirect():
    """Polar OAuth2 redirect - exchange the code for a token and link the user."""
    user_id = flask.session.get(COOKIE_USER)
    guard = _guard(user_id)
    if guard:
        return guard

    auth_code = flask.request.args.get("code")
    if not auth_code:
        flask.flash("Polar Flow authentication error: code is missing", "error")
        return flask.redirect(flask.url_for("polar_flow_api_developer"))

    user_profile = ds.profile(user_id)
    try:
        polar_flow.auth_exchange_code_for_token(
            user_profile=user_profile,
            code=str(auth_code),
            mytral_url=_auth_callback_url(),
            ds=ds,
            logger=app_logger,
        )
        polar_flow.register_user(user_profile=user_profile, ds=ds, logger=app_logger)
        flask.flash("Polar Flow authenticated successfully.", "success")
    except Exception as exc:
        app_logger.exception(
            "Polar Flow authentication failed",
            exc_info=True,
            error=str(exc),
            user_id=user_id,
        )
        flask.flash(f"Polar Flow authentication failed: {exc}", "danger")

    return flask.redirect(flask.url_for("polar_flow_api_developer"))


@flask_app.route("/polar/auth-reset", methods=["POST"])
def polar_flow_auth_reset():
    """Reset the Polar Flow access token and user link."""
    user_id = flask.session.get(COOKIE_USER)
    guard = _guard(user_id)
    if guard:
        return guard
    user_profile = ds.profile(user_id)
    user_profile.polar_flow_access_token = ""
    user_profile.polar_flow_user_id = ""
    ds.update_profile(user_profile)
    return flask.redirect(flask.url_for("polar_flow_api_developer"))


@flask_app.route("/polar/sync/new", methods=["POST"])
def polar_flow_sync_new():
    """Start an async task to sync new Polar Flow activities."""
    user_id = flask.session.get(COOKIE_USER)
    guard = _guard(user_id)
    if guard:
        return guard
    user_profile = ds.profile(user_id)

    task_params = _build_polar_task_params(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        import_recordings=flask.request.form.get("import_recordings", "1") == "1",
    )
    if task_params is None:
        return flask.redirect(flask.url_for("polar_flow_auth_start"))

    task = tasks.TaskEntity(
        key=str(uuid.uuid4()),
        user_id=str(user_id),
        task_type=polar_flow_sync.PolarFlowSyncTask.TASK_TYPE,
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
    return _submit(
        task,
        ok_msg="Polar Flow sync started - check Tasks.",
        err_msg="Could not start sync",
    )


@flask_app.route("/polar/sync/resync-all", methods=["POST"])
def polar_flow_resync_all_route():
    """Start an async task to re-sync all Polar Flow activities (purge + re-pull)."""
    user_id = flask.session.get(COOKIE_USER)
    guard = _guard(user_id)
    if guard:
        return guard

    if flask.request.form.get("purge_confirmed", "0") != "1":
        flask.flash(
            "Re-sync requires explicit confirmation via the confirmation button.",
            "warning",
        )
        return flask.redirect(flask.url_for("polar_flow_api_developer"))

    user_profile = ds.profile(user_id)
    task_params = _build_polar_task_params(
        user_id=user_id,
        dataset_name=user_profile.dataset_name,
        import_recordings=flask.request.form.get("import_recordings", "1") == "1",
    )
    if task_params is None:
        return flask.redirect(flask.url_for("polar_flow_auth_start"))
    task_params["purge_confirmed"] = True

    task = tasks.TaskEntity(
        key=str(uuid.uuid4()),
        user_id=str(user_id),
        task_type=polar_flow_resync_all.PolarFlowResyncAllTask.TASK_TYPE,
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
    return _submit(
        task,
        ok_msg="Polar Flow re-sync started - check Tasks.",
        err_msg="Could not start re-sync",
    )


@flask_app.route("/polar/import/export-zip", methods=["POST"])
def polar_flow_import_export_zip():
    """Upload a Polar Flow GDPR export ZIP and start the historical import task."""
    user_id = flask.session.get(COOKIE_USER)
    guard = _guard(user_id)
    if guard:
        return guard
    user_id = str(user_id)
    user_profile = ds.profile(user_id)

    form = forms.ImportPolarFlowExportForm()
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for error in field_errors:
                flask.flash(error, "warning")
        return flask.redirect(flask.url_for("tool_import"))

    # persist the uploaded ZIP into the user's work directory
    user_work_dir = persistences.create_user_work(ds.user_dir(user_id=user_id))
    zip_path = user_work_dir / f"{uuid.uuid4()}-polar-flow-export.zip"
    form.archive.data.save(str(zip_path))

    task = tasks.TaskEntity(
        key=str(uuid.uuid4()),
        user_id=user_id,
        task_type=polar_flow_export_import.PolarFlowExportImportTask.TASK_TYPE,
        status=tasks.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters={
            "user_id": user_id,
            "dataset_name": user_profile.dataset_name,
            "zip_path": str(zip_path),
            "on_conflict": form.on_conflict.data,
        },
    )
    return _submit(
        task,
        ok_msg="Polar Flow export import started - check Tasks.",
        err_msg="Could not start export import",
    )
