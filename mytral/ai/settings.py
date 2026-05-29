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
import dataclasses
import uuid

OOTB_TONY_D_PROMPT = (
    "You are Tony D'Amato, a legendary American football coach known for "
    "inspirational speeches and deep psychological insight into performance. "
    "You talk directly to the person in front of you — warm, personal, "
    'occasionally intense. Use "you" and "your", never refer to them as '
    '"the athlete" or in third person. Push hard, demand excellence, but '
    "always acknowledge the human behind the numbers. Reference specific "
    "metrics from their data to motivate and challenge. Open with a human, "
    "personal line before diving into the numbers."
)

OOTB_BOHOUS_PROMPT = (
    "Jsi trenér Bohouš Kolibrk, praktický a přátelský Čech s hlubokými "
    "znalostmi vytrvalostního sportu. Komunikuješ česky, používáš přirozený "
    'hovorový jazyk. Mluvíš přímo k člověku před sebou — říkáš "ty", "tvůj", '
    'nikdy "sportovec" ani ve třetí osobě. Jsi upřímný, někdy přímý až drsný, '
    "ale vždy lidský and konstruktivní. Začni odpověď lidsky, osobně, "
    "než se pustíš do čísel."
)

OOTB_EMIL_PROMPT = (
    "You are inspired by Emil Zátopek, the legendary Czech long-distance "
    "runner who revolutionized training through systematic hard work and "
    'self-experimentation. You talk directly to the person — use "you" and '
    '"your", never "the athlete" or third person. Bring Zátopek\'s warmth '
    "and lived experience into every reply. Embrace hard work, experiment "
    "boldly, recover wisely. Open with a personal, human line that connects "
    "to what you see in their data."
)

RESPONSE_FORMAT_INSTRUCTION = """
Talk directly to the person — use "you" and "your" throughout. Never say "the
athlete" or refer to them in third person.
Start your response with a brief warm, personal opener (1-2 sentences) that
reflects your personality and addresses what they asked.
Then structure your response in exactly four sections using bold headings (not
large headers):

**Observations** — 3 specific things you notice in their training data
**Insights** — 3 deeper conclusions drawn from those observations
**Advice** — 3 concrete recommendations addressed directly to them
**Action Items** — 3 immediate, specific things they should do next

Use exactly 3 numbered items per section. Be direct, personal, and concise.
"""


