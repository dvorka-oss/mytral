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
import pytest

from mytral import run_desktop


@pytest.mark.mytral
def test_use_portal_browser_true_when_env_is_portal(monkeypatch):
    # GIVEN MYTRAL_DESKTOP_BROWSER set to portal (Snap strict / Flatpak)
    monkeypatch.setenv("MYTRAL_DESKTOP_BROWSER", "portal")
    # WHEN the launcher decides the window mode
    result = run_desktop.use_portal_browser()
    # THEN it selects the portal browser path
    assert result is True


@pytest.mark.mytral
def test_use_portal_browser_is_case_insensitive(monkeypatch):
    # GIVEN the env var set with surrounding whitespace and mixed case
    monkeypatch.setenv("MYTRAL_DESKTOP_BROWSER", "  Portal  ")
    # WHEN the launcher decides the window mode
    result = run_desktop.use_portal_browser()
    # THEN it still selects the portal browser path
    assert result is True


@pytest.mark.mytral
def test_use_portal_browser_false_when_unset(monkeypatch):
    # GIVEN MYTRAL_DESKTOP_BROWSER not set (classic snap / PyInstaller desktop)
    monkeypatch.delenv("MYTRAL_DESKTOP_BROWSER", raising=False)
    # WHEN the launcher decides the window mode
    result = run_desktop.use_portal_browser()
    # THEN it keeps the native app-window path
    assert result is False


@pytest.mark.mytral
def test_use_portal_browser_false_for_other_value(monkeypatch):
    # GIVEN MYTRAL_DESKTOP_BROWSER set to a non-portal value
    monkeypatch.setenv("MYTRAL_DESKTOP_BROWSER", "native")
    # WHEN the launcher decides the window mode
    result = run_desktop.use_portal_browser()
    # THEN it keeps the native app-window path
    assert result is False
