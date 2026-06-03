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
import random
import shutil

import lorem

from mytral import config
from mytral import loggers
from mytral import security
from mytral import settings
from mytral.backends import dataset
from mytral.backends.datasets import dataset_json

# environment variables
ENV_DIR_MYTRAL_TEST_DATA = "MYTRAL_TEST_DATA_DIR"

# constants
TEST_USER = "test_user"
TEST_USER_HOME = pathlib.Path.home()
TEST_DATA_DIR = pathlib.Path(__file__).parent / "data"
TEST_DATA_FIT_DIR = TEST_DATA_DIR / "import" / "fit"
TEST_DATA_PARQUET_DIR = TEST_DATA_DIR / "import" / "parquet-for-fit"
TEST_DATA_STRAVA_ARCHIVE = TEST_DATA_DIR / "import" / "strava-archive"

TEST_DS_ROOT = pathlib.Path(__file__).parent.parent.parent.parent / "datasets-test"
TEST_DS_AVATARS = TEST_DS_ROOT / "avatars"
TEST_DS_FITNESS = TEST_DS_ROOT / "fit"
TEST_DS_GPX = TEST_DS_ROOT / "gpx"
TEST_DS_PHOTOS = TEST_DS_ROOT / "photos"
TEST_DS_STRAVA_USER_ARCHIVE = TEST_DS_ROOT / "strava" / "user-archive"

EXT_TEST_DATA_ROOT = (
    TEST_USER_HOME / "p" / "mytral" / "git" / "my-training-log-data-dev"
)

#
# commons
#


def given_lorem_ipsum() -> str:
    """Generate a random Lorem Ipsum paragraph.

    Returns
    -------
    str
        Random paragraph of Lorem Ipsum text.
    """

    return lorem.paragraph()


def given_markdown_ipsum(title: bool = False) -> str:
    """Generate a random Markdown-formatted text.

    Returns
    -------
    str
        Random text with Markdown elements (headers, bold, lists).
    """

    lines = [
        f"# {lorem.sentence()}" if title else "",
        "",
        lorem.paragraph(),
        "",
        f"**{lorem.sentence()}**",
        "",
        f"* {lorem.sentence()}",
        f"* {lorem.sentence()}",
        f"* {lorem.sentence()}",
        "",
        lorem.paragraph(),
        "",
        f"> {lorem.sentence()}",
        "",
        f"Checkout [MyTraL](https://mytral.fitness) - {lorem.sentence()}",
    ]
    return "\n".join(lines)


#
# GIVEN
#


def given_ds(
    test_config: config.MytralConfig,
) -> tuple[dataset.MyTraLDataset, dataset_json.JsonUsersDataset]:
    # TODO fixture w/ parameters
    # - https://stackoverflow.com/questions/18011902/
    #   how-to-pass-a-parameter-to-a-fixture-function-in-pytest

    ds = dataset.MyTraLDataset(
        mytral_config=test_config, logger=loggers.MytralPrintLogger()
    )

    return ds, ds.user()


def given_test(
    test_config: config.MytralConfig,
    user_id: str,
    user_name: str = "",
    user_display_name: str = "",
    user_password: str = "test",
) -> tuple[dataset.MyTraLDataset, dataset_json.JsonUsersDataset, settings.UserProfile]:
    ds, user_ds = given_ds(test_config=test_config)

    user_id = user_id or TEST_USER
    user_ds.register_new_user(
        user_id=user_id,
        user_name=user_name or user_id,
        user_display_name=user_display_name,
        password_enc=security.hash_password(user_password),
    )
    profile = user_ds.profile(user_id=user_id)

    return ds, user_ds, profile


def given_test_datasets(
    profile: settings.UserProfile,
    ds: dataset_json.JsonUsersDataset,
    datasets: list[pathlib.Path],
):
    """Prepare test datasets for given user profile by copying them."""
    for d in datasets:
        if not d.exists():
            raise FileNotFoundError(f"Missing source dataset: {d}")

        profile.dataset_names.append(d.stem)
        shutil.copy(src=d, dst=ds.user_dir(user_id=profile.user_id) / d.name)

    ds.update_profile(profile)


def given_random_name(length=6):
    """Generates a pronounceable string of a fixed length (must be even)."""
    if length % 2 != 0:
        raise ValueError("Length must be an even number for C-V structure.")

    consonants = "bcdfghjklmnpqrstvwxyz"
    vowels = "aeiou"

    name = []
    # force C-V-C-V-C-V pattern
    for i in range(length // 2):
        name.append(random.choice(consonants))
        name.append(random.choice(vowels))

    return "".join(name)
