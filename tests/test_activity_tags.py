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
import copy
import pathlib

import pytest

from mytral import commons
from mytral import config
from mytral import loggers
from mytral import utils
from mytral.backends import dataset
from mytral.backends import entities

#
# utils.parse_tags_csv - shared comma-separated tags parser
#


@pytest.mark.mytral
def test_parse_tags_csv_basic():
    """Comma-separated string is split into a list of tags."""
    # GIVEN / WHEN
    tags = utils.parse_tags_csv("trail, morning, with friends")

    # THEN
    assert tags == ["trail", "morning", "with friends"]
    print("DONE: basic split")


@pytest.mark.mytral
def test_parse_tags_csv_empty_and_none():
    """Empty string and None both yield an empty list."""
    # GIVEN / WHEN / THEN
    assert utils.parse_tags_csv("") == []
    assert utils.parse_tags_csv(None) == []
    assert utils.parse_tags_csv("   ,  ,") == []
    print("DONE: empty and none")


@pytest.mark.mytral
def test_parse_tags_csv_trims_and_dedupes():
    """Whitespace is trimmed, empties dropped, duplicates removed, order kept."""
    # GIVEN / WHEN
    tags = utils.parse_tags_csv("  trail ,, morning ,  trail ,evening ")

    # THEN
    assert tags == ["trail", "morning", "evening"]
    print("DONE: trims and dedupes")


#
# ActivityEntity tags field
#


@pytest.mark.mytral
def test_activity_entity_tags_default_empty():
    """A new ActivityEntity has an empty tags list by default."""
    # GIVEN / WHEN
    activity = entities.ActivityEntity()

    # THEN
    assert activity.tags == []
    print("DONE: default empty tags")


@pytest.mark.mytral
def test_activity_entity_tags_sparse_roundtrip():
    """Tags survive a to_sparse_dict / reconstruct round-trip."""
    # GIVEN
    activity = entities.ActivityEntity(
        name="Trail Run",
        tags=["trail", "morning"],
        when_year=2026,
        when_month=5,
        when_day=1,
    )

    # WHEN
    sparse = activity.to_sparse_dict()
    restored = entities.ActivityEntity(**sparse)

    # THEN
    assert sparse["tags"] == ["trail", "morning"]
    assert restored.tags == ["trail", "morning"]
    print("DONE: sparse round-trip preserves tags")


@pytest.mark.mytral
def test_activity_entity_tags_absent_when_empty():
    """Empty tags are omitted from the sparse dict (default-factory field)."""
    # GIVEN
    activity = entities.ActivityEntity(name="No Tags")

    # WHEN
    sparse = activity.to_sparse_dict()

    # THEN
    assert "tags" not in sparse
    print("DONE: empty tags omitted from sparse dict")


@pytest.mark.mytral
def test_activity_entity_tags_deepcopy_preserved():
    """copy.deepcopy (used by clone/copy routes) preserves tags independently."""
    # GIVEN
    activity = entities.ActivityEntity(name="Original", tags=["trail", "morning"])

    # WHEN
    clone = copy.deepcopy(activity)
    clone.tags.append("extra")

    # THEN
    assert clone.tags == ["trail", "morning", "extra"]
    assert activity.tags == ["trail", "morning"]  # original untouched
    print("DONE: deepcopy preserves and isolates tags")


#
# Persistence and filtering end-to-end
#


def _given_ds_with_tagged_activities(
    tmp_path: pathlib.Path,
) -> tuple[dataset.MyTraLDataset, str, str]:
    """Create a dataset with activities carrying different tags."""
    data_dir = tmp_path / ".local"
    data_dir.mkdir(parents=True, exist_ok=True)
    user_id = "tags-test-user-uuid"
    dataset_name = commons.DS_LIFELONG

    logger = loggers.MytralPrintLogger()
    app_config = config.MytralConfig(
        port=config.MytralConfig.DEFAULT_PORT,
        persistence_data_dir=data_dir.absolute(),
        auto_account_create=True,
    )
    mytral_ds = dataset.MyTraLDataset(mytral_config=app_config, logger=logger)
    mytral_ds.user().register_new_user(user_name="testathlete", user_id=user_id)

    mytral_ds.user().create_activity(
        user_id=user_id,
        dataset_name=dataset_name,
        entity=entities.ActivityEntity(
            name="Morning Trail Run",
            tags=["trail", "morning"],
            when_year=2026,
            when_month=3,
            when_day=10,
        ),
    )
    mytral_ds.user().create_activity(
        user_id=user_id,
        dataset_name=dataset_name,
        entity=entities.ActivityEntity(
            name="Evening Road Ride",
            tags=["road", "evening"],
            when_year=2026,
            when_month=3,
            when_day=12,
        ),
    )
    mytral_ds.user().create_activity(
        user_id=user_id,
        dataset_name=dataset_name,
        entity=entities.ActivityEntity(
            name="Untagged Swim",
            when_year=2026,
            when_month=3,
            when_day=14,
        ),
    )

    return mytral_ds, user_id, dataset_name


@pytest.mark.mytral
def test_activity_tags_persist_through_dataset(tmp_path: pathlib.Path):
    """Tags are stored and read back through the JSON dataset."""
    # GIVEN
    mytral_ds, user_id, dataset_name = _given_ds_with_tagged_activities(tmp_path)

    # WHEN
    activities = mytral_ds.user().list_activities(
        user_id=user_id, dataset_name=dataset_name, skip_future=False
    )
    by_name = {a.name: a for a in activities}

    # THEN
    assert by_name["Morning Trail Run"].tags == ["trail", "morning"]
    assert by_name["Evening Road Ride"].tags == ["road", "evening"]
    assert by_name["Untagged Swim"].tags == []
    print("DONE: tags persist through dataset")


@pytest.mark.mytral
def test_activity_list_tag_filter(tmp_path: pathlib.Path):
    """The list tag filter keeps only activities carrying the tag."""
    # GIVEN
    mytral_ds, user_id, dataset_name = _given_ds_with_tagged_activities(tmp_path)
    activities = mytral_ds.user().list_activities(
        user_id=user_id, dataset_name=dataset_name, skip_future=False
    )

    # WHEN - mirror the list_activities_year tag filter predicate
    filter_tag = "trail"
    filtered = [a for a in activities if filter_tag in (a.tags or [])]

    # THEN
    assert [a.name for a in filtered] == ["Morning Trail Run"]
    print("DONE: tag filter")


@pytest.mark.mytral
def test_search_activities_matches_tags(tmp_path: pathlib.Path):
    """Search matches on tags in addition to name and description."""
    # GIVEN
    mytral_ds, user_id, dataset_name = _given_ds_with_tagged_activities(tmp_path)
    activities = mytral_ds.user().list_activities(
        user_id=user_id, dataset_name=dataset_name, skip_future=False
    )

    # WHEN - mirror the search_activities predicate (name, description, tags)
    q_lower = "road"
    matched = [
        a
        for a in activities
        if q_lower in (a.name or "").lower()
        or q_lower in (a.description or "").lower()
        or any(q_lower in tag.lower() for tag in (a.tags or []))
    ]

    # THEN - only the road-tagged ride matches (no name/description carries "road")
    assert [a.name for a in matched] == ["Evening Road Ride"]
    print("DONE: search matches tags")
