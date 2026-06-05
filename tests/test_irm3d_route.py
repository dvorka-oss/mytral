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
from types import SimpleNamespace

import flask
import pytest

from mytral.blueprints import irm3d_uri_space
from mytral.metrics import irm3d


@pytest.mark.mytral
def test_insight_irm3d_redirects_without_user(monkeypatch):
    # GIVEN
    monkeypatch.setattr(flask, "url_for", lambda endpoint: "/login")
    with irm3d_uri_space.flask_app.test_request_context("/insight/irm3d", method="GET"):
        # WHEN
        response = irm3d_uri_space.insight_irm3d()

    # THEN
    assert response.status_code == 302
    assert "/login" in response.location
    print("DONE: /insight/irm3d redirects to login without session user")


@pytest.mark.mytral
def test_insight_irm3d_route_renders_with_data(monkeypatch):
    # GIVEN
    captured = {}
    profile = SimpleNamespace(
        dataset_name="main",
        age=38,
        athlete_metrics=SimpleNamespace(
            e_critical_power=300.0,
            critical_power=0.0,
            e_ftp=300.0,
            ftp=0.0,
            e_w_prime_joules=18000.0,
            w_prime_joules=0.0,
            e_p_max_watts=1000.0,
            p_max_watts=0.0,
        ),
    )

    def fake_render_template(template_name, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "ok"

    monkeypatch.setattr(irm3d_uri_space.ds, "profile", lambda user_id: profile)
    monkeypatch.setattr(
        irm3d_uri_space.ds,
        "list_activities",
        lambda **kwargs: [SimpleNamespace(weight=70.0, max_watts=0.0)],
    )
    monkeypatch.setattr(
        irm3d_uri_space.athlete_metrics_mod, "resolve", lambda **kwargs: None
    )
    monkeypatch.setattr(
        irm3d_uri_space,
        "_compute_workout_rows",
        lambda activities, user_id, model_params: [
            irm3d.WorkoutStrainBreakdown(
                activity_key="a1",
                date=datetime.date(2026, 6, 1),
                ss_total=65.0,
                ss_cp=40.0,
                ss_w_prime=20.0,
                ss_pmax=5.0,
                min_mpa_watts=760.0,
                max_power_watts=900.0,
                near_limit_seconds=8.0,
                samples=60,
            )
        ],
    )
    monkeypatch.setattr(
        irm3d_uri_space.charts,
        "irm3d_composite",
        lambda daily_rows, state_rows, is_mobile_view: (
            "<script>Bokeh</script>",
            "<div>chart</div>",
        ),
    )
    monkeypatch.setattr(flask, "render_template", fake_render_template)

    with irm3d_uri_space.flask_app.test_request_context("/insight/irm3d", method="GET"):
        flask.session[irm3d_uri_space.COOKIE_USER] = "user-1"

        # WHEN
        response = irm3d_uri_space.insight_irm3d()

    # THEN
    assert response == "ok"
    assert captured["template_name"] == "insight-irm3d.html"
    assert captured["context"]["div"] == "<div>chart</div>"
    assert captured["context"]["script"] == "<script>Bokeh</script>"
    assert captured["context"]["latest_state"] is not None
    assert captured["context"]["latest_day"] is not None
    print("DONE: /insight/irm3d renders and passes chart context")
