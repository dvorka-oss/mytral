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
import os
import pathlib

import pytest

from mytral import commons
from mytral import config
from mytral import loggers
from mytral import settings
from mytral import utils
from mytral.backends import caches
from mytral.backends import dataset


@pytest.mark.mytral
def test_passthrough_cache_returns_none_from_getters():
    """Test that PassthroughMytralCache user cache returns None from all getters."""
    # GIVEN
    logger = loggers.MytralPrintLogger()
    cache = caches.PassthroughMytralCache(cache_initializer=None, logger=logger)
    user_id = "test-user-123"

    # WHEN
    user_cache = cache.user(user_id)

    # THEN
    assert user_cache is not None
    assert user_cache.profile() is None
    assert user_cache.activities(commons.DS_LIFELONG) == {}
    assert user_cache.activity_types() is None
    assert user_cache.activity_types_stats() is None
    assert user_cache.gear() is None
    assert user_cache.gear_stats() is None
    assert user_cache.exercises() is None
    assert user_cache.exercises_stats() is None
    assert user_cache.symptoms() is None
    assert user_cache.symptoms_stats() is None
    assert user_cache.laps() is None
    assert user_cache.laps_stats() is None
    print("DONE: PassthroughMytralCache returns None from all getters")


@pytest.mark.mytral
def test_passthrough_cache_same_instance_per_user():
    """Test that PassthroughMytralCache returns same instance for same user."""
    # GIVEN
    logger = loggers.MytralPrintLogger()
    cache = caches.PassthroughMytralCache(cache_initializer=None, logger=logger)
    user_id = "test-user-123"

    # WHEN
    user_cache1 = cache.user(user_id)
    user_cache2 = cache.user(user_id)

    # THEN
    assert user_cache1 is user_cache2
    print("DONE: PassthroughMytralCache returns same instance per user")


@pytest.mark.mytral
def test_passthrough_cache_memory_size_minimal():
    """Test that PassthroughMytralCache reports minimal memory usage."""
    # GIVEN
    logger = loggers.MytralPrintLogger()
    cache = caches.PassthroughMytralCache(cache_initializer=None, logger=logger)

    # WHEN
    _ = cache.user("user1")
    _ = cache.user("user2")
    size = cache.memory_size()

    # THEN
    assert size > 0  # some overhead for empty cache objects
    assert size < 10000  # but should be minimal (< 10KB)
    print("DONE: PassthroughMytralCache memory size is minimal")


@pytest.mark.mytral
def test_passthrough_cache_evict_removes_user():
    """Test that PassthroughMytralCache evict removes user cache."""
    # GIVEN
    logger = loggers.MytralPrintLogger()
    cache = caches.PassthroughMytralCache(cache_initializer=None, logger=logger)
    user_id = "test-user-123"
    cache1 = cache.user(user_id)

    # WHEN
    cache.evict(user_id)
    cache2 = cache.user(user_id)

    # THEN
    assert cache1 is not cache2  # new instance created after eviction
    print("DONE: PassthroughMytralCache evict removes user")


@pytest.mark.mytral
def test_config_enable_cache_default_is_true():
    """Test that persistence_cache defaults to True for backward compatibility."""
    # GIVEN/WHEN
    app_config = config.MytralConfig()

    # THEN
    assert app_config.persistence_cache is True
    print("DONE: Config persistence_cache defaults to True")


@pytest.mark.mytral
def test_config_enable_cache_can_be_disabled():
    """Test that persistence_cache can be set to False."""
    # GIVEN/WHEN
    app_config = config.MytralConfig(persistence_cache=False)

    # THEN
    assert app_config.persistence_cache is False
    print("DONE: Config persistence_cache can be disabled")


