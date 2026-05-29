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
import datetime
import pathlib

import pandas as pd
import pytest

from mytral import commons
from mytral.ml import sick_model


@pytest.mark.skip(
    "MyTraL model - not a test: create dataset, train and interpret model"
)
@pytest.mark.mytral
def test_dataset(tmp_path: pathlib.Path):
    """Create a dataset, train an ML model and interpret it."""

    #
    # GIVEN
    #
    raw_ds_path = (
        pathlib.Path()
        / "data"
        / commons.DEFAULT_USER_NAME
        / f"{commons.DATASET_NAME_MAIN}.json"
    )
    is_dataset_small = True

    #
    # WHEN
    #
    model = sick_model.SickModel(
        mytral_dataset_path=raw_ds_path, is_dataset_small=is_dataset_small
    )
    model.dataset()
    model.train()
    model.interpret()

    #
    # THEN
    #

    # try the model for today
    x_try_dict = {
        "sick_lag_1": [1.0],
        "sick_lag_2": [0.0],
        "sick_lag_3": [0.0],
        "sick_lag_4": [0.0],
        "sick_lag_5": [0.0],
    }
    if not is_dataset_small:
        x_try_dict.update(
            {
                "year_day": [datetime.datetime.now().timetuple().tm_yday],
                "month": [9],
                "day": [20],
            }
        )
    y_hat = model.predict(pd.DataFrame.from_dict(x_try_dict))

    print(f"\nPrediction for today:\n{x_try_dict}\n->\n{y_hat}")
