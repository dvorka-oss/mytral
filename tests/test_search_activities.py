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
from mytral import loggers
from mytral.backends import dataset
from mytral.backends import entities


def _given_ds_with_activities(
    tmp_path: pathlib.Path,
) -> tuple[dataset.MyTraLDataset, str, str]:
    """Create a dataset with a few test activities."""
    data_dir = tmp_path / ".local"
    data_dir.mkdir(parents=True, exist_ok=True)
    user_id = "search-test-user-uuid"
    dataset_name = commons.DS_LIFELONG

    logger = loggers.MytralPrintLogger()
    app_config = config.MytralConfig(
        port=config.MytralConfig.DEFAULT_PORT,
        persistence_data_dir=data_dir.absolute(),
        auto_account_create=True,
    )
    mytral_ds = dataset.MyTraLDataset(mytral_config=app_config, logger=logger)
    mytral_ds.user().register_new_user(user_name="testathlete", user_id=user_id)

    # create activities with distinct names and descriptions
    mytral_ds.user().create_activity(
        user_id=user_id,
        dataset_name=dataset_name,
        entity=entities.ActivityEntity(
            name="Morning Run",
            description="Easy recovery run in the park",
            when_year=2025,
            when_month=3,
            when_day=10,
        ),
    )
    mytral_ds.user().create_activity(
        user_id=user_id,
        dataset_name=dataset_name,
        entity=entities.ActivityEntity(
            name="Tempo Ride",
            description="Hard bike session with intervals",
            when_year=2025,
            when_month=3,
            when_day=12,
        ),
    )
    mytral_ds.user().create_activity(
        user_id=user_id,
        dataset_name=dataset_name,
        entity=entities.ActivityEntity(
            name="Long Row",
            description="Steady ergometer run",
            when_year=2024,
            when_month=11,
            when_day=5,
        ),
    )
    mytral_ds.user().create_activity(
        user_id=user_id,
        dataset_name=dataset_name,
        entity=entities.ActivityEntity(
            name="Strength Training",
            description="",
            when_year=2025,
            when_month=1,
            when_day=20,
        ),
    )

    return mytral_ds, user_id, dataset_name


def _search(
    mytral_ds: dataset.MyTraLDataset,
    user_id: str,
    dataset_name: str,
    q: str,
) -> list[entities.ActivityEntity]:
    """Run a search matching the route logic."""
    activities = mytral_ds.user().list_activities(
        user_id=user_id,
        dataset_name=dataset_name,
        skip_future=True,
        sort_by_when=True,
    )
    q_lower = q.lower()
    return [
        a
        for a in activities
        if q_lower in (a.name or "").lower() or q_lower in (a.description or "").lower()
    ]


@pytest.mark.mytral
def test_search_activities_name_match(tmp_path: pathlib.Path):
    """Search should find activities whose name contains the query."""
    # GIVEN
    mytral_ds, user_id, dataset_name = _given_ds_with_activities(tmp_path)

    # WHEN
    results = _search(mytral_ds, user_id, dataset_name, "run")

    # THEN
    result_names = [a.name for a in results]
    print(f"Results for 'run': {result_names}")
    assert "Morning Run" in result_names
    assert len(results) == 2  # "Morning Run" and "Steady ergometer run" in description
    print("DONE: name match")


@pytest.mark.mytral
def test_search_activities_description_match(tmp_path: pathlib.Path):
    """Search should find activities whose description contains the query."""
    # GIVEN
    mytral_ds, user_id, dataset_name = _given_ds_with_activities(tmp_path)

    # WHEN
    results = _search(mytral_ds, user_id, dataset_name, "intervals")

    # THEN
    result_names = [a.name for a in results]
    print(f"Results for 'intervals': {result_names}")
    assert "Tempo Ride" in result_names
    assert len(results) == 1
    print("DONE: description match")


@pytest.mark.mytral
def test_search_activities_case_insensitive(tmp_path: pathlib.Path):
    """Search should be case-insensitive."""
    # GIVEN
    mytral_ds, user_id, dataset_name = _given_ds_with_activities(tmp_path)

    # WHEN
    results_lower = _search(mytral_ds, user_id, dataset_name, "morning run")
    results_upper = _search(mytral_ds, user_id, dataset_name, "MORNING RUN")
    results_mixed = _search(mytral_ds, user_id, dataset_name, "Morning Run")

    # THEN
    assert [a.name for a in results_lower] == [a.name for a in results_upper]
    assert [a.name for a in results_lower] == [a.name for a in results_mixed]
    assert len(results_lower) == 1
    assert results_lower[0].name == "Morning Run"
    print("DONE: case insensitive")


@pytest.mark.mytral
def test_search_activities_no_match(tmp_path: pathlib.Path):
    """Search should return empty list when no activity matches."""
    # GIVEN
    mytral_ds, user_id, dataset_name = _given_ds_with_activities(tmp_path)

    # WHEN
    results = _search(mytral_ds, user_id, dataset_name, "xyznotfound")

    # THEN
    print(f"Results for 'xyznotfound': {results}")
    assert results == []
    print("DONE: no match")


@pytest.mark.mytral
def test_search_activities_sorted_by_date_desc(tmp_path: pathlib.Path):
    """Search results should be sorted by date descending (latest first)."""
    # GIVEN
    mytral_ds, user_id, dataset_name = _given_ds_with_activities(tmp_path)

    # WHEN: 'run' matches Morning Run (2025-03-10) and Long Row description (2024-11-05)
    results = _search(mytral_ds, user_id, dataset_name, "run")

    # THEN: Morning Run (2025) should appear before Long Row (2024)
    assert len(results) == 2
    print(f"First: {results[0].name} ({results[0].when})")
    print(f"Second: {results[1].name} ({results[1].when})")
    first_date = (
        results[0].when_year,
        results[0].when_month,
        results[0].when_day,
    )
    second_date = (
        results[1].when_year,
        results[1].when_month,
        results[1].when_day,
    )
    assert first_date >= second_date

    print("DONE: sorted by date desc")
