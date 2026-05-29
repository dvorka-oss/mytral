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
"""ICL-based activity anomaly detection using TabPFN v2."""

import structlog

from mytral.ml.icl import features as icl_features
from mytral.ml.icl import manager as icl_manager

_logger = structlog.get_logger()

# minimum number of activity rows needed for a meaningful prediction
_MIN_ACTIVITIES = 10


class IclAnomalyPredictor:
    """Activity anomaly detector powered by TabPFN v2 in-context learning.

    Classifies the most recent activity as ``Normal`` or ``Anomaly`` based
    on how its metrics (distance, HR, pace) compare to the athlete's
    historical baseline.

    The predictor silently falls back to ``None`` when:

    - the ``tabpfn`` package is not installed,
    - model weights have not been downloaded, or
    - the user does not have enough activity history.
    """

    def predict(self, activities_json: dict, lookback_days: int = 180) -> dict:
        """Predict whether the most recent activity is anomalous.

        Parameters
        ----------
        activities_json : dict
            Top-level MyTraL dataset dictionary.
        lookback_days : int
            Days of history to use as training context.

        Returns
        -------
        dict
            Result dictionary with keys:

            - ``available`` (bool): whether a prediction was produced.
            - ``is_anomaly`` (bool | None): True if the last activity is flagged.
            - ``confidence`` (float | None): anomaly probability in [0, 1].
            - ``label`` (str | None): ``"Anomaly"`` or ``"Normal"``.
            - ``reason`` (str): explanation when unavailable.
        """
        if not icl_manager.is_tabpfn_installed():
            return _unavailable("TabPFN package is not installed (ml group).")

        if not icl_manager.is_weights_cached():
            return _unavailable("TabPFN model weights not downloaded yet.")

        df = icl_features.extract_anomaly_features(
            activities_json, lookback_days=lookback_days
        )
        if df.empty or len(df) < _MIN_ACTIVITIES:
            return _unavailable(
                "Not enough activity history to make a meaningful prediction "
                f"(need {_MIN_ACTIVITIES}, have {len(df)})."
            )

        X = df[icl_features.ANOMALY_FEATURE_COLS].values
        y = df["is_anomaly"].values

        if len(set(y)) < 2:
            return _unavailable(
                "Training context needs both normal and anomalous activities."
            )

        # use all but the last row as training context; last row = most recent activity
        X_train, y_train = X[:-1], y[:-1]
        X_test = X[-1:]

        try:
            from mytral.ml.icl import model as icl_model

            icl = icl_model.IclModel()
            proba = icl.classify(X_train, y_train, X_test, return_proba=True)
            confidence = float(proba[0])
        except ImportError:
            return _unavailable("TabPFN import failed.")
        except Exception as exc:
            _logger.error("tabpfn: anomaly prediction failed", error=str(exc))
            return _unavailable(f"Prediction error: {exc}")

        is_anomaly = confidence >= 0.5
        return {
            "available": True,
            "is_anomaly": is_anomaly,
            "confidence": round(confidence, 3),
            "label": "Anomaly" if is_anomaly else "Normal",
            "reason": "",
        }


def _unavailable(reason: str) -> dict:
    """Return a standard 'prediction unavailable' result dict.

    Parameters
    ----------
    reason : str
        Human-readable explanation.

    Returns
    -------
    dict
        Result dictionary with ``available`` set to False.
    """
    return {
        "available": False,
        "is_anomaly": None,
        "confidence": None,
        "label": None,
        "reason": reason,
    }
