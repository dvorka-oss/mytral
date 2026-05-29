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

import pytest

from mytral import commons
from mytral import config
from mytral import tools
from mytral.backends import entities
from tests import _given


def _given_prune_dataset(tmp_path: pathlib.Path):
    """Prepare a test user with 4 activities covering different year/src
    combinations.
    """
    _, ds, profile = _given.given_test(
        config.MytralConfig(persistence_data_dir=tmp_path),
        user_id=commons.DEFAULT_USER_NAME,
    )
    dataset_name = commons.DS_LIFELONG

    def _make(when_year, src, src_key, src_descriptor):
        return ds.create_activity(
            user_id=profile.user_id,
            dataset_name=dataset_name,
            entity=entities.ActivityEntity(
                name=f"{src} {when_year}",
                when_year=when_year,
                when_month=1,
                when_day=1,
                src=src,
                src_key=src_key,
                src_descriptor=src_descriptor,
            ),
        )

    # seq-0: 2023, strava
    _make(2023, "strava", "strava-key-001", "")
    # seq-1: 2024, strava (second strava, different year from seq-0)
    _make(2024, "strava", "strava-key-002", "")
    # seq-2: 2024, manual with descriptor
    _make(2024, "manual", "", "imported=true")
    # seq-3: 2024, concept2 with descriptor and key
    _make(2024, "concept2", "c2-key-001", "season=2024/2025")

    return ds, profile, dataset_name


@pytest.mark.mytral
def test_prune_by_year(tmp_path: pathlib.Path):
    """Pruning by year removes only activities from that year."""

    # GIVEN
    ds, profile, dataset_name = _given_prune_dataset(tmp_path)

    # WHEN
    pruned = tools.prune_activities(
        user_id=profile.user_id,
        dataset_name=dataset_name,
        ds=ds,
        filter_when_year="2023",
    )

    # THEN
    remaining = ds.list_activities(user_id=profile.user_id, dataset_name=dataset_name)
    assert pruned == 1, f"Expected 1 pruned, got {pruned}"
    assert len(remaining) == 3, f"Expected 3 remaining, got {len(remaining)}"
    assert all(str(a.when_year) != "2023" for a in remaining)
    print(f"DONE: pruned={pruned}, remaining={len(remaining)}")


@pytest.mark.mytral
def test_prune_by_src(tmp_path: pathlib.Path):
    """Pruning by src removes all activities with that source."""

    # GIVEN
    ds, profile, dataset_name = _given_prune_dataset(tmp_path)

    # WHEN
    pruned = tools.prune_activities(
        user_id=profile.user_id,
        dataset_name=dataset_name,
        ds=ds,
        filter_src="strava",
    )

    # THEN
    remaining = ds.list_activities(user_id=profile.user_id, dataset_name=dataset_name)
    assert pruned == 2, f"Expected 2 pruned, got {pruned}"
    assert len(remaining) == 2, f"Expected 2 remaining, got {len(remaining)}"
    assert all(a.src != "strava" for a in remaining)
    print(f"DONE: pruned={pruned}, remaining={len(remaining)}")


@pytest.mark.mytral
def test_prune_by_src_key(tmp_path: pathlib.Path):
    """Pruning by src_key removes only the activity with that exact key."""

    # GIVEN
    ds, profile, dataset_name = _given_prune_dataset(tmp_path)

    # WHEN
    pruned = tools.prune_activities(
        user_id=profile.user_id,
        dataset_name=dataset_name,
        ds=ds,
        filter_src_key="strava-key-001",
    )

    # THEN
    remaining = ds.list_activities(user_id=profile.user_id, dataset_name=dataset_name)
    assert pruned == 1, f"Expected 1 pruned, got {pruned}"
    assert len(remaining) == 3, f"Expected 3 remaining, got {len(remaining)}"
    assert all(a.src_key != "strava-key-001" for a in remaining)
    print(f"DONE: pruned={pruned}, remaining={len(remaining)}")


