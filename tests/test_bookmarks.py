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
import pathlib

import pytest

from mytral import commons
from mytral import config
from mytral.backends import entities
from tests import _given


def _given_config(tmp_path: pathlib.Path) -> config.MytralConfig:
    return config.MytralConfig(
        port=config.MytralConfig.DEFAULT_PORT,
        persistence_data_dir=tmp_path.absolute(),
        auto_account_create=True,
    )


def _given_activity(
    user_ds, user_id, dataset_name, name: str
) -> entities.ActivityEntity:
    return user_ds.create_activity(
        user_id=user_id,
        dataset_name=dataset_name,
        entity=entities.ActivityEntity(name=name, activity_type_key="run"),
    )


@pytest.mark.mytral
def test_bookmark_add_and_list(tmp_path: pathlib.Path):
    """Test that bookmarking an activity makes it appear in list_bookmarks."""
    # GIVEN
    ds, user_ds, profile = _given.given_test(
        test_config=_given_config(tmp_path), user_id="test-user"
    )
    user_id = profile.user_id
    dataset_name = commons.DS_LIFELONG

    a1 = _given_activity(user_ds, user_id, dataset_name, "Run 1")
    a2 = _given_activity(user_ds, user_id, dataset_name, "Run 2")

    # WHEN
    user_ds.create_bookmark(user_id=user_id, activity_key=a1.key)

    # THEN
    bookmarks = user_ds.list_bookmarks(user_id=user_id)
    assert bookmarks.activity_keys == [a1.key]
    assert bookmarks.is_bookmarked(a1.key) is True
    assert bookmarks.is_bookmarked(a2.key) is False
    print("DONE: bookmarked activity appears in list_bookmarks")


@pytest.mark.mytral
def test_bookmark_add_idempotent(tmp_path: pathlib.Path):
    """Test that bookmarking the same activity twice does not duplicate it."""
    # GIVEN
    ds, user_ds, profile = _given.given_test(
        test_config=_given_config(tmp_path), user_id="test-user"
    )
    user_id = profile.user_id
    dataset_name = commons.DS_LIFELONG

    a1 = _given_activity(user_ds, user_id, dataset_name, "Run 1")

    # WHEN
    user_ds.create_bookmark(user_id=user_id, activity_key=a1.key)
    user_ds.create_bookmark(user_id=user_id, activity_key=a1.key)

    # THEN
    bookmarks = user_ds.list_bookmarks(user_id=user_id)
    assert bookmarks.activity_keys == [a1.key]
    print("DONE: bookmarking twice did not duplicate the entry")


@pytest.mark.mytral
def test_bookmark_delete(tmp_path: pathlib.Path):
    """Test deleting a bookmark, including a no-op delete of an absent key."""
    # GIVEN
    ds, user_ds, profile = _given.given_test(
        test_config=_given_config(tmp_path), user_id="test-user"
    )
    user_id = profile.user_id
    dataset_name = commons.DS_LIFELONG

    a1 = _given_activity(user_ds, user_id, dataset_name, "Run 1")
    a2 = _given_activity(user_ds, user_id, dataset_name, "Run 2")
    user_ds.create_bookmark(user_id=user_id, activity_key=a1.key)
    user_ds.create_bookmark(user_id=user_id, activity_key=a2.key)

    # WHEN
    user_ds.delete_bookmark(user_id=user_id, activity_key=a1.key)

    # THEN
    bookmarks = user_ds.list_bookmarks(user_id=user_id)
    assert bookmarks.activity_keys == [a2.key]

    # WHEN deleting a non-bookmarked key - no exception raised
    user_ds.delete_bookmark(user_id=user_id, activity_key="does-not-exist")

    # THEN
    bookmarks = user_ds.list_bookmarks(user_id=user_id)
    assert bookmarks.activity_keys == [a2.key]
    print("DONE: bookmark deletion and no-op delete work correctly")


@pytest.mark.mytral
def test_bookmark_move_up_down(tmp_path: pathlib.Path):
    """Test reordering bookmarks with move up/down, including boundary no-ops."""
    # GIVEN
    ds, user_ds, profile = _given.given_test(
        test_config=_given_config(tmp_path), user_id="test-user"
    )
    user_id = profile.user_id
    dataset_name = commons.DS_LIFELONG

    a = _given_activity(user_ds, user_id, dataset_name, "A")
    b = _given_activity(user_ds, user_id, dataset_name, "B")
    c = _given_activity(user_ds, user_id, dataset_name, "C")
    for activity in (a, b, c):
        user_ds.create_bookmark(user_id=user_id, activity_key=activity.key)

    # WHEN moving the middle bookmark up
    user_ds.move_bookmark(user_id=user_id, activity_key=b.key, direction="up")

    # THEN
    assert user_ds.list_bookmarks(user_id=user_id).activity_keys == [
        b.key,
        a.key,
        c.key,
    ]

    # WHEN moving it back down once
    user_ds.move_bookmark(user_id=user_id, activity_key=b.key, direction="down")

    # THEN back to original order
    assert user_ds.list_bookmarks(user_id=user_id).activity_keys == [
        a.key,
        b.key,
        c.key,
    ]

    # WHEN moving the first item up / last item down - both are no-ops
    user_ds.move_bookmark(user_id=user_id, activity_key=a.key, direction="up")
    user_ds.move_bookmark(user_id=user_id, activity_key=c.key, direction="down")

    # THEN
    assert user_ds.list_bookmarks(user_id=user_id).activity_keys == [
        a.key,
        b.key,
        c.key,
    ]
    print("DONE: bookmark move up/down reorders correctly with boundary no-ops")


