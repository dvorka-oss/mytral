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
"""ICL-based race performance prediction using TabPFN v2."""

import structlog

from mytral.ml.icl import features as icl_features
from mytral.ml.icl import manager as icl_manager

_logger = structlog.get_logger()

# minimum number of run activities needed for a meaningful prediction
_MIN_RUN_ACTIVITIES = 10


class IclPerformancePredictor:
    """Race performance predictor powered by TabPFN v2 in-context learning.

    Estimates the athlete's current 10K finish time in minutes using recent
    run activity data and Riegel-formula-derived labels as training context.

    The predictor silently falls back to ``None`` when:

    - the ``tabpfn`` package is not installed,
    - model weights have not been downloaded, or
    - the user does not have enough run activity history.
    """

    def predict(self, activities_json: dict, lookback_days: int = 365) -> dict:
        """Predict 10K finish time from recent training data.

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
            - ``predicted_10k_minutes`` (float|None): estimated finish time in minutes.
            - ``predicted_10k_label`` (str|None): human-readable time like ``"48:30"``.
            - ``reason`` (str): explanation when unavailable.
        """
        if not icl_manager.is_tabpfn_installed():
            return _unavailable("TabPFN package is not installed (ml group).")

        if not icl_manager.is_weights_cached():
            return _unavailable("TabPFN model weights not downloaded yet.")

        df = icl_features.extract_performance_features(
            activities_json, lookback_days=lookback_days
        )
        if df.empty or len(df) < _MIN_RUN_ACTIVITIES:
            return _unavailable(
                "Not enough run activities to make a meaningful prediction "
                f"(need {_MIN_RUN_ACTIVITIES}, have {len(df)})."
            )

        X = df[icl_features.PERFORMANCE_FEATURE_COLS].values
        y = df["riegel_10k_min"].values

        # use all but the last row as training context; last row = most recent run
        X_train, y_train = X[:-1], y[:-1]
        X_test = X[-1:]

        try:
            from mytral.ml.icl import model as icl_model

            icl = icl_model.IclModel()
            predicted = icl.regress(X_train, y_train, X_test)
            minutes = float(predicted[0])
        except ImportError:
            return _unavailable("TabPFN import failed.")
        except Exception as exc:
            _logger.error("tabpfn: performance prediction failed", error=str(exc))
            return _unavailable(f"Prediction error: {exc}")

        if minutes <= 0:
            return _unavailable("Invalid predicted time (non-positive value).")

        return {
            "available": True,
            "predicted_10k_minutes": round(minutes, 1),
            "predicted_10k_label": _minutes_to_label(minutes),
            "reason": "",
        }


def _minutes_to_label(minutes: float) -> str:
    """Convert decimal minutes to a ``MM:SS`` or ``H:MM:SS`` label.

    Parameters
    ----------
    minutes : float
        Total finish time in minutes.

    Returns
    -------
    str
        Human-readable label.
    """
    total_seconds = int(round(minutes * 60))
    hours, rem = divmod(total_seconds, 3600)
    mins, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


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
        "predicted_10k_minutes": None,
        "predicted_10k_label": None,
        "reason": reason,
    }
