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
import time

import pytest

from mytral.recordings.models import RecordingData
from mytral.recordings.parquet_converter import fit_to_parquet
from mytral.recordings.parquet_converter import load_parquet
from tests import _given


def _assert_recording_data_equal(fit_rec: RecordingData, pq_rec: RecordingData) -> None:
    """Assert that two RecordingData instances are structurally equal.

    Parameters
    ----------
    fit_rec : RecordingData
        Records loaded directly from a FIT file via fit_to_parquet + load_parquet.
    pq_rec : RecordingData
        Records loaded from the corresponding pre-built Parquet file.
    """
    assert len(fit_rec.timestamps) == len(pq_rec.timestamps), (
        f"timestamp count mismatch: FIT={len(fit_rec.timestamps)} "
        f"Parquet={len(pq_rec.timestamps)}"
    )
    for i, (a, b) in enumerate(zip(fit_rec.timestamps, pq_rec.timestamps)):
        # compare with millisecond precision (Parquet stores ms)
        assert abs((a - b).total_seconds()) < 0.001, (
            f"timestamp[{i}] mismatch: FIT={a!r} Parquet={b!r}"
        )

    assert fit_rec.hr_values == pq_rec.hr_values, "hr_values mismatch"
    assert fit_rec.speed_values == pq_rec.speed_values, "speed_values mismatch"
    assert fit_rec.cadence_values == pq_rec.cadence_values, "cadence_values mismatch"
    assert fit_rec.altitude_values == pq_rec.altitude_values, "altitude_values mismatch"
    assert fit_rec.has_speed == pq_rec.has_speed, "has_speed mismatch"
    assert fit_rec.has_cadence == pq_rec.has_cadence, "has_cadence mismatch"
    assert fit_rec.has_altitude == pq_rec.has_altitude, "has_altitude mismatch"


@pytest.mark.mytral
@pytest.mark.benchmark
def test_benchmark_parquet():
    """Benchmark FIT vs Parquet loading into RecordingData and verify equality.

    For each FIT file in tests/data/import/fit the test:
      1. Converts FIT → Parquet bytes and saves to tests/data/import/parquet-for-fit/
         if the file is missing or outdated (auto-regeneration).
      2. Loads data via fit_to_parquet + load_parquet (FIT → RecordingData).
      3. Loads data via load_parquet from the on-disk Parquet file.
      4. Asserts that both structures are identical.
      5. Reports elapsed wall-clock time for each loading path.

    Example output::

      14122701.fit
        FIT    load: 0.0123 s  (547 records)
        Parquet load: 0.0012 s  (547 records)
        speedup: 10.25x
    """
    #
    # GIVEN
    #
    fit_files = sorted(_given.TEST_DATA_FIT_DIR.glob("*.fit"))
    assert fit_files, f"no .fit files found in {_given.TEST_DATA_FIT_DIR}"

    # ensure parquet directory exists
    _given.TEST_DATA_PARQUET_DIR.mkdir(parents=True, exist_ok=True)

    total_fit_s = 0.0
    total_pq_s = 0.0

    #
    # WHEN / THEN  (interleaved: load both formats per file, then compare)
    #
    for fit_path in fit_files:
        parquet_path = _given.TEST_DATA_PARQUET_DIR / (fit_path.stem + ".parquet")
        fit_data = fit_path.read_bytes()

        # auto-regenerate parquet if missing (new schema required)
        if not parquet_path.exists():
            parquet_bytes = fit_to_parquet(fit_data)
            parquet_path.write_bytes(parquet_bytes)
            print(f"\n  regenerated {parquet_path.name}")

        # --- FIT loading (convert on-the-fly, then load) ---
        t0 = time.perf_counter()
        fit_parquet_bytes = fit_to_parquet(fit_data)
        fit_rec = load_parquet(fit_parquet_bytes)
        fit_elapsed = time.perf_counter() - t0

        assert fit_rec.timestamps, (
            f"fit_to_parquet + load_parquet returned empty result for {fit_path.name}"
        )
        total_fit_s += fit_elapsed

        # --- Parquet loading (from pre-built file on disk) ---
        t0 = time.perf_counter()
        pq_rec = load_parquet(parquet_path.read_bytes())
        pq_elapsed = time.perf_counter() - t0

        assert pq_rec.timestamps, (
            f"load_parquet returned empty result for {parquet_path.name}"
        )
        total_pq_s += pq_elapsed

        n = len(fit_rec.timestamps)
        speedup = fit_elapsed / pq_elapsed if pq_elapsed > 0 else float("inf")
        print(
            f"\n{fit_path.name}"
            f"\n  FIT     load: {fit_elapsed:.4f} s  ({n} records)"
            f"\n  Parquet load: {pq_elapsed:.4f} s  ({len(pq_rec.timestamps)} records)"
            f"\n  speedup: {speedup:.2f}x"
        )

        _assert_recording_data_equal(fit_rec, pq_rec)
        print("  equality check: DONE")

    overall_speedup = total_fit_s / total_pq_s if total_pq_s > 0 else float("inf")
    print(
        f"\nTotals"
        f"\n  FIT     total: {total_fit_s:.4f} s"
        f"\n  Parquet total: {total_pq_s:.4f} s"
        f"\n  overall speedup: {overall_speedup:.2f}x"
    )
