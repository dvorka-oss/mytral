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
import dataclasses
import datetime

import pytest

from mytral import charts
from mytral.metrics import irm3d
from mytral.recordings import models as recording_models


def _recording_with_power(
    start: datetime.datetime,
    powers: list[float],
) -> recording_models.RecordingData:
    timestamps = [start + datetime.timedelta(seconds=i) for i in range(len(powers))]
    power_values = [float(power) for power in powers]
    return recording_models.RecordingData(
        timestamps=timestamps,
        hr_values=[None] * len(power_values),
        speed_values=[None] * len(power_values),
        cadence_values=[None] * len(power_values),
        altitude_values=[None] * len(power_values),
        lat_values=[None] * len(power_values),
        lon_values=[None] * len(power_values),
        power_values=power_values,
        has_speed=False,
        has_cadence=False,
        has_altitude=False,
        has_gps=False,
        has_power=True,
        source_format="fit",
    )


@pytest.mark.mytral
def test_mpa_boundary_values():
    # GIVEN
    params = irm3d.PowerModelParams(
        cp_watts=300.0, w_prime_joules=20000.0, pmax_watts=1200.0
    )

    # WHEN
    mpa_fresh = irm3d.compute_mpa(params, w_prime_expended_joules=0.0)
    mpa_depleted = irm3d.compute_mpa(params, w_prime_expended_joules=20000.0)

    # THEN
    assert mpa_fresh == pytest.approx(1200.0)
    assert mpa_depleted == pytest.approx(300.0)
    print("DONE: Eq.4 MPA boundary behavior is correct")


@pytest.mark.mytral
def test_system_contribution_sums_to_power():
    # GIVEN
    params = irm3d.PowerModelParams(
        cp_watts=300.0, w_prime_joules=20000.0, pmax_watts=1200.0
    )
    power = 1000.0

    # WHEN
    cp_share, w_prime_share, pmax_share = irm3d.compute_system_power_contrib(
        power, params
    )

    # THEN
    assert cp_share + w_prime_share + pmax_share == pytest.approx(power)
    assert cp_share == pytest.approx(300.0)
    print("DONE: Eq.8-10 decomposition closes to total power")


@pytest.mark.mytral
def test_system_contribution_below_cp():
    # GIVEN
    params = irm3d.PowerModelParams(
        cp_watts=300.0, w_prime_joules=20000.0, pmax_watts=1200.0
    )

    # WHEN
    cp_share, w_prime_share, pmax_share = irm3d.compute_system_power_contrib(
        250.0, params
    )

    # THEN
    assert cp_share == pytest.approx(250.0)
    assert w_prime_share == pytest.approx(0.0)
    assert pmax_share == pytest.approx(0.0)
    print("DONE: Power below CP is attributed only to CP")


@pytest.mark.mytral
def test_ss_normalization_one_hour_at_cp():
    # GIVEN
    params = irm3d.PowerModelParams(
        cp_watts=300.0, w_prime_joules=20000.0, pmax_watts=1200.0
    )
    mpa = irm3d.compute_mpa(params, w_prime_expended_joules=0.0)

    # WHEN
    second_strain = irm3d.compute_second_strain(
        power_watts=300.0, mpa_watts=mpa, model_params=params
    )
    ss_hour = second_strain.ss_total * 3600.0

    # THEN
    assert ss_hour == pytest.approx(100.0, abs=0.05)
    print("DONE: Eq.13 normalization gives 100 SS for 1h at CP")


@pytest.mark.mytral
def test_kstrain_increases_when_mpa_falls():
    # GIVEN
    params = irm3d.PowerModelParams(
        cp_watts=300.0, w_prime_joules=20000.0, pmax_watts=1200.0
    )
    power = 600.0

    # WHEN
    k_fresh = irm3d.compute_kstrain(
        power_watts=power, mpa_watts=1200.0, model_params=params
    )
    k_tired = irm3d.compute_kstrain(
        power_watts=power, mpa_watts=800.0, model_params=params
    )

    # THEN
    assert k_tired > k_fresh
    print("DONE: lower MPA yields higher strain coefficient")


@pytest.mark.mytral
def test_workout_daily_and_ir_history_pipeline():
    # GIVEN
    params = irm3d.PowerModelParams(
        cp_watts=300.0, w_prime_joules=18000.0, pmax_watts=1000.0
    )
    recording_a = _recording_with_power(
        start=datetime.datetime(2026, 6, 1, 10, 0, 0),
        powers=[350.0] * 120,
    )
    recording_b = _recording_with_power(
        start=datetime.datetime(2026, 6, 3, 10, 0, 0),
        powers=[500.0] * 60,
    )

    # WHEN
    workout_a = irm3d.compute_workout_strain_from_recording(
        recording_data=recording_a,
        model_params=params,
        activity_key="a",
        activity_date=datetime.date(2026, 6, 1),
    )
    workout_b = irm3d.compute_workout_strain_from_recording(
        recording_data=recording_b,
        model_params=params,
        activity_key="b",
        activity_date=datetime.date(2026, 6, 3),
    )
    daily_rows = irm3d.aggregate_daily_strain([workout_a, workout_b])
    state_rows = irm3d.run_3d_impulse_response(
        daily_rows=daily_rows,
        irm_params=irm3d.Irm3dParams(),
        model_params=params,
    )

    # THEN
    assert workout_a is not None
    assert workout_b is not None
    assert workout_a.ss_total > 0
    assert len(daily_rows) == 3
    assert daily_rows[1].date.isoformat() == "2026-06-02"
    assert daily_rows[1].ss_total == pytest.approx(0.0)
    assert len(state_rows) == len(daily_rows)
    assert state_rows[-1].cp_watts > 0
    assert state_rows[-1].w_prime_joules > 0
    assert state_rows[-1].pmax_watts > 0
    print("DONE: workout/day/history 3D IRM pipeline works")


@pytest.mark.mytral
def test_irm3d_chart_smoke():
    # GIVEN
    daily_row = irm3d.DailyStrainRow(
        date=datetime.date(2026, 6, 1),
        ss_total=65.0,
        ss_cp=40.0,
        ss_w_prime=20.0,
        ss_pmax=5.0,
        workouts=1,
        near_limit_seconds=12.0,
        min_mpa_watts=760.0,
    )
    state_row = irm3d.Irm3dStateRow(
        date=datetime.date(2026, 6, 1),
        load_cp=40.0,
        load_w_prime=20.0,
        load_pmax=5.0,
        cp_fitness=10.0,
        cp_fatigue=8.0,
        cp_readiness=2.0,
        w_prime_fitness=6.0,
        w_prime_fatigue=4.0,
        w_prime_readiness=2.0,
        pmax_fitness=2.0,
        pmax_fatigue=1.0,
        pmax_readiness=1.0,
        cp_watts=302.0,
        w_prime_joules=18002.0,
        pmax_watts=1001.0,
    )

    # WHEN
    script, div = charts.irm3d_composite(
        daily_rows=[dataclasses.asdict(daily_row)],
        state_rows=[dataclasses.asdict(state_row)],
    )

    # THEN
    assert "Bokeh" in script
    assert "RangeTool" in script
    assert "<div" in div
    print("DONE: 3D IRM chart returns Bokeh components")
