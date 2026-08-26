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

"""Tests for the component "Usage" stat card rendered by
``macros/gear_components.html``.

A component that is replaced in place (same component, a "replacement" entry
added to its service history) keeps its original ``installed_date`` and stays
``active`` - it is not retired and no new component is created for it. Its
"Usage" card must therefore show usage since the last service/replacement
event, not the component's full lifetime since its original install date,
or it silently displays the predecessor part's mileage as if it belonged to
the part currently mounted.
"""

import jinja2
import pytest

from mytral import settings
from mytral.routes import flask_app

_RENDER_STATS_CARDS = (
    "{% from 'macros/gear_components.html' import comp_stats_cards %}"
    "{{ comp_stats_cards(comp, gear, is_retired=is_retired) }}"
)


def _render_stats_cards(comp, gear, is_retired):
    # a private Environment (same template loader, own template cache) avoids
    # polluting flask_app.jinja_env's cached macro module - Jinja caches a
    # template's "default module" (used by plain {% from %} imports) keyed
    # only by global *names*, not values, so whichever test renders this
    # macro file first freezes its url_for closure for the rest of the
    # session; other macros in this file do call url_for, comp_stats_cards
    # doesn't, but sharing the app's environment would still risk it
    env = jinja2.Environment(loader=flask_app.jinja_loader, autoescape=True)
    template = env.from_string(_RENDER_STATS_CARDS)
    return template.render(comp=comp, gear=gear, is_retired=is_retired)


@pytest.mark.mytral
def test_active_component_usage_card_shows_usage_since_last_service():
    # GIVEN an active component installed long ago, then replaced in place via
    # a service history "replacement" entry - distance/time accumulated since
    # the ORIGINAL install, last_service_km/hours captured at that event
    component = settings.GearComponent(
        name="tire (front)",
        installed_date="2026-07-28",
        distance_meters=956_934,  # 956.9 km since the original install
        time_seconds=141_440,  # 39.3 h since the original install
        last_service_km=812.212,  # km at the last replacement event
        last_service_hours=34.1275,  # hours at the last replacement event
        status="active",
    )
    gear = settings.Gear(
        activity_type_key="ride", name="Bike", components=[component.to_dict()]
    )

    # WHEN
    html = _render_stats_cards(component, gear, is_retired=False)

    normalized = " ".join(html.split())

    # THEN - DONE: usage since the last replacement (957 - 812 = ~145 km),
    # not the component's full lifetime since its original install (957 km)
    assert "145 km" in normalized
    assert "5.2 h" in normalized
    assert "957 km" not in normalized
    assert "39.3 h" not in normalized
    print("DONE: active component Usage card reflects usage since last service")


@pytest.mark.mytral
def test_retired_component_usage_card_shows_full_lifetime_usage():
    # GIVEN a retired component that was serviced once before retirement -
    # "Usage at Retirement" is the part's whole life, not just its last leg
    component = settings.GearComponent(
        name="Old Chain",
        installed_date="2026-01-01",
        distance_meters=900_000,  # 900 km over its whole life
        time_seconds=180_000,  # 50 h over its whole life
        last_service_km=550.0,  # km at an intermediate service
        last_service_hours=20.0,  # hours at an intermediate service
        status="retired",
    )
    gear = settings.Gear(
        activity_type_key="ride", name="Bike", components=[component.to_dict()]
    )

    # WHEN
    html = _render_stats_cards(component, gear, is_retired=True)

    normalized = " ".join(html.split())

    # THEN - DONE: full lifetime usage (900 km), not since-last-service (350 km)
    assert "900 km" in normalized
    assert "50.0 h" in normalized
    assert "350 km" not in normalized
    print("DONE: retired component Usage card reflects full lifetime usage")
