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
import os

import flask

from mytral import app_config
from mytral import app_user_ds as ds
from mytral import ff
from mytral import forms
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app


@flask_app.route("/deployment", methods=["GET"])
def deployment():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    if not ds.profile(user_id).admin:
        flask.abort(403)

    if flask.request.method == "GET":
        form = forms.SettingsForm()
        form.data_files.choices = [(f, f) for f in ds.profile(user_id).dataset_names]
        form.data_files.default = ds.profile(user_id).dataset_name
        form.data_files.process(form.data_files.default)

        return flask.render_template(
            "deployment.html",
            ff=ff,
            user_profile=ds.profile(user_id),
            deployment_attrs={
                "instance_id": app_config.instance_id,
                "host": flask.request.host,
                "url": flask.request.url,
                "persistence_type": app_config.persistence_type,
                "persistence_data_dir": app_config.persistence_data_dir,
                "auto_account_creation": app_config.auto_account_creation,
                "user_registration": app_config.user_registration,
                "mytral_cache": app_config.persistence_cache,
                "cors_origins": app_config.cors_origins,
                "flask_debug_mode": app_config.debug,
                "flask_signing_key": "(set)" if app_config.signing_key else "(empty)",
                "encryption_key": "(set)" if app_config.encryption_key else "(empty)",
                "env_vars": dict(
                    sorted(
                        {
                            k: v
                            for k, v in os.environ.items()
                            if not any(
                                sensitive in k.upper()
                                for sensitive in (
                                    "SECRET",
                                    "PASSWORD",
                                    "PASSWD",
                                    "TOKEN",
                                    "KEY",
                                    "CREDENTIAL",
                                    "AUTH",
                                    "PRIVATE",
                                    "STRAVA",
                                    "URL",
                                    "DSN",
                                )
                            )
                        }.items()
                    )
                ),
            },
        )

    else:
        flask.flash(
            message=f"Settings error - unsupported method: {flask.request.method}",
            category="error",
        )
        return flask.redirect(flask.url_for("home"))
