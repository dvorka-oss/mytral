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
"""ICL-based fatigue and readiness prediction using TabPFN v2."""

import structlog

from mytral.ml.icl import features as icl_features
from mytral.ml.icl import manager as icl_manager

_logger = structlog.get_logger()

# minimum number of training rows needed for a meaningful prediction
_MIN_ROWS = 30


class IclFatiguePredictor:
    """Fatigue and readiness predictor powered by TabPFN v2 in-context learning.

    Classifies the athlete's current state as one of:
    ``fresh`` / ``normal`` / ``fatigued`` / ``overreaching``

    The predictor silently falls back to ``None`` when:

    - the ``tabpfn`` package is not installed,
    - model weights have not been downloaded, or
    - the user's dataset has insufficient training history.
    """

    def predict(self, activities_json: dict, lookback_days: int = 90) -> dict:
        """Predict fatigue level for today.

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
            - ``label`` (str | None): fatigue class label.
            - ``readiness_score`` (int | None): readiness score 0–100.
            - ``reason`` (str): explanation when unavailable.
        """
        if not icl_manager.is_tabpfn_installed():
            return _unavailable("TabPFN package is not installed (ml group).")

        if not icl_manager.is_weights_cached():
            return _unavailable("TabPFN model weights not downloaded yet.")

        df = icl_features.extract_fatigue_features(
            activities_json, lookback_days=lookback_days
        )
        if df.empty or len(df) < _MIN_ROWS:
            return _unavailable(
                "Not enough training history to make a meaningful prediction."
            )

        X = df[icl_features.FATIGUE_FEATURE_COLS].values
        y = df["fatigue_class"].values

        X_train, y_train = X[:-1], y[:-1]
        X_test = X[-1:]

        if len(set(y_train)) < 2:
            return _unavailable(
                "Training context needs at least two different fatigue classes."
            )

        try:
            from mytral.ml.icl import model as icl_model

            icl = icl_model.IclModel()
            label = icl.classify(X_train, y_train, X_test, return_proba=False)
            label = str(label[0]) if hasattr(label, "__iter__") else str(label)
        except ImportError:
            return _unavailable("TabPFN import failed.")
        except Exception as exc:
            _logger.error("tabpfn: fatigue prediction failed", error=str(exc))
            return _unavailable(f"Prediction error: {exc}")

        # derive readiness score (0-100) from TSB of the last row
        tsb = float(df["tsb"].iloc[-1])
        readiness_score = max(0, min(100, int(50 + tsb * 2)))

        return {
            "available": True,
            "label": label,
            "readiness_score": readiness_score,
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
        "label": None,
        "readiness_score": None,
        "reason": reason,
    }