@pytest.mark.mytral
def test_bookmark_persistence_across_reload(tmp_path: pathlib.Path):
    """Test that bookmark order survives a JSON round-trip via a fresh dataset."""
    # GIVEN
    test_config = _given_config(tmp_path)
    ds, user_ds, profile = _given.given_test(
        test_config=test_config, user_id="test-user"
    )
    user_id = profile.user_id
    dataset_name = commons.DS_LIFELONG

    a = _given_activity(user_ds, user_id, dataset_name, "A")
    b = _given_activity(user_ds, user_id, dataset_name, "B")
    user_ds.create_bookmark(user_id=user_id, activity_key=a.key)
    user_ds.create_bookmark(user_id=user_id, activity_key=b.key)

    # WHEN a fresh dataset instance reads from the same data directory
    _, reloaded_user_ds = _given.given_ds(test_config=test_config)

    # THEN
    assert reloaded_user_ds.list_bookmarks(user_id=user_id).activity_keys == [
        a.key,
        b.key,
    ]
    print("DONE: bookmark order survives a JSON round-trip")


@pytest.mark.mytral
def test_bookmark_self_heals_missing_file(tmp_path: pathlib.Path):
    """Test that accounts predating the bookmarks feature self-heal on access.

    Regression test: pre-existing accounts have no `user-activity-bookmarks.json`
    on disk, since it is only bootstrapped by `register_new_user`. Accessing
    bookmarks for such an account must not raise - it must create the file.
    """
    # GIVEN a registered user whose bookmarks file is then removed, simulating
    # an account that existed before the bookmarks feature was introduced
    test_config = _given_config(tmp_path)
    ds, user_ds, profile = _given.given_test(
        test_config=test_config, user_id="test-user"
    )
    user_id = profile.user_id
    user_ds.user_bookmarks_path(user_id).unlink()

    # WHEN a fresh dataset instance (empty cache) accesses list_bookmarks
    _, reloaded_user_ds = _given.given_ds(test_config=test_config)
    bookmarks = reloaded_user_ds.list_bookmarks(user_id=user_id)

    # THEN no exception is raised, bookmarks are empty, and the file is recreated
    assert bookmarks.activity_keys == []
    assert reloaded_user_ds.user_bookmarks_path(user_id).exists()
    print("DONE: missing bookmarks file self-heals on access")


@pytest.mark.mytral
def test_bookmark_file_name(tmp_path: pathlib.Path):
    """Test the persisted bookmarks file name and its bootstrap content."""
    # GIVEN
    ds, user_ds, profile = _given.given_test(
        test_config=_given_config(tmp_path), user_id="test-user"
    )
    user_id = profile.user_id

    # WHEN
    bookmarks_path = user_ds.user_bookmarks_path(user_id)

    # THEN
    assert bookmarks_path.name == "user-activity-bookmarks.json"
    assert bookmarks_path.exists()
    assert bookmarks_path.read_text().strip() == "[]"
    print("DONE: bookmarks file is bootstrapped with the expected name and content")


@pytest.mark.mytral
def test_bookmark_removed_on_activity_delete(tmp_path: pathlib.Path):
    """Test that deleting an activity removes its bookmark too."""
    # GIVEN
    ds, user_ds, profile = _given.given_test(
        test_config=_given_config(tmp_path), user_id="test-user"
    )
    user_id = profile.user_id
    dataset_name = commons.DS_LIFELONG

    a1 = _given_activity(user_ds, user_id, dataset_name, "Run 1")
    a2 = _given_activity(user_ds, user_id, dataset_name, "Run 2")
    user_ds.create_bookmark(user_id=user_id, activity_key=a1.key)
    user_ds.create_bookmark(user_id=user_id, activity_key=a2.key)

    # WHEN
    user_ds.delete_activity(user_id=user_id, dataset_name=dataset_name, key=a1.key)

    # THEN
    bookmarks = user_ds.list_bookmarks(user_id=user_id)
    assert bookmarks.activity_keys == [a2.key]
    print("DONE: deleting a bookmarked activity removes its stale bookmark entry")
