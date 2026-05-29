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

from mytral.ai import providers as ai_providers
from mytral.ai import settings as ai_settings


@pytest.mark.mytral
def test_llm_provider_type_constants():
    """Test LlmProviderType has expected constants."""
    # GIVEN / WHEN / THEN
    assert ai_providers.LlmProviderType.OLLAMA == "ollama"
    assert ai_providers.LlmProviderType.ANTHROPIC == "anthropic"
    assert ai_providers.LlmProviderType.OPENAI == "openai"
    assert len(ai_providers.LlmProviderType.ALL) == 3
    assert len(ai_providers.LlmProviderType.THIRD_PARTY) == 2
    print("DONE: LlmProviderType constants")


@pytest.mark.mytral
def test_build_system_message():
    """Test build_system_message combines coach prompt, format and context."""
    # GIVEN
    coach = ai_settings.ACoach(
        key="c1",
        name="Test Coach",
        model_key="m1",
        n_recent_activities=30,
        system_prompt="You are a test coach.",
    )
    user_context = "## ATHLETE PROFILE\nAthlete: tester"

    # WHEN
    msg = ai_providers.build_system_message(coach, user_context)

    # THEN
    assert "You are a test coach." in msg
    assert "## ATHLETE PROFILE" in msg
    assert "ATHLETE CONTEXT:" in msg
    assert "Observations" in msg
    print("DONE: build_system_message")


@pytest.mark.mytral
def test_list_models_anthropic():
    """Test list_models returns known Anthropic models."""
    # GIVEN
    provider = ai_settings.AiProvider(
        key="p1",
        type="anthropic",
        url="",
        api_key_enc="",
        api_key_from_env=False,
    )

    # WHEN
    models = ai_providers.list_models(provider, encryption_key="")

    # THEN
    assert len(models) > 0
    assert "claude-sonnet-4-5" in models
    print("DONE: list_models anthropic")


@pytest.mark.mytral
def test_list_models_openai():
    """Test list_models returns known OpenAI models."""
    # GIVEN
    provider = ai_settings.AiProvider(
        key="p1",
        type="openai",
        url="",
        api_key_enc="",
        api_key_from_env=False,
    )

    # WHEN
    models = ai_providers.list_models(provider, encryption_key="")

    # THEN
    assert len(models) > 0
    assert "gpt-4o" in models
    print("DONE: list_models openai")


@pytest.mark.mytral
def test_resolved_api_key_from_env(monkeypatch):
    """Test resolved_api_key reads from environment when api_key_from_env is True."""
    # GIVEN
    monkeypatch.setenv("MYTRAL_ANTHROPIC_API_KEY", "test-key-123")
    provider = ai_settings.AiProvider(
        key="p1",
        type="anthropic",
        url="",
        api_key_enc="",
        api_key_from_env=True,
    )

    # WHEN
    key = ai_providers.resolved_api_key(provider, encryption_key="")

    # THEN
    assert key == "test-key-123"
    print("DONE: resolved_api_key from env")


@pytest.mark.mytral
def test_resolved_api_key_empty_when_no_key():
    """Test resolved_api_key returns empty string when no key configured."""
    # GIVEN
    provider = ai_settings.AiProvider(
        key="p1",
        type="ollama",
        url="http://localhost:11434",
        api_key_enc="",
        api_key_from_env=False,
    )

    # WHEN
    key = ai_providers.resolved_api_key(provider, encryption_key="")

    # THEN
    assert key == ""
    print("DONE: resolved_api_key empty when not configured")
