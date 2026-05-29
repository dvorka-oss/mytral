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
import json
import os

import requests
import structlog

from mytral import security
from mytral.ai import settings as ai_settings

_logger = structlog.get_logger()


class LlmProviderType:
    """Constants for supported LLM provider types."""

    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    ALL = [OLLAMA, ANTHROPIC, OPENAI]
    THIRD_PARTY = [ANTHROPIC, OPENAI]

    ANTHROPIC_KNOWN_MODELS = [
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        "claude-opus-4",
        "claude-sonnet-4",
    ]
    OPENAI_KNOWN_MODELS = [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
        "o1",
        "o1-mini",
        "o3-mini",
    ]
    ANTHROPIC_MODELS_URL = (
        "https://docs.anthropic.com/en/docs/about-claude/models/overview"
    )
    OPENAI_MODELS_URL = "https://platform.openai.com/docs/models"

    ENV_OLLAMA_KEY = "MYTRAL_OLLAMA_KEY"
    ENV_ANTHROPIC_KEY = "MYTRAL_ANTHROPIC_API_KEY"
    ENV_OPENAI_KEY = "MYTRAL_OPENAI_API_KEY"

    OLLAMA_DEFAULT_URL = "http://localhost:11434"


def resolved_api_key(provider: ai_settings.AiProvider, encryption_key: str) -> str:
    """Return plaintext API key.

    Parameters
    ----------
    provider : ai_settings.AiProvider
        Provider configuration.
    encryption_key : str
        Fernet encryption key for decrypting stored API key.

    Returns
    -------
    str
        Plaintext API key.
    """
    env_map = {
        LlmProviderType.OLLAMA: LlmProviderType.ENV_OLLAMA_KEY,
        LlmProviderType.ANTHROPIC: LlmProviderType.ENV_ANTHROPIC_KEY,
        LlmProviderType.OPENAI: LlmProviderType.ENV_OPENAI_KEY,
    }
    if provider.api_key_from_env:
        return os.environ.get(env_map.get(provider.type, ""), "")
    if provider.api_key_enc:
        return security.decrypt(provider.api_key_enc, encryption_key)
    return ""


def list_models(provider: ai_settings.AiProvider, encryption_key: str) -> list[str]:
    """Return available model names for a provider.

    Parameters
    ----------
    provider : ai_settings.AiProvider
        Provider configuration.
    encryption_key : str
        Encryption key for resolving API key.

    Returns
    -------
    list[str]
        List of model name strings.
    """
    if provider.type == LlmProviderType.ANTHROPIC:
        return LlmProviderType.ANTHROPIC_KNOWN_MODELS
    if provider.type == LlmProviderType.OPENAI:
        return LlmProviderType.OPENAI_KNOWN_MODELS
    if provider.type == LlmProviderType.OLLAMA:
        try:
            url = (provider.url or LlmProviderType.OLLAMA_DEFAULT_URL).rstrip(
                "/"
            ) + "/api/tags"
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as exc:
            _logger.warning("providers: failed to list ollama models", error=str(exc))
            return []
    return []


def health_check(
    provider: ai_settings.AiProvider, model_name: str, encryption_key: str
) -> tuple[bool, str]:
    """Send trivial prompt to verify connectivity.

    Parameters
    ----------
    provider : ai_settings.AiProvider
        Provider configuration.
    model_name : str
        Model to test.
    encryption_key : str
        Encryption key.

    Returns
    -------
    tuple[bool, str]
        Tuple of (ok, message).
    """
    try:
        messages = [{"role": "user", "content": "Say OK"}]
        result = complete(provider, model_name, messages, encryption_key)
        return True, f"OK: {result[:80]}"
    except Exception as exc:
        return False, str(exc)


def build_system_message(coach: ai_settings.ACoach, user_context: str) -> str:
    """Compose full system message combining personality, format and context.

    Parameters
    ----------
    coach : ai_settings.ACoach
        Coach configuration with system prompt.
    user_context : str
        Structured athlete context string.

    Returns
    -------
    str
        Full system message for LLM.
    """
    return (
        coach.system_prompt
        + "\n\n"
        + ai_settings.RESPONSE_FORMAT_INSTRUCTION.strip()
        + "\n\nATHLETE CONTEXT:\n"
        + user_context
    )


def complete(
    provider: ai_settings.AiProvider,
    model_name: str,
    messages: list[dict],
    encryption_key: str,
) -> str:
    """Send messages to LLM and return full response text.

    Parameters
    ----------
    provider : ai_settings.AiProvider
        Provider configuration.
    model_name : str
        Model name.
    messages : list[dict]
        Chat messages with 'role' and 'content'.
    encryption_key : str
        Encryption key.

    Returns
    -------
    str
        Full response text from LLM.
    """
    api_key = resolved_api_key(provider, encryption_key)

    if provider.type == LlmProviderType.OLLAMA:
        url = (provider.url or LlmProviderType.OLLAMA_DEFAULT_URL).rstrip(
            "/"
        ) + "/api/chat"
        resp = requests.post(
            url,
            json={"model": model_name, "messages": messages, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    if provider.type == LlmProviderType.ANTHROPIC:
        import anthropic

        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [m for m in messages if m["role"] != "system"]
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model_name,
            max_tokens=1024,
            system=system_msg,
            messages=user_msgs,
        )
        return response.content[0].text

    if provider.type == LlmProviderType.OPENAI:
        import openai

        client = openai.OpenAI(
            api_key=api_key,
            base_url=provider.url or None,
        )
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
        )
        return response.choices[0].message.content or ""

    raise ValueError(f"Unknown provider type: {provider.type}")


def stream_complete(
    provider: ai_settings.AiProvider,
    model_name: str,
    messages: list[dict],
    encryption_key: str,
):
    """Yield text tokens from LLM.

    Parameters
    ----------
    provider : ai_settings.AiProvider
        Provider configuration.
    model_name : str
        Model name.
    messages : list[dict]
        Chat messages with 'role' and 'content'.
    encryption_key : str
        Encryption key.

    Yields
    ------
    str
        Text tokens from LLM response.
    """
    api_key = resolved_api_key(provider, encryption_key)

    if provider.type == LlmProviderType.OLLAMA:
        url = (provider.url or LlmProviderType.OLLAMA_DEFAULT_URL).rstrip(
            "/"
        ) + "/api/chat"
        with requests.post(
            url,
            json={"model": model_name, "messages": messages, "stream": True},
            stream=True,
            timeout=120,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        if not chunk.get("done", False):
                            content = chunk.get("message", {}).get("content", "")
                            if content:
                                yield content
                    except Exception:
                        pass
        return

    if provider.type == LlmProviderType.ANTHROPIC:
        import anthropic

        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [m for m in messages if m["role"] != "system"]
        client = anthropic.Anthropic(api_key=api_key)
        with client.messages.stream(
            model=model_name,
            max_tokens=2048,
            system=system_msg,
            messages=user_msgs,
        ) as stream:
            for text in stream.text_stream:
                yield text
        return

    if provider.type == LlmProviderType.OPENAI:
        import openai

        client = openai.OpenAI(
            api_key=api_key,
            base_url=provider.url or None,
        )
        with client.chat.completions.create(
            model=model_name,
            messages=messages,
            stream=True,
        ) as stream:
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        return

    raise ValueError(f"Unknown provider type: {provider.type}")
