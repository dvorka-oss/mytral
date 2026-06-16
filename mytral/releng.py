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
from mytral import utils


class FeatureFlags:
    """Control which features are enabled in the application."""

    # features to enable / disable
    ACOACHES = "ACOACHES"  # AI coaches
    GSHEETS_DVORKA_IMPORT = "GSHEETS_DVORKA_IMPORT"  # Dvorka's own GSheets import
    IRM3D = "IRM3D"  # 3D inpulse response model
    PFN_PREDICTIONS = "PFN_PREDICTIONS"
    STRAVA_API_IMPORT = "STRAVA_API_IMPORT"  # Strava API import
    TASKS_DEV = "TASKS_DEV"  # features, like Hello World! tasks, for tasks development
    TRIMP = "TRIMP"
    TRIMP_ROCKS = "TRIMP_ROCKS"  # Banister fitness-fatigue-performance model

    # env variables
    ENV_FF_PREFIX = "MYTRAL_FF"
    ENV_ACOACHES = f"{ENV_FF_PREFIX}_{ACOACHES}"
    ENV_GSHEETS_DVORKA_IMPORT = f"{ENV_FF_PREFIX}_{GSHEETS_DVORKA_IMPORT}"
    ENV_IRM3D = f"{ENV_FF_PREFIX}_{IRM3D}"
    ENV_PFN_PREDICTIONS = f"{ENV_FF_PREFIX}_{PFN_PREDICTIONS}"
    ENV_STRAVA_API_IMPORT = f"{ENV_FF_PREFIX}_{STRAVA_API_IMPORT}"
    ENV_TASKS_DEV = f"{ENV_FF_PREFIX}_{TASKS_DEV}"
    ENV_TRIMP = f"{ENV_FF_PREFIX}_{TRIMP}"
    ENV_TRIMP_ROCKS = f"{ENV_FF_PREFIX}_{TRIMP_ROCKS}"

    # switch MyTraL to DEVELOPMENT / WIP / PRODUCTION mode
    MODE_GA = "ga"  # production quality features only
    MODE_WIP = "wip"  # ^ + work in progress features
    MODE_MOCK = "mock"  # ^ + mock features

    def __init__(self) -> None:
        self._flags: dict = {
            FeatureFlags.ACOACHES: utils.getenv_bool(FeatureFlags.ENV_ACOACHES),
            FeatureFlags.GSHEETS_DVORKA_IMPORT: utils.getenv_bool(
                FeatureFlags.ENV_GSHEETS_DVORKA_IMPORT
            ),
            FeatureFlags.IRM3D: utils.getenv_bool(name=FeatureFlags.ENV_IRM3D),
            FeatureFlags.PFN_PREDICTIONS: utils.getenv_bool(
                FeatureFlags.ENV_PFN_PREDICTIONS
            ),
            FeatureFlags.STRAVA_API_IMPORT: utils.getenv_bool(
                name=FeatureFlags.ENV_STRAVA_API_IMPORT, default=True
            ),
            FeatureFlags.TASKS_DEV: utils.getenv_bool(FeatureFlags.ENV_TASKS_DEV),
            FeatureFlags.TRIMP: utils.getenv_bool(FeatureFlags.ENV_TRIMP),
            FeatureFlags.TRIMP_ROCKS: utils.getenv_bool(FeatureFlags.ENV_TRIMP_ROCKS),
        }
        self._mode = FeatureFlags.MODE_GA  # MyTraL is in GA mode by default

    def mode(self, mode: str) -> bool:
        """Check if the application is in particular mode."""
        match mode:
            case FeatureFlags.MODE_GA:
                return self._mode == FeatureFlags.MODE_GA
            case FeatureFlags.MODE_WIP:
                return self._mode in [FeatureFlags.MODE_WIP, FeatureFlags.MODE_MOCK]
            case FeatureFlags.MODE_MOCK:
                return self._mode == FeatureFlags.MODE_MOCK
            case _:
                raise ValueError(f"Unknown mode: {mode}")

    def set_mode(self, mode: str):
        """Set the application mode."""
        if mode in [
            FeatureFlags.MODE_GA,
            FeatureFlags.MODE_WIP,
            FeatureFlags.MODE_MOCK,
        ]:
            self._mode = mode
        else:
            raise ValueError(f"Unknown mode: {mode}")

    def enable(self, feature: str):
        """Enable a feature."""
        self._flags[feature] = True

    def disable(self, feature: str):
        """Disable a feature."""
        self._flags[feature] = False

    def can(self, feature: str) -> bool:
        """Check if a feature is enabled."""
        return bool(self._flags.get(feature, False))

    def print(self, logger):
        logger.info("Feature flags:")
        for flag in self._flags:
            env_flag = f"{FeatureFlags.ENV_FF_PREFIX}_{flag}"
            logger.info(
                f"- {env_flag} = {self.can(flag)}",
                env_var=env_flag,
            )