@dataclasses.dataclass
class AiProvider:
    """AI LLM provider configuration."""

    key: str
    type: str  # LlmProviderType constant
    url: str
    api_key_enc: str
    api_key_from_env: bool

    @staticmethod
    def from_dict(d: dict) -> "AiProvider":
        """Deserialize from dictionary.

        Parameters
        ----------
        d : dict
            Source dictionary.

        Returns
        -------
        AiProvider
            Deserialized instance.
        """
        return AiProvider(
            key=d.get("key", ""),
            type=d.get("type", ""),
            url=d.get("url", ""),
            api_key_enc=d.get("api_key_enc", ""),
            api_key_from_env=d.get("api_key_from_env", False),
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary.

        Returns
        -------
        dict
            Serialized dictionary.
        """
        return {
            "key": self.key,
            "type": self.type,
            "url": self.url,
            "api_key_enc": self.api_key_enc,
            "api_key_from_env": self.api_key_from_env,
        }


@dataclasses.dataclass
class AiModel:
    """AI model configuration linking a provider to a model name."""

    key: str
    provider_key: str
    model_name: str

    @staticmethod
    def from_dict(d: dict) -> "AiModel":
        """Deserialize from dictionary.

        Parameters
        ----------
        d : dict
            Source dictionary.

        Returns
        -------
        AiModel
            Deserialized instance.
        """
        return AiModel(
            key=d.get("key", ""),
            provider_key=d.get("provider_key", ""),
            model_name=d.get("model_name", ""),
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary.

        Returns
        -------
        dict
            Serialized dictionary.
        """
        return {
            "key": self.key,
            "provider_key": self.provider_key,
            "model_name": self.model_name,
        }


@dataclasses.dataclass
class ACoach:
    """AI coach persona configuration."""

    key: str
    name: str
    model_key: str
    system_prompt: str
    n_recent_activities: int = 15
    photo_blob_key: str = ""

    @staticmethod
    def from_dict(d: dict) -> "ACoach":
        """Deserialize from dictionary.

        Parameters
        ----------
        d : dict
            Source dictionary.

        Returns
        -------
        ACoach
            Deserialized instance.
        """
        return ACoach(
            key=d.get("key", ""),
            name=d.get("name", ""),
            model_key=d.get("model_key", ""),
            system_prompt=d.get("system_prompt", ""),
            n_recent_activities=int(d.get("n_recent_activities", 15)),
            photo_blob_key=d.get("photo_blob_key", ""),
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary.

        Returns
        -------
        dict
            Serialized dictionary.
        """
        return {
            "key": self.key,
            "name": self.name,
            "model_key": self.model_key,
            "system_prompt": self.system_prompt,
            "n_recent_activities": self.n_recent_activities,
            "photo_blob_key": self.photo_blob_key,
        }


class ACoachSettings:
    """Container for all ACoach-related settings (providers, models, coaches)."""

    KEY_ACOACH = "acoach"
    KEY_PROVIDERS = "providers"
    KEY_MODELS = "models"
    KEY_COACHES = "coaches"

    def __init__(
        self,
        providers: list[AiProvider],
        models: list[AiModel],
        coaches: list[ACoach],
    ) -> None:
        self.providers = providers
        self.models = models
        self.coaches = coaches

    @staticmethod
    def empty() -> "ACoachSettings":
        """Return empty settings with no providers, models, or coaches.

        Returns
        -------
        ACoachSettings
            Empty settings instance.
        """
        return ACoachSettings(providers=[], models=[], coaches=[])

    @staticmethod
    def with_ootb_coaches() -> "ACoachSettings":
        """Return settings pre-populated with out-of-the-box coaches.

        Returns
        -------
        ACoachSettings
            Settings with three default coach personas.
        """
        coaches = [
            ACoach(
                key=str(uuid.uuid4()),
                name="Tony D'Amato",
                model_key="",
                system_prompt=OOTB_TONY_D_PROMPT,
            ),
            ACoach(
                key=str(uuid.uuid4()),
                name="Bohouš Kolibrk",
                model_key="",
                system_prompt=OOTB_BOHOUS_PROMPT,
            ),
            ACoach(
                key=str(uuid.uuid4()),
                name="Emil Zátopek",
                model_key="",
                system_prompt=OOTB_EMIL_PROMPT,
            ),
        ]
        return ACoachSettings(providers=[], models=[], coaches=coaches)

    @staticmethod
    def from_dict(d: dict) -> "ACoachSettings":
        """Deserialize from dictionary.

        Parameters
        ----------
        d : dict
            Source dictionary.

        Returns
        -------
        ACoachSettings
            Deserialized instance; returns OOTB coaches if dict is empty.
        """
        if not d:
            return ACoachSettings.with_ootb_coaches()
        providers = [
            AiProvider.from_dict(p) for p in d.get(ACoachSettings.KEY_PROVIDERS, [])
        ]
        models = [AiModel.from_dict(m) for m in d.get(ACoachSettings.KEY_MODELS, [])]
        coaches = [ACoach.from_dict(c) for c in d.get(ACoachSettings.KEY_COACHES, [])]
        return ACoachSettings(providers=providers, models=models, coaches=coaches)

    def to_dict(self) -> dict:
        """Serialize to dictionary.

        Returns
        -------
        dict
            Serialized dictionary.
        """
        return {
            ACoachSettings.KEY_PROVIDERS: [p.to_dict() for p in self.providers],
            ACoachSettings.KEY_MODELS: [m.to_dict() for m in self.models],
            ACoachSettings.KEY_COACHES: [c.to_dict() for c in self.coaches],
        }
