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
from mytral import settings as user_settings
from mytral.backends import entities
from tests import _given


@pytest.mark.mytral
def test_activity_outfit_persistence(tmp_path: pathlib.Path):
    """Test that outfit field is correctly persisted in ActivityEntity."""
    # GIVEN
    test_config = config.MytralConfig(
        port=config.MytralConfig.DEFAULT_PORT,
        persistence_data_dir=tmp_path.absolute(),
        auto_account_create=True,
    )
    ds, user_ds, profile = _given.given_test(
        test_config=test_config, user_id="test-user"
    )
    user_id = profile.user_id
    dataset_name = commons.DS_LIFELONG

    outfit_key = "winter-running-outfit"
    activity = entities.ActivityEntity(
        name="Running in snow", activity_type_key="run", outfit=outfit_key
    )

    # WHEN
    created_activity = user_ds.create_activity(
        user_id=user_id, dataset_name=dataset_name, entity=activity
    )

    # THEN
    assert created_activity.outfit == outfit_key

    # WHEN
    fetched_activity = user_ds.get_activity(
        user_id=user_id, dataset_name=dataset_name, key=created_activity.key
    )

    # THEN
    assert fetched_activity.outfit == outfit_key
    print(f"DONE: activity outfit '{fetched_activity.outfit}' persisted correctly")


@pytest.mark.mytral
def test_activity_outfit_update(tmp_path: pathlib.Path):
    """Test that outfit field can be updated in ActivityEntity."""
    # GIVEN
    test_config = config.MytralConfig(
        port=config.MytralConfig.DEFAULT_PORT,
        persistence_data_dir=tmp_path.absolute(),
        auto_account_create=True,
    )
    ds, user_ds, profile = _given.given_test(
        test_config=test_config, user_id="test-user"
    )
    user_id = profile.user_id
    dataset_name = commons.DS_LIFELONG

    activity = entities.ActivityEntity(
        name="Running", activity_type_key="run", outfit="summer-outfit"
    )
    created_activity = user_ds.create_activity(
        user_id=user_id, dataset_name=dataset_name, entity=activity
    )

    # WHEN
    created_activity.outfit = "autumn-outfit"
    updated_activity = user_ds.update_activity(
        user_id=user_id, dataset_name=dataset_name, entity=created_activity
    )

    # THEN
    assert updated_activity.outfit == "autumn-outfit"

    # WHEN
    fetched_activity = user_ds.get_activity(
        user_id=user_id, dataset_name=dataset_name, key=created_activity.key
    )

    # THEN
    assert fetched_activity.outfit == "autumn-outfit"
    print(
        f"DONE: activity outfit update to '{fetched_activity.outfit}' persisted "
        f"correctly"
    )


@pytest.mark.mytral
def test_outfits_stats(tmp_path: pathlib.Path):
    """Test outfit statistics calculation."""
    # GIVEN
    test_config = config.MytralConfig(
        port=config.MytralConfig.DEFAULT_PORT,
        persistence_data_dir=tmp_path.absolute(),
        auto_account_create=True,
    )
    ds, user_ds, profile = _given.given_test(
        test_config=test_config, user_id="test-user"
    )
    user_id = profile.user_id
    dataset_name = commons.DS_LIFELONG

    outfit = user_settings.Outfit(name="Warm Outfit", activity_type="run")
    user_ds.create_outfit(user_id=user_id, outfit=outfit)
    outfit_key = outfit.key

    # create activities with this outfit
    for i in range(3):
        activity = entities.ActivityEntity(
            name=f"Run {i}",
            activity_type_key="run",
            outfit=outfit_key,
            when_year=2026,
            when_month=5,
            when_day=i + 1,
        )
        user_ds.create_activity(
            user_id=user_id, dataset_name=dataset_name, entity=activity
        )

    # WHEN
    stats_obj = user_ds.outfits_stats(user_id=user_id, dataset_name=dataset_name)
    outfit_stat = stats_obj.stats(outfit_key)

    # THEN
    assert outfit_stat is not None
    assert outfit_stat.count == 3
    print(f"DONE: outfit stats count is {outfit_stat.count}")


@pytest.mark.mytral
def test_outfits_list_sorting_and_counting(tmp_path: pathlib.Path):
    """Test that list_outfits correctly counts and sorts outfits."""
    # GIVEN
    test_config = config.MytralConfig(
        port=config.MytralConfig.DEFAULT_PORT,
        persistence_data_dir=tmp_path.absolute(),
        auto_account_create=True,
    )
    ds, user_ds, profile = _given.given_test(
        test_config=test_config, user_id="test-user"
    )
    user_id = profile.user_id
    dataset_name = commons.DS_LIFELONG

    o1 = user_settings.Outfit(name="Outfit 1", activity_type="run")
    user_ds.create_outfit(user_id=user_id, outfit=o1)
    o2 = user_settings.Outfit(name="Outfit 2", activity_type="run")
    user_ds.create_outfit(user_id=user_id, outfit=o2)

    # o1 used twice, o2 once
    for i in range(2):
        user_ds.create_activity(
            user_id=user_id,
            dataset_name=dataset_name,
            entity=entities.ActivityEntity(
                activity_type_key="run",
                outfit=o1.key,
                when_year=2026,
                when_month=1,
                when_day=1,
            ),
        )
    user_ds.create_activity(
        user_id=user_id,
        dataset_name=dataset_name,
        entity=entities.ActivityEntity(
            activity_type_key="run",
            outfit=o2.key,
            when_year=2026,
            when_month=1,
            when_day=2,
        ),
    )

    # WHEN
    outfits = user_ds.list_outfits(user_id=user_id, dataset_name=dataset_name)

    # THEN
    assert outfits.outfits_by_key[o1.key].count == 2
    assert outfits.outfits_by_key[o2.key].count == 1
    print("DONE: list_outfits correctly counted usage")
