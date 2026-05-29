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
import unittest.mock

import pytest

from mytral.ai import context as ai_context


def _make_activity(
    when, activity_type_key, name, distance, duration, avg_hr, sickness_symptoms=None
):
    act = unittest.mock.MagicMock()
    act.when = when
    act.activity_type_key = activity_type_key
    act.name = name
    act.distance = distance
    act.duration = duration
    act.avg_hr = avg_hr
    act.sickness_symptoms = sickness_symptoms or []
    return act


def _make_user_profile(user="testuser", age=35, height=1.75):
    profile = unittest.mock.MagicMock()
    profile.user = user
    profile.age = age
    profile.height = height
    profile.dataset_name = "training"
    return profile


@pytest.mark.mytral
def test_build_user_context_basic():
    """Test build_user_context returns non-empty context string."""
    # GIVEN
    profile = _make_user_profile()
    activity = _make_activity(
        when="2025-01-10T08:00:00",
        activity_type_key="Running",
        name="Morning run",
        distance=10000,
        duration="00:50:00",
        avg_hr=145,
    )
    dataset = unittest.mock.MagicMock()
    dataset.all_activities.return_value = {"a1": activity}
    dataset.list_goals.side_effect = Exception("no goals")

    # WHEN
    context = ai_context.build_user_context(profile, dataset, n_recent=5)

    # THEN
    assert "testuser" in context
    assert "ATHLETE PROFILE" in context
    assert "RECENT ACTIVITIES" in context
    assert "Running" in context
    assert "10.0 km" in context
    print("DONE: build_user_context basic")


@pytest.mark.mytral
def test_build_user_context_includes_profile_data():
    """Test that athlete profile section includes age and height."""
    # GIVEN
    profile = _make_user_profile(user="alice", age=28, height=1.65)
    dataset = unittest.mock.MagicMock()
    dataset.all_activities.return_value = {}
    dataset.list_goals.side_effect = Exception("no goals")

    # WHEN
    context = ai_context.build_user_context(profile, dataset)

    # THEN
    assert "alice" in context
    assert "28" in context
    assert "1.65" in context
    print("DONE: build_user_context profile data")


@pytest.mark.mytral
def test_build_user_context_truncates_long_context():
    """Test that context is truncated if it exceeds MAX_CONTEXT_CHARS."""
    # GIVEN
    profile = _make_user_profile()
    # create many activities to generate a large context
    activities = {}
    for i in range(500):
        act = _make_activity(
            when=f"2025-01-{(i % 28) + 1:02d}T08:00:00",
            activity_type_key="Running",
            name=f"Run number {i} with a very long name to inflate the context size",
            distance=10000 + i * 100,
            duration="01:00:00",
            avg_hr=150,
        )
        activities[f"a{i}"] = act

    dataset = unittest.mock.MagicMock()
    dataset.all_activities.return_value = activities
    dataset.list_goals.side_effect = Exception("no goals")

    # WHEN
    context = ai_context.build_user_context(profile, dataset, n_recent=500)

    # THEN
    assert len(context) <= ai_context.MAX_CONTEXT_CHARS
    print("DONE: build_user_context truncation")


@pytest.mark.mytral
def test_build_user_context_handles_dataset_error():
    """Test that context builder handles dataset errors gracefully."""
    # GIVEN
    profile = _make_user_profile()
    dataset = unittest.mock.MagicMock()
    dataset.all_activities.side_effect = Exception("dataset unavailable")
    dataset.list_goals.side_effect = Exception("no goals")

    # WHEN
    context = ai_context.build_user_context(profile, dataset)

    # THEN
    # should still return valid context with at least the profile section
    assert "ATHLETE PROFILE" in context
    assert "testuser" in context
    print("DONE: build_user_context handles errors")
