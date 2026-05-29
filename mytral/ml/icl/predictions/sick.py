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
"""ICL-based illness risk prediction using TabPFN v2."""

import structlog

from mytral.ml.icl import features as icl_features
from mytral.ml.icl import manager as icl_manager

_logger = structlog.get_logger()

# minimum fraction of positive class needed in training set
_MIN_SICK_FRACTION = 0.01


class IclSickPredictor:
    """Illness risk predictor powered by TabPFN v2 in-context learning.

    Uses recent activity history as training context and predicts the
    probability of illness for the current day.  No separate training step is
    required — TabPFN operates as a pure in-context learner.

    The predictor silently falls back to ``None`` when:

    - the ``tabpfn`` package is not installed,
    - model weights have not been downloaded, or
    - the user's dataset contains insufficient illness history.
    """

    def predict(self, activities_json: dict, lookback_days: int = 180) -> dict:
        """Predict illness risk for today.

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
            - ``probability`` (float | None): illness probability [0, 1].
            - ``label`` (str | None): human-readable risk label.
            - ``reason`` (str): explanation when prediction is unavailable.
        """
        if not icl_manager.is_tabpfn_installed():
            return _unavailable("TabPFN package is not installed (ml group).")

        if not icl_manager.is_weights_cached():
            return _unavailable("TabPFN model weights not downloaded yet.")

        df = icl_features.extract_sick_features(
            activities_json, lookback_days=lookback_days
        )
        if not icl_features.sufficient_data(df):
            return _unavailable(
                "Not enough illness history to make a meaningful prediction."
            )

        X = df[icl_features.SICK_FEATURE_COLS].values
        y = df["sick"].values

        # use all but the last row as training context; last row = today
        X_train, y_train = X[:-1], y[:-1]
        X_test = X[-1:]

        if len(set(y_train)) < 2:
            return _unavailable(
                "Training context needs at least one sick and one healthy day."
            )

        try:
            from mytral.ml.icl import model as icl_model

            icl = icl_model.IclModel()
            proba = icl.classify(X_train, y_train, X_test, return_proba=True)
            p = float(proba[0])
        except ImportError:
            return _unavailable("TabPFN import failed.")
        except Exception as exc:
            _logger.error("tabpfn: sick prediction failed", error=str(exc))
            return _unavailable(f"Prediction error: {exc}")

        label = _risk_label(p)
        return {
            "available": True,
            "probability": round(p, 3),
            "label": label,
            "reason": "",
        }


def _risk_label(probability: float) -> str:
    """Convert a probability to a human-readable risk label.

    Parameters
    ----------
    probability : float
        Illness probability in [0, 1].

    Returns
    -------
    str
        Risk label: low, moderate, high, or very_high.
    """
    if probability < 0.15:
        return "low"
    if probability < 0.35:
        return "moderate"
    if probability < 0.60:
        return "high"
    return "very_high"


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
        "probability": None,
        "label": None,
        "reason": reason,
    }
