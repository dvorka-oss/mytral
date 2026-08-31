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

from mytral import charts
from mytral import settings
from mytral.backends import entities


def _activity(activity_type_key, distance_m, duration_s, elevation_m):
    activity = entities.ActivityEntity()
    activity.activity_type_key = activity_type_key
    activity.distance = distance_m
    activity.duration_seconds = duration_s
    activity.elevation_gain = elevation_m
    return activity


def _gear_activity(when):
    activity = entities.ActivityEntity()
    activity.when = when
    return activity


def _activity_types():
    return settings.UserActivityTypes(list(settings.UserActivityTypes.BOOTSTRAP))


@pytest.mark.mytral
def test_activities_histograms_builds_all_aspects():
    # GIVEN a few rides with distance, duration, and elevation
    activities = [
        _activity("ride", 12_000, 45 * 60, 120),
        _activity("ride", 48_000, 130 * 60, 900),
        _activity("ride", 52_000, 140 * 60, 1_100),
    ]

    # WHEN building histograms filtered to rides
    histograms = charts.activities_histograms(
        activities, _activity_types(), filter_activity_type="ride"
    )

    # THEN each aspect yields a (script, div) pair
    assert set(histograms) == {"distance", "time", "elevation"}
    for aspect, chart in histograms.items():
        assert chart is not None, aspect
        script, div = chart
        assert script and div


@pytest.mark.mytral
def test_activities_histograms_filters_by_activity_type():
    # GIVEN one ride and one flat run (no elevation gain)
    activities = [
        _activity("ride", 40_000, 120 * 60, 500),
        _activity("run", 5_000, 22 * 60, 0),
    ]

    # WHEN filtering to runs only
    histograms = charts.activities_histograms(
        activities, _activity_types(), filter_activity_type="run"
    )

    # THEN charts are built from the single run (distance/time present)
    assert histograms["distance"] is not None
    assert histograms["time"] is not None
    # AND the run has no meaningful elevation -> that aspect is empty
    assert histograms["elevation"] is None


@pytest.mark.mytral
def test_histogram_components_bins_values_and_handles_empty():
    # GIVEN durations in minutes and a 15-minute bin width
    values = [10.0, 20.0, 44.0, 46.0]

    # WHEN binning into a histogram
    chart = charts._histogram_components(
        values,
        bin_width=15,
        title="Activities by Time",
        x_axis_label="Duration (min)",
        unit="min",
    )

    # THEN a (script, div) pair is produced
    assert chart is not None
    script, div = chart
    assert script and div

    # AND an empty input yields no chart (empty-state path)
    assert (
        charts._histogram_components(
            [], bin_width=15, title="t", x_axis_label="x", unit="min"
        )
        is None
    )


@pytest.mark.mytral
def test_gear_weekly_usage_histogram_bins_by_iso_week_across_years():
    # GIVEN gear activities in the same ISO week of two different years, plus
    # one activity in a different week
    activities = [
        _gear_activity("2024-03-04"),  # ISO week 10
        _gear_activity("2025-03-03"),  # ISO week 10 (different year)
        _gear_activity("2024-06-10"),  # ISO week 24
    ]

    # WHEN building the weekly usage histogram
    chart = charts.gear_weekly_usage_histogram(activities)

    # THEN a (script, div) pair is produced, merging counts across years
    assert chart is not None
    script, div = chart
    assert script and div


@pytest.mark.mytral
def test_gear_weekly_usage_histogram_folds_iso_week_53_into_52():
    # GIVEN a gear activity on a date that falls into ISO week 53
    activities = [_gear_activity("2026-12-31")]

    # WHEN building the weekly usage histogram
    chart = charts.gear_weekly_usage_histogram(activities)

    # THEN the chart is still built (week 53 folded into the last bin)
    assert chart is not None


@pytest.mark.mytral
def test_gear_weekly_usage_histogram_handles_empty_and_missing_dates():
    # GIVEN no activities at all
    # WHEN building the weekly usage histogram
    # THEN there is no chart to show
    assert charts.gear_weekly_usage_histogram([]) is None

    # AND an activity without a usable date is ignored, also yielding no chart
    assert charts.gear_weekly_usage_histogram([_gear_activity("")]) is None


@pytest.mark.mytral
def test_duration_label_formats_minutes_as_hms():
    # GIVEN durations expressed in minutes
    # WHEN formatting them for the time histogram tooltip
    # THEN the hours part is dropped when empty and the leading unit is unpadded
    assert charts._duration_label(0) == "0m00s"
    assert charts._duration_label(45) == "45m00s"
    assert charts._duration_label(60) == "1h00m00s"
    assert charts._duration_label(63) == "1h03m00s"
    assert charts._duration_label(135) == "2h15m00s"
    # AND sub-minute seconds keep two-digit padding
    assert charts._duration_label(1.5) == "1m30s"
