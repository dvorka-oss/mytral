# MyTraL: my trailing log
#
# Copyright (C) 2022-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
from types import SimpleNamespace

import flask
import pytest

from mytral import routes
from mytral import settings
from mytral.blueprints import gear_crud
from mytral.tasks.do import strava_gear_sync


def _gear(key: str, name: str, vendor: str, model: str) -> settings.Gear:
    return settings.Gear(
        key=key,
        activity_type_key="run",
        name=name,
        vendor=vendor,
        model=model,
    )


@pytest.mark.mytral
def test_pick_fuzzy_match_prefers_unique_best_score():
    # GIVEN two same-brand shoes both clearing the brand-only threshold, where
    # the second is the actual match (model and nickname also match)
    speedcross_5 = _gear(
        "ae9198f2", "Salomon Speedcross 5 blue/white", "Salomon", "Speedcross 5"
    )
    speedcross_6 = _gear(
        "98b24151", "Salomon Speedcross 6 black/yellow", "Salomon", "Speedcross"
    )
    strava_item = {
        "id": "g27900197",
        "name": "Salomon Speedcross 6",
        "nickname": "black/yellow",
        "brand_name": "Salomon",
        "model_name": "Speedcross 6",
    }
    mytral_gears = [speedcross_5, speedcross_6]
    candidates = [
        (g, strava_gear_sync._score_match(strava_item, g)) for g in mytral_gears
    ]
    candidates = [(g, s) for g, s in candidates if s >= 3]

    # WHEN picking the fuzzy match
    matched = strava_gear_sync._pick_fuzzy_match(strava_item, candidates)

    # THEN the correct Speedcross 6 is chosen, not skipped as ambiguous
    assert matched is speedcross_6
    print("DONE")


@pytest.mark.mytral
def test_pick_fuzzy_match_tied_scores_stay_ambiguous():
    # GIVEN two candidates that tie at the top score and neither name matches
    shoe_a = _gear("a", "Brooks Glycerin 20 blue", "Brooks", "")
    shoe_b = _gear("b", "Brooks Glycerin 21 red", "Brooks", "")
    strava_item = {
        "id": "g1",
        "name": "Brooks Glycerin",
        "nickname": "",
        "brand_name": "Brooks",
        "model_name": "",
    }
    candidates = [(shoe_a, 3), (shoe_b, 3)]

    # WHEN picking the fuzzy match
    matched = strava_gear_sync._pick_fuzzy_match(strava_item, candidates)

    # THEN it stays ambiguous (None) so it is not mis-assigned
    assert matched is None
    print("DONE")


@pytest.mark.mytral
def test_pick_fuzzy_match_single_candidate():
    # GIVEN a single candidate
    shoe = _gear("a", "Nike Vomero 9", "Nike", "Vomero 9")
    candidates = [(shoe, 5)]

    # WHEN picking the fuzzy match
    matched = strava_gear_sync._pick_fuzzy_match({"id": "g1"}, candidates)

    # THEN that candidate is returned
    assert matched is shoe
    print("DONE")


@pytest.mark.mytral
def test_pick_fuzzy_match_no_candidates():
    # GIVEN no candidates
    # WHEN picking the fuzzy match
    matched = strava_gear_sync._pick_fuzzy_match({"id": "g1"}, [])

    # THEN nothing is matched
    assert matched is None
    print("DONE")


@pytest.mark.mytral
def test_settings_gear_advanced_renders_service_mapping(monkeypatch):
    # GIVEN a gear mapped to a Strava gear ID but not to Garmin/Polar
    entity = _gear("gear-1", "Salomon Speedcross 6", "Salomon", "Speedcross")
    entity.set_external_id("strava", "g27900197")
    profile = SimpleNamespace(user="User", expert=False, dataset_name="default")

    def fake_url_for(endpoint, **values):
        if "key" in values:
            return f"/{endpoint}/{values['key']}"
        return f"/{endpoint}"

    monkeypatch.setattr(
        gear_crud.ds, "get_gear", lambda user_id, key, dataset_name: entity
    )
    monkeypatch.setattr(gear_crud.ds, "profile", lambda user_id: profile)
    monkeypatch.setitem(routes.flask_app.jinja_env.globals, "url_for", fake_url_for)

    with routes.flask_app.test_request_context(
        "/settings/gears/gear-1/advanced", method="GET"
    ):
        flask.session[routes.COOKIE_USER] = "user-1"

        # WHEN rendering the advanced page
        html = gear_crud.settings_gear_advanced("gear-1")

    # THEN it lists every supported service, the Strava ID, and mapped status
    if hasattr(html, "get_data"):
        html = html.get_data(as_text=True)
    normalized = " ".join(html.split())
    assert "Strava" in normalized
    assert "Garmin Connect" in normalized
    assert "Polar" in normalized
    assert "g27900197" in normalized
    assert "Mapped" in normalized
    assert "Not mapped" in normalized
    print("DONE")
