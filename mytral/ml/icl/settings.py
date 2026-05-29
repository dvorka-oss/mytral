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
"""Per-user settings for TabPFN in-context learning (ICL) integration."""

import dataclasses

# model download status constants
MODEL_STATUS_NOT_INSTALLED = "not_installed"
MODEL_STATUS_NOT_DOWNLOADED = "not_downloaded"
MODEL_STATUS_DOWNLOADING = "downloading"
MODEL_STATUS_DOWNLOADED = "downloaded"
MODEL_STATUS_FAILED = "failed"


@dataclasses.dataclass
class IclSettings:
    """Per-user configuration for TabPFN ICL predictions.

    Attributes
    ----------
    enabled : bool
        Master switch - whether ICL predictions are enabled for this user.
    enable_illness_risk : bool
        Whether illness risk prediction is active.
    enable_fatigue : bool
        Whether fatigue/readiness score prediction is active.
    enable_performance : bool
        Whether race performance estimation is active.
    enable_rest_day : bool
        Whether optimal rest day prediction is active.
    enable_anomaly : bool
        Whether activity anomaly detection is active.
    """

    enabled: bool = False
    enable_illness_risk: bool = True
    enable_fatigue: bool = True
    enable_performance: bool = True
    enable_rest_day: bool = True
    enable_anomaly: bool = True

    @staticmethod
    def empty() -> "IclSettings":
        """Return default disabled settings.

        Returns
        -------
        IclSettings
            Empty (disabled) settings instance.
        """
        return IclSettings(enabled=False)

    @staticmethod
    def from_dict(d: dict) -> "IclSettings":
        """Deserialize from dictionary.

        Parameters
        ----------
        d : dict
            Source dictionary.

        Returns
        -------
        IclSettings
            Deserialized instance; returns default empty settings if dict is empty.
        """
        if not d:
            return IclSettings.empty()
        return IclSettings(
            enabled=d.get("enabled", False),
            enable_illness_risk=d.get("enable_illness_risk", True),
            enable_fatigue=d.get("enable_fatigue", True),
            enable_performance=d.get("enable_performance", True),
            enable_rest_day=d.get("enable_rest_day", True),
            enable_anomaly=d.get("enable_anomaly", True),
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary.

        Returns
        -------
        dict
            Serialized dictionary.
        """
        return {
            "enabled": self.enabled,
            "enable_illness_risk": self.enable_illness_risk,
            "enable_fatigue": self.enable_fatigue,
            "enable_performance": self.enable_performance,
            "enable_rest_day": self.enable_rest_day,
            "enable_anomaly": self.enable_anomaly,
        }
