# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
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
import pytest

from mytral import athlete_metrics as am_module
from mytral import charts
from mytral import settings
from mytral.recordings import parquet_converter
from tests import _given


@pytest.mark.mytral
def test_hr_zones_in_ts_charts():
    # GIVEN
    fit_files = sorted(_given.TEST_DATA_FIT_DIR.glob("*.fit"))
    assert fit_files
    fit_data = fit_files[0].read_bytes()
    parquet_bytes = parquet_converter.fit_to_parquet(fit_data)
    recording = parquet_converter.load_parquet(parquet_bytes)

    athlete_metrics = settings.AthleteMetrics(
        max_hr=190,
        anaerobic_threshold_hr=170,
        aerobic_threshold_hr=140,
    )
    user_profile = settings.UserProfile(
        user_id="test-user",
        user="test-user",
        email="test@example.com",
        password_enc="enc",
        dataset_name="default",
        dataset_names=["default"],
        height=1.80,
        born_year=1980,
        born_month=1,
        born_day=1,
        athlete_metrics=athlete_metrics,
    )

    am_module.resolve(
        athlete_metrics=athlete_metrics,
        user_profile=user_profile,
        activities=[],
    )

    # WHEN
    (
        overlay_res,
        ridge_res,
        hr_zones_res,
        cadence_hist_res,
        power_zones_res,
        power_curve_res,
        power_ts_res,
        hr_ts_res,
        speed_cadence_ts_res,
    ) = charts.activity_fit_charts(recording, athlete_metrics=athlete_metrics)

    # THEN
    # We want to verify that HR charts contain information about zones

    assert overlay_res is not None
    assert hr_ts_res is not None
    assert ridge_res is not None

    def assert_zones_in_script(result):
        script, div = result
        # Check for at least one zone color from HR_ZONE_COLORS
        # Tabler green: #2fb344, teal: #0ca678, yellow: #f59f00,
        # orange: #f76707, red: #d63939
        found = False
        for color in charts.HR_ZONE_COLORS:
            if color in script:
                found = True
                break
        assert found, f"None of the HR zone colors found in script: {script[:100]}..."

    assert_zones_in_script(overlay_res)
    assert_zones_in_script(hr_ts_res)
    assert_zones_in_script(ridge_res)

    print("test_hr_zones_in_ts_charts: DONE")
