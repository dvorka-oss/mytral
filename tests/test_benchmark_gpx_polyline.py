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
import pathlib
import time

import pytest

from mytral.recordings import gpx_extractor


def _load_largest_gpx_files(
    directory: pathlib.Path,
    limit: int,
) -> list[pathlib.Path]:
    """Return the largest GPX fixtures from *directory*."""
    gpx_files = sorted(
        directory.glob("*.gpx"),
        key=lambda path: path.stat().st_size,
        reverse=True,
    )
    return gpx_files[:limit]

@pytest.mark.skip(reason="This is a polyline benchmark test, not a functional test.")
@pytest.mark.mytral
@pytest.mark.benchmark
def test_benchmark_gpx_polyline_methods():
    """Compare the current and fast GPX polyline simplifiers."""
    #
    # GIVEN
    #
    data_dir = pathlib.Path(__file__).resolve().parent / "data" / "import" / "gpx"
    gpx_files = _load_largest_gpx_files(data_dir, limit=2)
    assert gpx_files, f"no .gpx files found in {data_dir}"

    total_current_s = 0.0
    total_fast_s = 0.0

    #
    # WHEN / THEN
    #
    for gpx_path in gpx_files:
        gpx_data = gpx_path.read_bytes()
        points = gpx_extractor.extract_gps_points(gpx_data)

        current_start = time.perf_counter()
        current_result = gpx_extractor.encode_gps_polylines(
            points,
            polyline_method=gpx_extractor.GPX_POLYLINE_METHOD_LEGACY,
        )
        current_elapsed = time.perf_counter() - current_start

        fast_start = time.perf_counter()
        fast_result = gpx_extractor.encode_gps_polylines(
            points,
            polyline_method=gpx_extractor.GPX_POLYLINE_METHOD_FAST,
        )
        fast_elapsed = time.perf_counter() - fast_start

        assert current_result is not None
        assert fast_result is not None
        current_summary_polyline, current_bbox, _ = current_result
        fast_summary_polyline, fast_bbox, _ = fast_result

        current_points = gpx_extractor.decode_polyline(current_summary_polyline)
        fast_points = gpx_extractor.decode_polyline(fast_summary_polyline)
        assert current_points, f"current polyline decoded to no points for {gpx_path}"
        assert fast_points, f"fast polyline decoded to no points for {gpx_path}"
        assert current_points[0] == pytest.approx(fast_points[0], abs=1e-5)
        assert current_points[-1] == pytest.approx(fast_points[-1], abs=1e-5)
        assert current_bbox == fast_bbox

        total_current_s += current_elapsed
        total_fast_s += fast_elapsed

        speedup = current_elapsed / fast_elapsed if fast_elapsed > 0 else float("inf")
        print(
            f"\n{gpx_path.name}"
            f"\n  current: {current_elapsed:.4f} s"
            f"\n  fast:    {fast_elapsed:.4f} s"
            f"\n  speedup: {speedup:.2f}x"
        )

    overall_speedup = (
        total_current_s / total_fast_s if total_fast_s > 0 else float("inf")
    )
    assert total_fast_s < total_current_s
    print(
        f"\nTotals"
        f"\n  current: {total_current_s:.4f} s"
        f"\n  fast:    {total_fast_s:.4f} s"
        f"\n  speedup: {overall_speedup:.2f}x"
    )
