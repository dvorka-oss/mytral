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

from mytral.ai import settings as ai_settings


@pytest.mark.mytral
def test_ai_provider_roundtrip():
    """Test AiProvider serialization roundtrip."""
    # GIVEN
    provider = ai_settings.AiProvider(
        key="p1",
        type="ollama",
        url="http://localhost:11434",
        api_key_enc="",
        api_key_from_env=False,
    )

    # WHEN
    d = provider.to_dict()
    restored = ai_settings.AiProvider.from_dict(d)

    # THEN
    assert restored.key == provider.key
    assert restored.type == provider.type
    assert restored.url == provider.url
    assert restored.api_key_enc == provider.api_key_enc
    assert restored.api_key_from_env == provider.api_key_from_env
    print("DONE: AiProvider roundtrip")


@pytest.mark.mytral
def test_ai_model_roundtrip():
    """Test AiModel serialization roundtrip."""
    # GIVEN
    model = ai_settings.AiModel(
        key="m1",
        provider_key="p1",
        model_name="llama3",
    )

    # WHEN
    d = model.to_dict()
    restored = ai_settings.AiModel.from_dict(d)

    # THEN
    assert restored.key == model.key
    assert restored.provider_key == model.provider_key
    assert restored.model_name == model.model_name
    print("DONE: AiModel roundtrip")


@pytest.mark.mytral
def test_acoach_roundtrip():
    """Test ACoach serialization roundtrip."""
    # GIVEN
    coach = ai_settings.ACoach(
        key="c1",
        name="Test Coach",
        model_key="m1",
        n_recent_activities=20,
        system_prompt="You are a test coach.",
    )

    # WHEN
    d = coach.to_dict()
    restored = ai_settings.ACoach.from_dict(d)

    # THEN
    assert restored.key == coach.key
    assert restored.name == coach.name
    assert restored.model_key == coach.model_key
    assert restored.n_recent_activities == coach.n_recent_activities
    assert restored.system_prompt == coach.system_prompt
    print("DONE: ACoach roundtrip")


@pytest.mark.mytral
def test_acoach_settings_empty():
    """Test ACoachSettings.empty() creates empty container."""
    # GIVEN / WHEN
    settings = ai_settings.ACoachSettings.empty()

    # THEN
    assert settings.providers == []
    assert settings.models == []
    assert settings.coaches == []
    print("DONE: ACoachSettings.empty()")


@pytest.mark.mytral
def test_acoach_settings_with_ootb_coaches():
    """Test ACoachSettings.with_ootb_coaches() creates three coaches."""
    # GIVEN / WHEN
    settings = ai_settings.ACoachSettings.with_ootb_coaches()

    # THEN
    assert len(settings.coaches) == 3
    names = [c.name for c in settings.coaches]
    assert "Tony D'Amato" in names
    assert "Bohouš Kolibrk" in names
    assert "Emil Zátopek" in names
    for coach in settings.coaches:
        assert coach.key  # has a UUID
        assert coach.system_prompt
    print("DONE: ACoachSettings.with_ootb_coaches()")


@pytest.mark.mytral
def test_acoach_settings_roundtrip():
    """Test ACoachSettings serialization roundtrip with all fields."""
    # GIVEN
    settings = ai_settings.ACoachSettings(
        providers=[
            ai_settings.AiProvider(
                key="p1",
                type="ollama",
                url="http://localhost:11434",
                api_key_enc="",
                api_key_from_env=True,
            )
        ],
        models=[
            ai_settings.AiModel(
                key="m1",
                provider_key="p1",
                model_name="llama3",
            )
        ],
        coaches=[
            ai_settings.ACoach(
                key="c1",
                name="Coach X",
                model_key="m1",
                n_recent_activities=15,
                system_prompt="Be direct.",
            )
        ],
    )

    # WHEN
    d = settings.to_dict()
    restored = ai_settings.ACoachSettings.from_dict(d)

    # THEN
    assert len(restored.providers) == 1
    assert restored.providers[0].key == "p1"
    assert len(restored.models) == 1
    assert restored.models[0].model_name == "llama3"
    assert len(restored.coaches) == 1
    assert restored.coaches[0].name == "Coach X"
    print("DONE: ACoachSettings roundtrip")


@pytest.mark.mytral
def test_acoach_settings_from_empty_dict_returns_ootb():
    """Test that empty dict triggers OOTB coaches."""
    # GIVEN
    empty_dict: dict = {}

    # WHEN
    settings = ai_settings.ACoachSettings.from_dict(empty_dict)

    # THEN
    assert len(settings.coaches) == 3
    print("DONE: ACoachSettings.from_dict({}) returns OOTB")
