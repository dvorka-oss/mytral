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

"""TabPFN v2 model wrapper for in-context learning predictions.

All imports of ``tabpfn`` are lazy so the module loads cleanly even when the
``ml`` optional dependency group is not installed.
"""

try:
    import tabpfn

    _HAS_TABPFN = True
except ImportError:
    _HAS_TABPFN = False


class IclModel:
    """Thin scikit-learn-compatible wrapper around TabPFN v2.

    Uses the Apache 2.0 licensed v2 weights only.  The TabPFN v2 model
    receives the entire training context in a single forward pass — there is
    no separate ``fit`` step needed by callers.

    Attributes
    ----------
    _clf : object or None
        Lazily loaded ``TabPFNClassifier`` instance.
    _reg : object or None
        Lazily loaded ``TabPFNRegressor`` instance.
    """

    def __init__(self) -> None:
        self._clf = None
        self._reg = None

    #
    # Internal helpers
    #

    def _get_classifier(self):
        """Return (or lazily create) the TabPFN v2 classifier.

        Returns
        -------
        TabPFNClassifier
            Configured TabPFN v2 classifier instance.

        Raises
        ------
        ImportError
            If ``tabpfn`` is not installed.
        RuntimeError
            If TabPFN weights are not available.
        """
        if not _HAS_TABPFN:
            raise ImportError(
                "TabPFN is not installed - please install the 'tabpfn' dependency"
            )

        if self._clf is None:
            self._clf = tabpfn.TabPFNClassifier(model_path="auto")
        return self._clf

    def _get_regressor(self):
        """Return (or lazily create) the TabPFN v2 regressor.

        Returns
        -------
        TabPFNRegressor
            Configured TabPFN v2 regressor instance.

        Raises
        ------
        ImportError
            If ``tabpfn`` is not installed.
        RuntimeError
            If TabPFN weights are not available.
        """
        if not _HAS_TABPFN:
            raise ImportError(
                "TabPFN is not installed - please install the 'tabpfn' dependency"
            )

        if self._reg is None:
            self._reg = tabpfn.TabPFNRegressor(model_path="auto")
        return self._reg

    #
    # Public API
    #

    def classify(self, X_train, y_train, X_test, return_proba: bool = True) -> list:
        """Run in-context classification on the given data.

        Parameters
        ----------
        X_train : array-like of shape (n_train, n_features)
            Training feature matrix.
        y_train : array-like of shape (n_train,)
            Training labels.
        X_test : array-like of shape (n_test, n_features)
            Test feature matrix.
        return_proba : bool
            When True return probability of positive class; otherwise return
            hard class predictions.

        Returns
        -------
        list
            List of floats (probabilities) or ints (class labels).

        Raises
        ------
        ImportError
            If ``tabpfn`` is not installed.
        """
        clf = self._get_classifier()
        clf.fit(X_train, y_train)
        if return_proba:
            proba = clf.predict_proba(X_test)
            # return probability of positive class (index 1)
            return [float(row[1]) for row in proba]
        return list(clf.predict(X_test))

    def regress(self, X_train, y_train, X_test) -> list:
        """Run in-context regression on the given data.

        Parameters
        ----------
        X_train : array-like of shape (n_train, n_features)
            Training feature matrix.
        y_train : array-like of shape (n_train,)
            Continuous target values.
        X_test : array-like of shape (n_test, n_features)
            Test feature matrix.

        Returns
        -------
        list
            List of float predictions.

        Raises
        ------
        ImportError
            If ``tabpfn`` is not installed.
        """
        reg = self._get_regressor()
        reg.fit(X_train, y_train)
        return [float(p) for p in reg.predict(X_test)]
