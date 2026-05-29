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

from mytral import settings


@pytest.mark.mytral
def test_user_exercises_bootstrap_enriches_exercises_with_defaults():
    # GIVEN
    bootstrap = settings.UserExercises.bootstrap()

    # WHEN
    by_name = {exercise.name: exercise for exercise in bootstrap}
    squat = by_name["squat"]
    push_up = by_name["push-up"]
    plank = by_name["plank"]
    bench_press = by_name["bench press"]

    # THEN
    assert len(bootstrap) == len(settings.UserExercises.BOOTSTRAP)
    for exercise in bootstrap:
        assert exercise.description
        assert not exercise.description.startswith("- **Setup:**")
        assert (
            "This exercise helps build strength and improve movement control."
            not in (exercise.description)
        )
        assert exercise.weight > 0
        assert exercise.tags
        assert exercise.muscle_groups == settings.mg.validate_muscle_keys(
            exercise.muscle_groups
        )
        assert exercise.muscle_groups_secondary == settings.mg.validate_muscle_keys(
            exercise.muscle_groups_secondary
        )

    assert "leg day" in squat.tags
    assert "bodyweight" in push_up.tags
    assert plank.muscle_groups == ["abs", "obliques", "lower_back"]
    assert bench_press.weight == 50.0
    print("DONE: bootstrap exercises include descriptions, weight, tags, and muscles")
