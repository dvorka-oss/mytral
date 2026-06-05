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
import json
import os

import pytest

from mytral.metrics import irm3d
from mytral.metrics import irm3d_cache


@pytest.mark.mytral
def test_model_params_hash_deterministic():
    # GIVEN
    params = irm3d.PowerModelParams(
        cp_watts=300.0, w_prime_joules=18000.0, pmax_watts=1000.0
    )

    # WHEN
    hash1 = irm3d_cache.compute_model_params_hash(params)
    hash2 = irm3d_cache.compute_model_params_hash(params)

    # THEN
    assert hash1 == hash2
    assert len(hash1) == 64
    print("DONE: model params hash is deterministic")


@pytest.mark.mytral
def test_model_params_hash_changes_with_params():
    # GIVEN
    params_a = irm3d.PowerModelParams(
        cp_watts=300.0, w_prime_joules=18000.0, pmax_watts=1000.0
    )
    params_b = irm3d.PowerModelParams(
        cp_watts=310.0, w_prime_joules=18000.0, pmax_watts=1000.0
    )

    # WHEN
    hash_a = irm3d_cache.compute_model_params_hash(params_a)
    hash_b = irm3d_cache.compute_model_params_hash(params_b)

    # THEN
    assert hash_a != hash_b
    print("DONE: different model params produce different hashes")


@pytest.mark.mytral
def test_irm3d_file_cache_save_and_load(tmp_path):
    # GIVEN
    cache_dir = str(tmp_path)
    blobs_dir = os.path.join(cache_dir, "blobs")
    os.makedirs(blobs_dir, exist_ok=True)
    file_cache = irm3d_cache.Irm3dFileCache(cache_dir)
    data = {"key": "value", "nested": {"a": 1}}

    # WHEN
    file_cache.save(data)
    loaded = file_cache.load()

    # THEN
    assert loaded is not None
    assert loaded["key"] == "value"
    assert loaded["nested"]["a"] == 1
    assert os.path.isfile(os.path.join(blobs_dir, "irm3d_cache.json"))
    print("DONE: IRM3D file cache saves and loads correctly")


@pytest.mark.mytral
def test_irm3d_file_cache_load_nonexistent(tmp_path):
    # GIVEN
    cache_dir = str(tmp_path)
    file_cache = irm3d_cache.Irm3dFileCache(cache_dir)

    # WHEN
    loaded = file_cache.load()

    # THEN
    assert loaded is None
    print("DONE: IRM3D file cache returns None for nonexistent file")


@pytest.mark.mytral
def test_irm3d_file_cache_invalidate(tmp_path):
    # GIVEN
    cache_dir = str(tmp_path)
    blobs_dir = os.path.join(cache_dir, "blobs")
    os.makedirs(blobs_dir, exist_ok=True)
    cache_path = os.path.join(blobs_dir, "irm3d_cache.json")
    with open(cache_path, "w") as fh:
        json.dump({"test": True}, fh)

    file_cache = irm3d_cache.Irm3dFileCache(cache_dir)

    # WHEN
    file_cache.invalidate()

    # THEN
    assert not os.path.isfile(cache_path)
    print("DONE: IRM3D file cache invalidate removes file")


@pytest.mark.mytral
def test_irm3d_file_cache_dates_roundtrip(tmp_path):
    # GIVEN
    cache_dir = str(tmp_path)
    blobs_dir = os.path.join(cache_dir, "blobs")
    os.makedirs(blobs_dir, exist_ok=True)
    file_cache = irm3d_cache.Irm3dFileCache(cache_dir)
    workout_data = {
        "activity_key": "abc123",
        "date": datetime.date(2026, 6, 1),
        "ss_total": 65.0,
        "ss_cp": 40.0,
        "ss_w_prime": 20.0,
        "ss_pmax": 5.0,
        "min_mpa_watts": 760.0,
        "max_power_watts": 900.0,
        "near_limit_seconds": 8.0,
        "samples": 60,
    }
    cache_entry = {
        "recording_fingerprint": "abc123def456",
        "data": workout_data,
    }
    data = {
        "model_params_hash": "hash123",
        "workout_strains": {"abc123": cache_entry},
    }

    # WHEN
    file_cache.save(data)
    loaded = file_cache.load()

    # THEN
    assert loaded is not None
    loaded_entry = loaded["workout_strains"]["abc123"]
    assert loaded_entry["recording_fingerprint"] == "abc123def456"
    loaded_data = loaded_entry["data"]
    assert isinstance(loaded_data["date"], datetime.date)
    assert loaded_data["date"] == datetime.date(2026, 6, 1)
    assert loaded_data["ss_total"] == 65.0
    assert loaded_data["activity_key"] == "abc123"
    print("DONE: IRM3D file cache roundtrips dates and fingerprints correctly")


@pytest.mark.mytral
def test_irm3d_file_cache_legacy_flat_entries(tmp_path):
    """Legacy flat entries (no fingerprint wrapper) still deserialize."""
    # GIVEN
    cache_dir = str(tmp_path)
    blobs_dir = os.path.join(cache_dir, "blobs")
    os.makedirs(blobs_dir, exist_ok=True)
    file_cache = irm3d_cache.Irm3dFileCache(cache_dir)
    legacy_entry = {
        "activity_key": "old123",
        "date": datetime.date(2025, 1, 1),
        "ss_total": 50.0,
        "ss_cp": 30.0,
        "ss_w_prime": 15.0,
        "ss_pmax": 5.0,
        "min_mpa_watts": 500.0,
        "max_power_watts": 600.0,
        "near_limit_seconds": 5.0,
        "samples": 30,
    }
    data = {
        "model_params_hash": "oldhash",
        "workout_strains": {"old123": legacy_entry},
    }

    # WHEN
    file_cache.save(data)
    loaded = file_cache.load()

    # THEN
    assert loaded is not None
    loaded_entry = loaded["workout_strains"]["old123"]
    # legacy entries have no recording_fingerprint key
    assert "recording_fingerprint" not in loaded_entry
    assert loaded_entry["activity_key"] == "old123"
    assert loaded_entry["date"] == datetime.date(2025, 1, 1)
    print("DONE: legacy flat cache entries load without errors")


@pytest.mark.mytral
def test_irm3d_file_cache_load_corrupt_json(tmp_path):
    # GIVEN
    cache_dir = str(tmp_path)
    blobs_dir = os.path.join(cache_dir, "blobs")
    os.makedirs(blobs_dir, exist_ok=True)
    cache_path = os.path.join(blobs_dir, "irm3d_cache.json")
    with open(cache_path, "w") as fh:
        fh.write("this is not valid json {")

    file_cache = irm3d_cache.Irm3dFileCache(cache_dir)

    # WHEN
    loaded = file_cache.load()

    # THEN
    assert loaded is None
    print("DONE: IRM3D file cache returns None for corrupt JSON")
