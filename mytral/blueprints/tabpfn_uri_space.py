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
"""TabPFN / ICL model settings routes.

Provides:
  GET  /app/settings/tabpfn          - settings page
  POST /app/settings/tabpfn/update   - save user ICL preference toggles
  POST /app/settings/tabpfn/download - start background weight download
  POST /app/settings/tabpfn/delete   - delete cached weights
  GET  /app/settings/tabpfn/status   - JSON status poll endpoint
"""

import datetime
import uuid

import flask
import structlog

from mytral import app_task_manager
from mytral import app_user_ds as ds
from mytral.ml.icl import manager as icl_manager
from mytral.ml.icl import settings as icl_settings
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app
from mytral.tasks import _entities as task_entities
from mytral.tasks import executor as task_executor
from mytral.tasks.do import tabpfn_download as tabpfn_download_task

_logger = structlog.get_logger()


#
# Settings page
#


@flask_app.route("/app/settings/tabpfn", methods=["GET"])
def settings_tabpfn():
    """Render the TabPFN / ICL model settings page."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)
    model_status = icl_manager.get_status()
    info = icl_manager.storage_info()
    error = icl_manager.get_last_error()

    return flask.render_template(
        "settings-tabpfn.html",
        user_profile=user_profile,
        model_status=model_status,
        storage_info=info,
        last_error=error,
        STATUS_NOT_INSTALLED=icl_settings.MODEL_STATUS_NOT_INSTALLED,
        STATUS_NOT_DOWNLOADED=icl_settings.MODEL_STATUS_NOT_DOWNLOADED,
        STATUS_DOWNLOADING=icl_settings.MODEL_STATUS_DOWNLOADING,
        STATUS_DOWNLOADED=icl_settings.MODEL_STATUS_DOWNLOADED,
        STATUS_FAILED=icl_settings.MODEL_STATUS_FAILED,
    )


#
# Update preferences
#


@flask_app.route("/app/settings/tabpfn/update", methods=["POST"])
def settings_tabpfn_update():
    """Save user ICL preference toggles."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    user_profile = ds.profile(user_id)

    # server-side guard: master switch may only be enabled when weights are ready.
    # The UI disables the checkbox in that state, but we enforce it here too so that
    # a crafted POST cannot bypass the UI restriction.
    enabled = flask.request.form.get("enabled") == "on"
    if enabled and not icl_manager.is_weights_cached():
        enabled = False
        flask.flash(
            "TabPFN predictions cannot be enabled until model weights are downloaded.",
            "warning",
        )

    enable_illness_risk = flask.request.form.get("enable_illness_risk") == "on"
    enable_fatigue = flask.request.form.get("enable_fatigue") == "on"
    enable_performance = flask.request.form.get("enable_performance") == "on"
    enable_rest_day = flask.request.form.get("enable_rest_day") == "on"
    enable_anomaly = flask.request.form.get("enable_anomaly") == "on"

    user_profile.icl_settings = icl_settings.IclSettings(
        enabled=enabled,
        enable_illness_risk=enable_illness_risk,
        enable_fatigue=enable_fatigue,
        enable_performance=enable_performance,
        enable_rest_day=enable_rest_day,
        enable_anomaly=enable_anomaly,
    )
    ds.update_profile(user_profile)

    flask.flash("TabPFN settings saved.", "success")
    return flask.redirect(flask.url_for("settings_tabpfn"))


#
# Model download
#


@flask_app.route("/app/settings/tabpfn/download", methods=["POST"])
def settings_tabpfn_download():
    """Submit a TabPFN weight download task to the task queue."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if not icl_manager.is_tabpfn_installed():
        flask.flash(
            "TabPFN package is not installed. "
            "Install the 'ml' dependency group first: "
            "<code>uv sync --group ml</code>.",
            "warning",
        )
        return flask.redirect(flask.url_for("settings_tabpfn"))

    if icl_manager.is_weights_cached():
        flask.flash("Model weights are already downloaded.", "info")
        return flask.redirect(flask.url_for("settings_tabpfn"))

    task = task_entities.TaskEntity(
        key=str(uuid.uuid4()),
        user_id=user_id,
        task_type=tabpfn_download_task.TASK_TYPE,
        status=task_entities.TaskStatus.QUEUED,
        created_at=datetime.datetime.now(),
        started_at=None,
        completed_at=None,
        error_message=None,
        error_type=None,
        error_traceback=None,
        progress=0,
        parameters={},
    )

    try:
        app_task_manager.executor.submit(task)
        flask.flash(
            "TabPFN weight download started — follow progress in Tasks.",
            "success",
        )
        _logger.info(
            "tabpfn: weight download task submitted", user=user_id, task_id=task.key
        )
    except task_executor.ResourceLockError:
        flask.flash(
            "Another task is already running for your account. "
            "Please wait for it to finish.",
            "warning",
        )
    except Exception as exc:
        flask.flash(f"Could not start download: {exc}", "danger")

    return flask.redirect(flask.url_for("tasks_list"))


#
# Delete weights
#


@flask_app.route("/app/settings/tabpfn/delete", methods=["POST"])
def settings_tabpfn_delete():
    """Delete locally cached TabPFN v2 model weights."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    deleted = icl_manager.delete_weights()
    if deleted:
        flask.flash("Model weights deleted.", "success")
        _logger.info("tabpfn: weights deleted from settings page", user=user_id)
    else:
        flask.flash("No cached weights found.", "info")

    return flask.redirect(flask.url_for("settings_tabpfn"))


#
# JSON status poll
#


@flask_app.route("/app/settings/tabpfn/status", methods=["GET"])
def settings_tabpfn_status():
    """Return JSON with current model status for client-side polling."""
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.jsonify({"error": "unauthorized"}), 401

    return flask.jsonify(
        {
            "status": icl_manager.get_status(),
            "storage_info": icl_manager.storage_info(),
            "last_error": icl_manager.get_last_error(),
        }
    )
