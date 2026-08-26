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

"""Tests for the gear update route recomputing component service intervals.

The gear update page (``/settings/gears/<key>/update``) renders the same
component usage cards as the gear detail page (``/settings/gears/<key>/get``),
so it must call ``recompute_gear_service_intervals`` too. Without it, a
component's ``distance_meters``/``time_seconds`` shown on that page are
whatever was last persisted - e.g. zeroed out at creation time for a new
component that replaced an older one - instead of the actual usage derived
from activity records.
"""

from types import SimpleNamespace

import flask
import pytest

from mytral.blueprints import gear_crud


@pytest.mark.mytral
def test_settings_gear_update_get_recomputes_component_service_intervals(
    monkeypatch,
):
    # GIVEN a gear whose components have stale/uncomputed usage snapshots
    class _Gear:
        key = "gear-1"
        activity_type_key = "cycling"
        name = "Bike"
        vendor = ""
        model = ""
        size = ""
        weight = 0.0
        comment = ""
        url = ""
        retired = False
        is_default = False
        tcoo_base = 0.0
        tcoo_additional = 0.0
        purchased = ""

    class _ActivityTypes:
        def choices(self):
            return [("cycling", "Cycling")]

    profile = SimpleNamespace(dataset_name="default")
    gear = _Gear()
    recompute_calls = []

    monkeypatch.setattr(
        gear_crud.ds, "get_gear", lambda user_id, key, dataset_name: gear
    )
    monkeypatch.setattr(gear_crud.ds, "profile", lambda user_id: profile)
    monkeypatch.setattr(
        gear_crud.ds, "list_activity_types", lambda user_id: _ActivityTypes()
    )
    monkeypatch.setattr(
        gear_crud.ds,
        "recompute_gear_service_intervals",
        lambda **kwargs: recompute_calls.append(kwargs),
    )
    monkeypatch.setattr(flask, "render_template", lambda *args, **kwargs: "ok")

    with gear_crud.flask_app.test_request_context(
        "/settings/gears/gear-1/update", method="GET"
    ):
        flask.session[gear_crud.COOKIE_USER] = "user-1"

        # WHEN
        gear_crud.settings_gear_update("gear-1")

    # THEN - DONE: recompute ran against the fetched gear before rendering,
    # same as the gear get route, so component usage is never stale
    assert len(recompute_calls) == 1
    assert recompute_calls[0] == {
        "user_id": "user-1",
        "dataset_name": "default",
        "gear": gear,
    }
    print("DONE: gear update page recomputes component service intervals")
