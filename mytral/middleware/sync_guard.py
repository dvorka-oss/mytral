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
"""Sync guard middleware - blocks writes while an activities sync is in progress."""

import flask

import mytral
from mytral import forms

# HTTP methods that modify data
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# URL prefix -> resource key template.
#
# Using URL prefixes instead of endpoint names is intentional: endpoint names are
# internal Python identifiers that silently drift as code is refactored, while URL
# prefixes are the stable public contract of the application.  Any new write route
# added under a guarded prefix is automatically protected without touching this file.
#
# Order matters: more-specific prefixes must come before shorter ones so that the
# first match wins (though currently no prefix is a prefix of another).
_WRITE_URL_RESOURCES: list[tuple[str, str]] = [
    # activity data - all create/update/delete/copy/clone routes
    ("/app/activities", "user_{user_id}_activities"),
    ("/activities/", "user_{user_id}_activities"),
    # gear and gear-component data
    ("/settings/gears", "user_{user_id}_gear"),
    # goals and activity-type definitions affect activity dataset integrity
    ("/settings/goals", "user_{user_id}_activities"),
    ("/settings/activity-types", "user_{user_id}_activities"),
]


def _resource_for_path(path: str) -> str | None:
    """Return the resource key template matching *path*, or ``None``.

    Parameters
    ----------
    path : str
        URL path of the current request (``flask.request.path``).

    Returns
    -------
    str | None
        Resource key template string, or ``None`` when the path is not guarded.
    """
    for prefix, resource_template in _WRITE_URL_RESOURCES:
        if path == prefix or path.startswith(prefix + "/"):
            return resource_template
    return None


def is_user_syncing(app, user_id: str) -> bool:
    """Check if any task is currently running for a user.

    Parameters
    ----------
    app : Flask
        Flask application instance.
    user_id : str
        User identifier.

    Returns
    -------
    bool
        True if a task is running (account is in read-only mode).
    """
    if not hasattr(app, "task_manager"):
        return False
    return app.task_manager.lock_manager.is_locked(user_id)


def register_sync_guard(app) -> None:
    """Register the sync guard before_request hook on a Flask app.

    Parameters
    ----------
    app : Flask
        Flask application instance.
    """

    @app.before_request
    def sync_guard():
        """Block write operations while a sync task holds the resource lock."""
        if flask.request.method not in _WRITE_METHODS:
            return None

        from mytral import routes as routes_module

        user_id = flask.session.get(routes_module.COOKIE_USER)
        if not user_id:
            return None

        resource_template = _resource_for_path(flask.request.path)
        if not resource_template:
            return None

        if not hasattr(app, "task_manager"):
            return None

        if app.task_manager.lock_manager.is_locked(user_id):
            # find the active task and the user profile for the template
            active_task_id = None
            user_profile = None
            cancel_form = None
            try:
                from mytral.tasks import _entities as task_entities

                tasks = app.task_manager.executor.get_all_tasks(user_id)
                for t in tasks:
                    if t.status == task_entities.TaskStatus.RUNNING:
                        active_task_id = t.key
                        break
            except Exception:
                pass

            try:
                user_profile = mytral.app_user_ds.profile(user_id)
                cancel_form = forms.CancelTaskForm()
            except Exception:
                pass

            return (
                flask.render_template(
                    "sync-locked.html",
                    active_task_id=active_task_id,
                    user_profile=user_profile,
                    cancel_form=cancel_form,
                ),
                423,
            )
        return None


def inject_sync_status(app) -> None:
    """Register a context processor that injects sync_locked into all templates.

    Parameters
    ----------
    app : Flask
        Flask application instance.
    """

    @app.context_processor
    def _sync_status():
        from mytral import routes as routes_module

        user_id = flask.session.get(routes_module.COOKIE_USER)
        if not user_id:
            return {"sync_locked": False}
        return {"sync_locked": is_user_syncing(app, user_id)}