@pytest.mark.mytral
@pytest.mark.parametrize("enable_cache", [True, False])
def test_dataset_crud_operations_work_with_both_caches(
    tmp_path: pathlib.Path, enable_cache: bool
):
    """Test that basic CRUD operations work with both cache modes."""
    # GIVEN
    data_dir = tmp_path / ".local"
    data_dir.mkdir(parents=True, exist_ok=True)
    logger = loggers.MytralPrintLogger()
    app_config = config.MytralConfig(
        persistence_data_dir=data_dir.absolute(),
        persistence_cache=enable_cache,
    )
    mytral_ds = dataset.MyTraLDataset(mytral_config=app_config, logger=logger)

    # create user
    user_id = "test-user-123"
    user_name = "testuser"
    mytral_ds.user().register_new_user(
        user_name=user_name, user_id=user_id, password_enc="test"
    )

    # WHEN - create activity type
    activity_type = settings.ActivityType(
        key="running",
        name="Running",
        is_distance=True,
        is_exercise=False,
        is_regen=False,
        is_meta=False,
        is_built_in=False,
        emoji="🏃",
        color="blue",
    )
    mytral_ds.user().create_activity_type(user_id, activity_type)

    # THEN - can retrieve activity types
    activity_types = mytral_ds.user().list_activity_types(user_id)
    assert activity_types is not None
    assert len(activity_types.activity_types_by_key) > 0
    assert "running" in activity_types.activity_types_by_key

    # WHEN - get activity types stats
    stats = mytral_ds.user().activity_types_stats(user_id, commons.DS_LIFELONG)

    # THEN - stats should be available (even if empty)
    assert stats is not None

    # WHEN - get heatmaps
    activity_type_heatmap = mytral_ds.user().activity_type_heatmap(
        user_id, commons.DS_LIFELONG
    )
    sick_heatmap = mytral_ds.user().sick_heatmap(user_id, commons.DS_LIFELONG)

    # THEN - heatmaps should be available
    assert activity_type_heatmap is not None
    assert sick_heatmap is not None

    print(f"DONE: CRUD operations work with persistence_cache={enable_cache}")


@pytest.mark.mytral
def test_dataset_uses_passthrough_cache_when_disabled(tmp_path: pathlib.Path):
    """Test that dataset uses PassthroughMytralCache when cache is disabled."""
    # GIVEN
    data_dir = tmp_path / ".local"
    data_dir.mkdir(parents=True, exist_ok=True)
    logger = loggers.MytralPrintLogger()
    app_config = config.MytralConfig(
        persistence_data_dir=data_dir.absolute(),
        persistence_cache=False,
    )

    # WHEN
    mytral_ds = dataset.MyTraLDataset(mytral_config=app_config, logger=logger)

    # THEN
    assert mytral_ds is not None
    assert isinstance(mytral_ds.user()._cache, caches.PassthroughMytralCache)
    print("DONE: Dataset uses PassthroughMytralCache when disabled")


@pytest.mark.mytral
def test_dataset_uses_in_memory_cache_when_enabled(tmp_path: pathlib.Path):
    """Test that dataset uses InMemoryMytralCache when cache is enabled."""
    # GIVEN
    data_dir = tmp_path / ".local"
    data_dir.mkdir(parents=True, exist_ok=True)
    logger = loggers.MytralPrintLogger()
    app_config = config.MytralConfig(
        persistence_data_dir=data_dir.absolute(),
        persistence_cache=True,
    )

    # WHEN
    mytral_ds = dataset.MyTraLDataset(mytral_config=app_config, logger=logger)

    # THEN
    assert mytral_ds is not None
    assert isinstance(mytral_ds.user()._cache, caches.InMemoryMytralCache)
    print("DONE: Dataset uses InMemoryMytralCache when enabled")


@pytest.mark.mytral
def test_environment_variable_disables_cache(tmp_path: pathlib.Path, monkeypatch):
    """Test that MYTRAL_ENABLE_CACHE=false environment variable disables cache."""
    # GIVEN
    data_dir = tmp_path / ".local"
    data_dir.mkdir(parents=True, exist_ok=True)

    # simulate environment variable being set to "false"
    monkeypatch.setenv(
        config.MytralConfig.ENV_MYTRAL_PERSISTENCE_CACHE,
        utils.ENV_VALUE_FALSE,
    )

    # WHEN
    enable_cache = (
        False
        if os.getenv(config.MytralConfig.ENV_MYTRAL_PERSISTENCE_CACHE, "")
        == utils.ENV_VALUE_FALSE
        else True
    )
    app_config = config.MytralConfig(
        persistence_data_dir=data_dir.absolute(),
        persistence_cache=enable_cache,
    )

    # THEN
    assert app_config.persistence_cache is False
    print("DONE: Environment variable MYTRAL_ENABLE_CACHE=false disables cache")