@pytest.mark.mytral
def test_prune_by_src_descriptor(tmp_path: pathlib.Path):
    """Pruning by src_descriptor removes only matching activities."""

    # GIVEN
    ds, profile, dataset_name = _given_prune_dataset(tmp_path)

    # WHEN
    pruned = tools.prune_activities(
        user_id=profile.user_id,
        dataset_name=dataset_name,
        ds=ds,
        filter_src_descriptor="season=2024/2025",
    )

    # THEN
    remaining = ds.list_activities(user_id=profile.user_id, dataset_name=dataset_name)
    assert pruned == 1, f"Expected 1 pruned, got {pruned}"
    assert len(remaining) == 3, f"Expected 3 remaining, got {len(remaining)}"
    assert all(a.src_descriptor != "season=2024/2025" for a in remaining)
    print(f"DONE: pruned={pruned}, remaining={len(remaining)}")


@pytest.mark.mytral
def test_prune_multi_filter_and_logic(tmp_path: pathlib.Path):
    """Pruning with multiple filters applies AND logic - only exact match is removed."""

    # GIVEN
    ds, profile, dataset_name = _given_prune_dataset(tmp_path)

    # WHEN - year=2024 AND src=strava: matches seq-1 only (seq-0 is 2023/strava)
    pruned = tools.prune_activities(
        user_id=profile.user_id,
        dataset_name=dataset_name,
        ds=ds,
        filter_when_year="2024",
        filter_src="strava",
    )

    # THEN
    remaining = ds.list_activities(user_id=profile.user_id, dataset_name=dataset_name)
    assert pruned == 1, f"Expected 1 pruned, got {pruned}"
    assert len(remaining) == 3, f"Expected 3 remaining, got {len(remaining)}"
    # seq-0 (2023/strava) must still be present
    strava_remaining = [a for a in remaining if a.src == "strava"]
    assert len(strava_remaining) == 1, "seq-0 (2023 strava) should remain"
    assert strava_remaining[0].when_year == 2023
    print(f"DONE: pruned={pruned}, remaining={len(remaining)}")


@pytest.mark.mytral
def test_prune_all_filter_prunes_everything(tmp_path: pathlib.Path):
    """Pruning with ALL for all filters removes every activity."""

    # GIVEN
    ds, profile, dataset_name = _given_prune_dataset(tmp_path)

    # WHEN
    pruned = tools.prune_activities(
        user_id=profile.user_id,
        dataset_name=dataset_name,
        ds=ds,
        filter_when_year=tools.PRUNE_FILTER_ALL,
        filter_src=tools.PRUNE_FILTER_ALL,
        filter_src_key=tools.PRUNE_FILTER_ALL,
        filter_src_descriptor=tools.PRUNE_FILTER_ALL,
    )

    # THEN
    remaining = ds.list_activities(user_id=profile.user_id, dataset_name=dataset_name)
    assert pruned == 4, f"Expected 4 pruned, got {pruned}"
    assert len(remaining) == 0, f"Expected 0 remaining, got {len(remaining)}"
    print(f"DONE: pruned={pruned}, remaining={len(remaining)}")


@pytest.mark.mytral
def test_prune_no_match_prunes_nothing(tmp_path: pathlib.Path):
    """Pruning with a filter that matches nothing removes no activities."""

    # GIVEN
    ds, profile, dataset_name = _given_prune_dataset(tmp_path)

    # WHEN
    pruned = tools.prune_activities(
        user_id=profile.user_id,
        dataset_name=dataset_name,
        ds=ds,
        filter_src="nonexistent-source",
    )

    # THEN
    remaining = ds.list_activities(user_id=profile.user_id, dataset_name=dataset_name)
    assert pruned == 0, f"Expected 0 pruned, got {pruned}"
    assert len(remaining) == 4, f"Expected 4 remaining, got {len(remaining)}"
    print(f"DONE: pruned={pruned}, remaining={len(remaining)}")
