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

import uuid

import flask

import mytral
from mytral import app_user_ds as ds
from mytral.routes import COOKIE_USER
from mytral.routes import flask_app


@flask_app.route("/app/tools/activities/export")
def tool_export_activities():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    return flask.render_template("tools-export.html", user_profile=ds.profile(user_id))


@flask_app.route("/app/tools/activities/export/json")
def tool_export_activities_json():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    return ds.export_activities(
        user_id=user_id, dataset_name=ds.profile(user_id).dataset_name
    )


@flask_app.route("/app/tools/activities/export/zip")
def tool_export_profile_zip():
    user_id = flask.session.get(COOKIE_USER)
    if not user_id:
        return flask.redirect(flask.url_for("login"))

    zip_name = f"{user_id}_{uuid.uuid4()}.zip"
    download_dir = mytral.app_config.user_data_dir / "download"
    download_dir.mkdir(parents=True, exist_ok=True)
    zip_path = download_dir / zip_name

    # export all user data in as ZIP archive
    ds.export(user_id=user_id, archive_path=zip_path, export_format="zip")

    return flask.send_file(zip_path, as_attachment=True)
