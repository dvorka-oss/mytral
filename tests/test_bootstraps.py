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

from mytral import bootstraps
from mytral import commons
from mytral import config
from mytral import loggers
from mytral import security
from mytral.backends import dataset


def _given_desktop_ds(
    tmp_path: pathlib.Path,
) -> tuple[dataset.MyTraLDataset, dataset.UserDataset]:
    app_config = config.MytralConfig(
        port=config.MytralConfig.DEFAULT_PORT,
        persistence_data_dir=tmp_path.absolute(),
        incarnation=config.MytralIncarnation.DESKTOP,
    )
    mytral_ds = dataset.MyTraLDataset(
        mytral_config=app_config, logger=loggers.MytralPrintLogger()
    )
    return mytral_ds, mytral_ds.user()


@pytest.mark.mytral
def test_bootstrap_default_desktop_user_creates_athlete_when_no_users(
    tmp_path: pathlib.Path,
):
    # GIVEN a fresh desktop installation with no user profile at all
    _, user_ds = _given_desktop_ds(tmp_path)
    logger = loggers.MytralPrintLogger()
    assert user_ds.list_profiles() == []

    # WHEN
    bootstraps.bootstrap_default_desktop_user(ds=user_ds, logger=logger)

    # THEN - the default athlete user is auto-created w/ auto-login enabled
    profile_names = user_ds.list_profile_names()
    assert profile_names.keys() == {commons.DEFAULT_DESKTOP_USER_NAME}

    user_id = profile_names[commons.DEFAULT_DESKTOP_USER_NAME]
    profile = user_ds.profile(user_id)
    assert profile.display_name == commons.DEFAULT_DESKTOP_USER_DISPLAY_NAME
    assert profile.auto_login is True

    print("DONE: bootstrap creates the default desktop athlete user")


@pytest.mark.mytral
def test_bootstrap_default_desktop_user_is_noop_when_user_exists(
    tmp_path: pathlib.Path,
):
    # GIVEN a desktop installation which already has a user
    _, user_ds = _given_desktop_ds(tmp_path)
    logger = loggers.MytralPrintLogger()
    user_ds.register_new_user(
        user_name="already-here",
        user_id="existing-user-id",
        password_enc=security.hash_password("test-password"),
    )

    # WHEN
    bootstraps.bootstrap_default_desktop_user(ds=user_ds, logger=logger)

    # THEN - no default athlete user is added
    profile_names = user_ds.list_profile_names()
    assert profile_names.keys() == {"already-here"}

    print("DONE: bootstrap is a no-op when a user profile already exists")
