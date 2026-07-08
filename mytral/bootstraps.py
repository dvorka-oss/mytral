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

"""Bootstrap related code."""

import uuid

from mytral import commons
from mytral import loggers
from mytral import security
from mytral.backends import dataset


def bootstrap_default_desktop_user(
    ds: dataset.UserDataset, logger: loggers.MytralStructLogger
) -> None:
    """Auto-create the default athlete user on the first DESKTOP boot.

    Smooth first start: DESKTOP incarnation with no user profile on disk yet
    gets a default user (with auto-login enabled) so that it can go straight
    to the dashboard, without sign-up/login. Installations which already have
    at least one profile are left untouched.

    Parameters
    ----------
    ds : dataset.UserDataset
        User dataset used to check for existing profiles and register the
        default user.
    logger : loggers.MytralStructLogger
        Logger used to record that the default user was created.

    """
    if ds.list_profiles():
        return

    user_id = str(uuid.uuid4())
    ds.register_new_user(
        user_name=commons.DEFAULT_DESKTOP_USER_NAME,
        user_id=user_id,
        user_display_name=commons.DEFAULT_DESKTOP_USER_DISPLAY_NAME,
        password_enc=security.hash_password(commons.DEFAULT_DESKTOP_USER_PASSWORD),
        auto_login=True,
    )
    logger.info(
        "Bootstrapped default desktop user",
        user_name=commons.DEFAULT_DESKTOP_USER_NAME,
        user_id=user_id,
    )
