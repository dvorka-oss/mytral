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
import json
import pathlib
from datetime import date
from datetime import timedelta

import pandas as pd

from mytral import commons
from mytral import loggers
from mytral import persistences

# TODO cross validation


class SickModel:
    """Machine learning model for predicting user's sickness:

    - predicts whether probability of user's sickness tomorrow

    Technical aspects:

    - time series model with lag features
    - XGBoost regressor

    """

    F_YEAR_DAY = "year_day"
    F_MONTH = "month"
    F_DAY = "day"

    TARGET = "sick"

    FEATURES = [F_YEAR_DAY, F_MONTH, F_DAY]

    def __init__(
        self,
        mytral_dataset_path: pathlib.Path,
        is_dataset_small: bool = True,
        logger=None,
    ) -> None:
        """Initialize the model with the dataset path.

        Parameters
        ----------
        mytral_dataset_path : pathlib.Path
            Path to the dataset in MyTraL format (JSON).
        is_dataset_small : bool
            Whether the dataset is small - not enough data for training over the years.
            Only lag features are used if the dataset is small.

        """
        if not mytral_dataset_path.exists():
            raise FileNotFoundError(f"Dataset file {mytral_dataset_path} not found.")

        # dataset ~ RAW data in MyTraL format ~ source for building the data frame
        self.ds_raw_path = mytral_dataset_path
        self.model_dir_path = self.ds_raw_path.parent / "models"
        self.model_dir_path.mkdir(parents=True, exist_ok=True)

        self.ds_stats: dict[str, list] = {
            # years with at least one activity_type_key activity or sickness
            "active_years": [],
        }

        # data frame ~ processed data used to train the model
        self.df = None
        self.df_train = None
        self.df_test = None

        # drop features if the dataset is small
        self.drop_df_features = [SickModel.TARGET]
        if is_dataset_small:
            self.drop_df_features.extend(
                [SickModel.F_YEAR_DAY, SickModel.F_MONTH, SickModel.F_DAY]
            )

        # REGRESSION model
        self.model = None
        self.model_features: list = []
        self.model_feature_importance: dict = {}

        self.interpret_metrics: dict = {}

        self.logger = logger or loggers.MytralStructLogger()

    @staticmethod
    def _date_as_key(year: int, month: int, day: int) -> str:
        return f"{year}-{month:0>2}-{day:0>2}"

    def _dataset_stats(self, activities_json: dict) -> list:
        """Calculate dataset statistics.

        Parameters
        ----------
        activities_json : dict
            Activities in the dataset (map: key -> activity).

        Returns
        -------
        list
            Serialized dates when the user was sick.

        """
        if not activities_json:
            raise ValueError("Empty activities in the dataset.")

        # sick list ~ dates when sick: ["<year>-<month>-<day>", ...]
        sick_list = activities_json.get("sick", [])

        # calculate statistics
        for a in activities_json.values():
            year = a.get("when_year")
            if a.get("activity_type_key") in [commons.AT_COMMENT]:
                continue

            if a.get("activity_type_key") in [commons.AT_SICK, commons.AT_INJURED]:
                sick_list.append(
                    SickModel._date_as_key(
                        year=year, month=a.get("when_month"), day=a.get("when_day")
                    )
                )

            if year not in self.ds_stats["active_years"]:
                self.ds_stats["active_years"].append(year)
        self.ds_stats["active_years"].sort()

        self.logger.info(f" Dataset statistics:\n{json.dumps(self.ds_stats, indent=2)}")

        return sick_list

    def dataset(self):
        """Prepare the dataset for training the model:

        - time series dataset:
          - group: year
            - Consider seasonal sicknesses and injuries.
        - target:
            - sick
        - lag features:
            - sick_lag_1 ... was the user sick yesterday? [0.0, 1.0]
            - ...
            - sick_lag_5 ... was the user sick 5 days ago? [0.0, 1.0]
        - features - NOT USED when NOT enough data ~ not enough years:
            - year_day ... day in year 1 - 365
            - month
            - day

        """

        # load JSON dataset
        activities_json = persistences.load_json(self.ds_raw_path)
        if not activities_json:
            raise ValueError(
                f"Unable to train the model - no activities in the dataset: "
                f"{self.ds_raw_path}"
            )
        # calculate dataset statistics
        sick_list = self._dataset_stats(activities_json)
        # TODO years when user was NOT sick single day don't bring value to the model
        #   (IMO impossible) - skip them
        self.ds_stats["active_years"] = [2024]

        # DATASET
        df_dict = {
            SickModel.F_YEAR_DAY: [],
            SickModel.F_MONTH: [],
            SickModel.F_DAY: [],
            SickModel.TARGET: [],
        }
        # create dataset rows for all ACTIVE years
        if not self.ds_stats["active_years"]:
            raise ValueError(
                "Unable to train the model - no active years in the dataset: "
                "no activities or sicknesses."
            )

        def _daterange(start_range: date, end_range: date):
            days = int((end_range - start_date).days)
            for n in range(days):
                yield start_range + timedelta(n), n

        for year in self.ds_stats["active_years"]:
            start_date = date(year=year, month=1, day=1)
            end_date = date(year=year, month=12, day=31)
            for single_date in _daterange(start_date, end_date):
                single_date, year_day = single_date
                key = SickModel._date_as_key(
                    year=single_date.year, month=single_date.month, day=single_date.day
                )
                sick = 1.0 if key in sick_list else 0.0

                # append new row to the dataset
                df_dict[SickModel.F_YEAR_DAY].append(year_day)
                df_dict[SickModel.F_MONTH].append(single_date.month)
                df_dict[SickModel.F_DAY].append(single_date.day)
                df_dict[SickModel.TARGET].append(sick)

        # LAG FEATURES
        # - add lag features for the last 5 days
        lag_features = 5
        # TODO add lag features for the last 5 years - if year available
        #   (index five last days above)
        last_year_5_values = [0.0 for _ in range(lag_features)]
        last_year_5_values.reverse()  # inserted in reverse order

        for i in range(1, lag_features + 1):
            wip_lag = df_dict[SickModel.TARGET].copy()
            # insert 5 values to the head of wip lag
            for v in last_year_5_values[:i]:
                wip_lag.insert(0, v)
                # delete last value
                wip_lag.pop()
            df_dict[f"sick_lag_{i}"] = wip_lag

        self.df = pd.DataFrame.from_dict(df_dict)

        # save to CSV
        self.df.to_csv(self.model_dir_path / "sick.dataset.csv", index=False)

        # split to train and test
        self.df_train = self.df.iloc[: int(len(self.df) * 0.8)]
        self.df_test = self.df.iloc[int(len(self.df) * 0.8) :]

        self.logger.info(f"  Dataset saved to: {self.ds_raw_path.with_suffix('.csv')}")
        self.logger.info(f"  Train dataset shape: {self.df_train.shape}")
        self.logger.info(f"  Test dataset shape: {self.df_test.shape}")

    def train(self):
        """Train the model."""
        import xgboost as xgb

        if self.df_train is None or self.df_test is None:
            raise ValueError("Train and/or test datasets not initialized")

        x_train = self.df_train
        x_test = self.df_test
        for c in self.drop_df_features:
            x_train = x_train.drop(c, axis=1)
            x_test = x_test.drop(c, axis=1)

        y_train = self.df_train[SickModel.TARGET]
        y_test = self.df_test[SickModel.TARGET]

        self.model_features = x_train.columns

        self.logger.info(f"  Train dataset features: {x_train.columns}")
        self.logger.info(f"  Test dataset features: {x_test.columns}")

        self.model = xgb.XGBRegressor(
            n_estimators=100,  # number of trees
            early_stopping_rounds=5,  # stop if no improvement for 5 rounds
            learning_rate=0.01,  # step size shrinkage used to prevent overfitting
        )
        # train the model
        self.model.fit(
            x_train,
            y_train,
            eval_set=[(x_train, y_train), (x_test, y_test)],
            verbose=True,
        )

        # save the model as JSON
        self.model.save_model(self.model_dir_path / "sick.model.json")

    def interpret(self):
        """Interpret the model."""
        self.model_feature_importance = zip(
            self.model_features, self.model.feature_importances_
        )
        self.model_feature_importance = sorted(
            self.model_feature_importance, key=lambda x: x[1], reverse=True
        )
        self.logger.info("Feature importance:")
        for feature, importance in self.model_feature_importance:
            self.logger.info(f"  {feature}: {importance}")

    def predict(self, row: pd.DataFrame) -> float:
        return self.model.predict(row) if self.model else -1.0

    @staticmethod
    def load(self):
        pass
