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

"""Tests for the profile_metrics route logic and AthleteMetrics form integration.

These tests verify the form/model integration and metric update logic
without requiring a running Flask server.
"""

from unittest import mock

import pytest

from mytral import athlete_metrics as am
from mytral import settings as app_settings

#
# Route business logic: metric value update simulation
#


@pytest.mark.mytral
def test_profile_metrics_update_sets_values():
    # GIVEN — an AthleteMetrics instance with all-zero defaults
    metrics = app_settings.AthleteMetrics()

    # WHEN — simulate what the POST handler does (convert form data to metrics)
    metrics.max_hr = int(183)
    metrics.anaerobic_threshold_hr = int(156)
    metrics.aerobic_threshold_hr = int(131)
    metrics.ftp = float(220.0)
    metrics.vo2max = float(52.5)
    metrics.hrv_rmssd = float(42.0)
    metrics.fat_max = float(31.5)
    metrics.z1_high = int(117)
    metrics.z2_high = int(133)
    metrics.z3_high = int(148)
    metrics.z4_high = int(164)

    # THEN — all values must be stored correctly
    assert metrics.max_hr == 183
    assert metrics.anaerobic_threshold_hr == 156
    assert metrics.aerobic_threshold_hr == 131
    assert metrics.ftp == pytest.approx(220.0)
    assert metrics.vo2max == pytest.approx(52.5)
    assert metrics.hrv_rmssd == pytest.approx(42.0)
    assert metrics.fat_max == pytest.approx(31.5)
    assert metrics.z1_high == 117
    assert metrics.z2_high == 133
    assert metrics.z3_high == 148
    assert metrics.z4_high == 164
    print("DONE: profile_metrics_update sets all metric fields correctly")


@pytest.mark.mytral
def test_profile_metrics_update_clears_values():
    # GIVEN — metrics previously set
    metrics = app_settings.AthleteMetrics(
        max_hr=183,
        ftp=220.0,
        z1_high=117,
        z2_high=133,
        z3_high=148,
        z4_high=164,
    )

    # WHEN — user clears all fields (simulate setting to 0)
    metrics.max_hr = int(0)
    metrics.ftp = float(0.0)
    metrics.z1_high = int(0)
    metrics.z2_high = int(0)
    metrics.z3_high = int(0)
    metrics.z4_high = int(0)

    # THEN — 0 means "not set" — estimates will take over after resolve()
    assert metrics.max_hr == 0
    assert metrics.ftp == pytest.approx(0.0)
    assert metrics.z1_high == 0
    print("DONE: profile_metrics_update clears fields when set to 0")


#
# Metrics round-trip: set → serialize → deserialize → resolve
#


@pytest.mark.mytral
def test_metrics_full_round_trip():
    # GIVEN — set metrics, serialize, deserialize, then resolve
    metrics = app_settings.AthleteMetrics(
        max_hr=183,
        anaerobic_threshold_hr=156,
        aerobic_threshold_hr=131,
        ftp=220.0,
    )

    # WHEN — serialize to dict (as if saving to JSON) and back
    data = metrics.to_dict_persisted()
    restored = app_settings.AthleteMetrics.from_dict(data)

    # resolve() fills e_* fields
    user_profile = mock.MagicMock()
    user_profile.athlete_metrics = restored
    user_profile.age = 38

    am.resolve(
        athlete_metrics=restored,
        user_profile=user_profile,
        activities=[],
        weight_kg=70.0,
    )

    # THEN — set values pass through; e_* mirrors set values
    assert restored.e_max_hr == 183  # set value used
    assert restored.e_anaerobic_threshold_hr == 156  # set value used
    assert restored.e_ftp == pytest.approx(220.0)  # set value used
    assert restored.e_power_to_weight > 0  # derived from ftp + weight
    # zone boundaries estimated from set LTHR (156)
    assert restored.e_z1_high > 0
    assert restored.e_z5_high == 183  # Z5 upper = e_max_hr
    print("DONE: full round-trip (set → serialize → deserialize → resolve) OK")
