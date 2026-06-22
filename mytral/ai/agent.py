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
import datetime

import pydantic_ai
import pydantic_ai.exceptions
import pydantic_ai.models
import structlog
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider

from mytral.ai import context as ai_context
from mytral.ai import providers as ai_providers
from mytral.ai import settings as ai_settings

_logger = structlog.get_logger()


#
# Structured response model — enforced at the Pydantic level
#


#
# NOTE: We intentionally use output_type=str (plain text / markdown) rather
# than a structured Pydantic result model.
#
# Reason: local models (e.g. llama3.2 via Ollama) do not reliably produce
# strict JSON matching a schema with min_length constraints — they return
# conversational prose, which PydanticAI cannot parse, causing
# UnexpectedModelBehavior after exhausting retries.
#
# Instead, the desired 4-section structure (Observations / Insights / Advice /
# Action Items) is enforced through the system-prompt instruction
# (RESPONSE_FORMAT_INSTRUCTION), which every model family can follow in plain
# markdown.  This works uniformly for Ollama, Anthropic, and OpenAI.
#


#
# Dependency injection container
#


@dataclasses.dataclass
class CoachDeps:
    """Runtime dependencies injected into agent tools."""

    # avoid circular imports — typed as object
    user_profile: object  # settings.UserProfile
    dataset: object  # dataset.UserDataset


#
# PydanticAI model factory
#


def _make_pydantic_ai_model(
    provider: ai_settings.AiProvider,
    model_name: str,
    encryption_key: str,
) -> pydantic_ai.models.Model:
    """Construct a PydanticAI model object for the given provider.

    Parameters
    ----------
    provider : ai_settings.AiProvider
        Provider configuration.
    model_name : str
        Model name string.
    encryption_key : str
        Fernet key to decrypt stored API key.

    Returns
    -------
    pydantic_ai.models.Model
        PydanticAI model instance.
    """

    api_key = ai_providers.resolved_api_key(provider, encryption_key)

    if provider.type == ai_providers.LlmProviderType.OLLAMA:
        base_url = (provider.url or "http://localhost:11434").rstrip("/") + "/v1"
        ollama_provider = OpenAIProvider(base_url=base_url, api_key=api_key or "ollama")
        return OpenAIModel(model_name, provider=ollama_provider)

    if provider.type == ai_providers.LlmProviderType.ANTHROPIC:
        anthropic_provider = AnthropicProvider(api_key=api_key)
        return AnthropicModel(model_name, provider=anthropic_provider)

    if provider.type == ai_providers.LlmProviderType.OPENAI:
        kwargs: dict = {"api_key": api_key}
        if provider.url:
            kwargs["base_url"] = provider.url
        openai_provider = OpenAIProvider(**kwargs)
        return OpenAIModel(model_name, provider=openai_provider)

    raise ValueError(f"Unknown provider type: {provider.type}")


#
# Agent builder
#


def build_agent(
    coach: ai_settings.ACoach,
    provider: ai_settings.AiProvider,
    model_name: str,
    encryption_key: str,
) -> pydantic_ai.Agent:
    """Build a configured PydanticAI agent for a given coach.

    Parameters
    ----------
    coach : ai_settings.ACoach
        Coach configuration (name, system_prompt).
    provider : ai_settings.AiProvider
        LLM provider configuration.
    model_name : str
        LLM model name string.
    encryption_key : str
        Fernet key for API key decryption.

    Returns
    -------
    pydantic_ai.Agent
        Configured agent with tools and structured output.
    """
    model = _make_pydantic_ai_model(provider, model_name, encryption_key)

    system_prompt = (
        coach.system_prompt
        + "\n\n"
        + ai_settings.RESPONSE_FORMAT_INSTRUCTION.strip()
        + "\n\n"
        "The athlete's training data is provided in the [DATA CONTEXT] section of "
        "every message. Base your response on that data directly - speak to the person "
        "using 'you' and 'your', never refer to them in the third person. "
        "You may also call the available tools to fetch additional or more specific "
        "data not already in the DATA CONTEXT - but never output raw tool-call JSON "
        "as your answer. If you have enough data in the DATA CONTEXT, answer directly."
    )

    _logger.debug(
        "agent: building agent",
        coach=coach.name,
        provider_type=str(provider.type),
        model=model_name,
        system_prompt_len=len(system_prompt),
    )

    agent: pydantic_ai.Agent[CoachDeps, str] = pydantic_ai.Agent(
        model,
        deps_type=CoachDeps,
        output_type=str,
        system_prompt=system_prompt,
        # allow retries on transient failures (e.g. tool errors)
        output_retries=2,
    )

    # register tools

    @agent.tool
    async def get_recent_activities(
        ctx: pydantic_ai.RunContext[CoachDeps],
        activity_type_key: str | None = None,
        limit: int = 20,
    ) -> str:
        """Fetch the most recent activities, optionally filtered by activity_type_key.

        Parameters
        ----------
        ctx : pydantic_ai.RunContext[CoachDeps]
            Injected runtime context.
        activity_type_key : str | None
            Activity type filter (e.g. 'run', 'cycle'). None means all activities.
        limit : int
            Maximum number of activities to return (default 20, max 50).

        Returns
        -------
        str
            Formatted table of recent activities.
        """
        limit = min(limit, 50)
        _health_sports = {"sick", "injured"}
        try:
            all_acts = ctx.deps.dataset.all_activities(
                user_id=ctx.deps.user_profile.user_id,
                dataset_name=ctx.deps.user_profile.dataset_name,
            )
            acts = sorted(all_acts.values(), key=lambda a: a.when, reverse=True)
            if activity_type_key:
                acts = [
                    a
                    for a in acts
                    if a.activity_type_key.lower() == activity_type_key.lower()
                ]
            acts = acts[:limit]
            if not acts:
                return "No activities found."
            rows = []
            for a in acts:
                prefix = (
                    "[HEALTH EVENT] "
                    if a.activity_type_key.lower() in _health_sports
                    else ""
                )
                dist = f"{a.distance / 1000:.1f}km" if a.distance else "-"
                pace = a.pace or "-"
                hr = str(a.avg_hr) if a.avg_hr else "-"
                elev = f"+{a.elevation_gain}m" if a.elevation_gain else "-"
                symptoms = ""
                if a.sickness_symptoms:
                    names = [
                        s.name if hasattr(s, "name") else str(s)
                        for s in a.sickness_symptoms
                    ]
                    symptoms = f" | symptoms: {', '.join(names)}"
                rows.append(
                    f"{prefix}{a.when[:10]} | {a.activity_type_key} | {a.name} | {dist}"
                    f" | {a.duration} | {pace}/km | HR:{hr} | {elev}{symptoms}"
                )
            return "\n".join(rows)
        except Exception as exc:
            _logger.warning("agent tool: get_recent_activities failed", error=str(exc))
            return f"Error fetching activities: {exc}"

    @agent.tool
    async def get_activities_in_range(
        ctx: pydantic_ai.RunContext[CoachDeps],
        from_date: str,
        to_date: str,
        activity_type_key: str | None = None,
    ) -> str:
        """Fetch activities between two dates (YYYY-MM-DD format).

        Parameters
        ----------
        ctx : pydantic_ai.RunContext[CoachDeps]
            Injected runtime context.
        from_date : str
            Start date inclusive, YYYY-MM-DD.
        to_date : str
            End date inclusive, YYYY-MM-DD.
        activity_type_key : str | None
            Optional activity_type_key filter.

        Returns
        -------
        str
            Formatted activity list or summary.
        """
        try:
            all_acts = ctx.deps.dataset.all_activities(
                user_id=ctx.deps.user_profile.user_id,
                dataset_name=ctx.deps.user_profile.dataset_name,
            )
            acts = [a for a in all_acts.values() if from_date <= a.when[:10] <= to_date]
            if activity_type_key:
                acts = [
                    a
                    for a in acts
                    if a.activity_type_key.lower() == activity_type_key.lower()
                ]
            acts = sorted(acts, key=lambda a: a.when, reverse=True)
            if not acts:
                return f"No activities found between {from_date} and {to_date}."
            total_km = sum(a.distance for a in acts) / 1000
            total_h = sum(a.duration_seconds for a in acts) / 3600
            summary = (
                f"Period {from_date} to {to_date}: "
                f"{len(acts)} activities, {total_km:.0f} km, {total_h:.1f} h\n"
            )
            rows = []
            for a in acts[:30]:
                dist = f"{a.distance / 1000:.1f}km" if a.distance else "-"
                rows.append(
                    f"{a.when[:10]} | {a.activity_type_key} | {a.name} | {dist} "
                    f"| {a.duration}"
                )
            return summary + "\n".join(rows)
        except Exception as exc:
            _logger.warning(
                "agent tool: get_activities_in_range failed", error=str(exc)
            )
            return f"Error: {exc}"

    @agent.tool
    async def get_yearly_summary(
        ctx: pydantic_ai.RunContext[CoachDeps],
        year: int,
    ) -> str:
        """Get annual training summary for a given year.

        Parameters
        ----------
        ctx : pydantic_ai.RunContext[CoachDeps]
            Injected runtime context.
        year : int
            Calendar year (e.g. 2024).

        Returns
        -------
        str
            Annual totals broken down by activity_type_key.
        """
        try:
            all_acts = ctx.deps.dataset.all_activities(
                user_id=ctx.deps.user_profile.user_id,
                dataset_name=ctx.deps.user_profile.dataset_name,
            )
            year_str = str(year)
            acts = [a for a in all_acts.values() if a.when[:4] == year_str]
            if not acts:
                return f"No activities found for {year}."
            by_sport: dict[str, dict] = {}
            for a in acts:
                s = a.activity_type_key
                if s not in by_sport:
                    by_sport[s] = {"count": 0, "km": 0.0, "hours": 0.0}
                by_sport[s]["count"] += 1
                by_sport[s]["km"] += a.distance / 1000
                by_sport[s]["hours"] += a.duration_seconds / 3600
            lines = [f"Year {year}: {len(acts)} total activities"]
            for sport_name, totals in sorted(by_sport.items()):
                lines.append(
                    f"  {sport_name}: {totals['count']} sessions, "
                    f"{totals['km']:.0f} km, {totals['hours']:.1f} h"
                )
            return "\n".join(lines)
        except Exception as exc:
            _logger.warning("agent tool: get_yearly_summary failed", error=str(exc))
            return f"Error: {exc}"

    @agent.tool
    async def get_training_load(
        ctx: pydantic_ai.RunContext[CoachDeps],
        weeks: int = 12,
    ) -> str:
        """Get weekly training load for the last N weeks.

        Parameters
        ----------
        ctx : pydantic_ai.RunContext[CoachDeps]
            Injected runtime context.
        weeks : int
            Number of weeks to look back (default 12, max 52).

        Returns
        -------
        str
            Week-by-week totals.
        """
        weeks = min(weeks, 52)
        try:
            all_acts = ctx.deps.dataset.all_activities(
                user_id=ctx.deps.user_profile.user_id,
                dataset_name=ctx.deps.user_profile.dataset_name,
            )
            today = datetime.date.today()
            cutoff = today - datetime.timedelta(weeks=weeks)
            cutoff_str = cutoff.isoformat()
            acts = [a for a in all_acts.values() if a.when[:10] >= cutoff_str]
            # group by ISO 8601 week (Monday-anchored, correct year via isocalendar)
            by_week: dict[str, dict] = {}
            for a in acts:
                d = datetime.date.fromisoformat(a.when[:10])
                iso = d.isocalendar()
                week_key = f"{iso[0]}-W{iso[1]:02d}"
                if week_key not in by_week:
                    by_week[week_key] = {
                        "km": 0.0,
                        "hours": 0.0,
                        "count": 0,
                        "activity_types": set(),
                    }
                by_week[week_key]["km"] += a.distance / 1000
                by_week[week_key]["hours"] += a.duration_seconds / 3600
                by_week[week_key]["count"] += 1
                by_week[week_key]["activity_types"].add(a.activity_type_key)
            if not by_week:
                return "No training data found for this period."
            lines = [f"Weekly load (last {weeks} weeks):"]
            for week in sorted(by_week.keys(), reverse=True):
                w = by_week[week]
                sports_str = ", ".join(sorted(w["activity_types"]))
                lines.append(
                    f"  {week}: {w['count']} sessions, {w['km']:.0f} km, "
                    f"{w['hours']:.1f} h | {sports_str}"
                )
            return "\n".join(lines)
        except Exception as exc:
            _logger.warning("agent tool: get_training_load failed", error=str(exc))
            return f"Error: {exc}"

    @agent.tool
    async def get_personal_bests(
        ctx: pydantic_ai.RunContext[CoachDeps],
        activity_type_key: str | None = None,
    ) -> str:
        """Get personal bests — longest and fastest efforts per activity_type_key.

        Parameters
        ----------
        ctx : pydantic_ai.RunContext[CoachDeps]
            Injected runtime context.
        activity_type_key : str | None
            Filter to specific activity_type_key. None returns all activity_types.

        Returns
        -------
        str
            Personal best records formatted as text.
        """
        try:
            all_acts = ctx.deps.dataset.all_activities(
                user_id=ctx.deps.user_profile.user_id,
                dataset_name=ctx.deps.user_profile.dataset_name,
            )
            acts = list(all_acts.values())
            if activity_type_key:
                acts = [
                    a
                    for a in acts
                    if a.activity_type_key.lower() == activity_type_key.lower()
                ]
            by_sport: dict[str, list] = {}
            for a in acts:
                if a.distance > 0:
                    by_sport.setdefault(a.activity_type_key, []).append(a)
            lines = ["Personal bests by activity_type_key:"]
            for s, sport_acts in sorted(by_sport.items()):
                top_dist = sorted(sport_acts, key=lambda a: a.distance, reverse=True)[
                    :3
                ]
                top_speed = sorted(
                    [a for a in sport_acts if a.avg_speed > 0],
                    key=lambda a: a.avg_speed,
                    reverse=True,
                )[:3]
                lines.append(f"  {s}:")
                for a in top_dist:
                    lines.append(
                        f"    Longest: {a.distance / 1000:.1f} km"
                        f" on {a.when[:10]} ({a.name})"
                    )
                for a in top_speed:
                    lines.append(
                        f"    Fastest: {a.avg_speed:.1f} km/h"
                        f" ({a.pace}/km) on {a.when[:10]}"
                    )
            return "\n".join(lines) if len(lines) > 1 else "No personal bests found."
        except Exception as exc:
            _logger.warning("agent tool: get_personal_bests failed", error=str(exc))
            return f"Error: {exc}"

    @agent.tool
    async def get_gear_status(
        ctx: pydantic_ai.RunContext[CoachDeps],
    ) -> str:
        """Get current gear inventory with mileage and service status.

        Parameters
        ----------
        ctx : pydantic_ai.RunContext[CoachDeps]
            Injected runtime context.

        Returns
        -------
        str
            Gear list with usage stats.
        """
        try:
            user_gear = ctx.deps.dataset.list_gear(
                user_id=ctx.deps.user_profile.user_id,
                dataset_name=ctx.deps.user_profile.dataset_name,
            )
            gear_list = list(user_gear.gear.values())
            active = [g for g in gear_list if not g.retired]
            if not active:
                return "No active gear found."
            lines = ["Active gear:"]
            for g in active:
                default_tag = " [default]" if g.is_default else ""
                lines.append(
                    f"  {g.name} ({g.activity_type_key}){default_tag}"
                    f" | {g.vendor} {g.model}"
                    f" | purchased: {g.purchased or 'unknown'}"
                )
                components = g.get_components(include_retired=False)
                for comp in components:
                    service_info = ""
                    if (
                        hasattr(comp, "service_interval_km")
                        and comp.service_interval_km
                    ):
                        service_info = f" | service every {comp.service_interval_km}km"
                    lines.append(f"    component: {comp.name}{service_info}")
            return "\n".join(lines)
        except Exception as exc:
            _logger.warning("agent tool: get_gear_status failed", error=str(exc))
            return f"Error: {exc}"

    @agent.tool
    async def get_goals(
        ctx: pydantic_ai.RunContext[CoachDeps],
    ) -> str:
        """Get current training goals.

        Parameters
        ----------
        ctx : pydantic_ai.RunContext[CoachDeps]
            Injected runtime context.

        Returns
        -------
        str
            Active goals formatted as text.
        """
        try:
            user_goals = ctx.deps.dataset.list_goals(
                user_id=ctx.deps.user_profile.user_id,
            )
            goals = [g for g in user_goals.get_all() if not g.done]
            if not goals:
                return "No active goals."
            lines = ["Active goals:"]
            for g in goals:
                deadline = (
                    g.target_date
                    if hasattr(g, "target_date") and g.target_date
                    else "no deadline"
                )
                lines.append(
                    f"  {g.name} | {g.activity_type} | due: {deadline}"
                    f" | {g.description}"
                )
            return "\n".join(lines)
        except Exception as exc:
            _logger.warning("agent tool: get_goals failed", error=str(exc))
            return f"Error: {exc}"

    @agent.tool
    async def get_athlete_profile(
        ctx: pydantic_ai.RunContext[CoachDeps],
    ) -> str:
        """Get athlete's profile information.

        Parameters
        ----------
        ctx : pydantic_ai.RunContext[CoachDeps]
            Injected runtime context.

        Returns
        -------
        str
            Athlete profile summary.
        """
        p = ctx.deps.user_profile
        lines = [f"Athlete: {p.user}"]
        if p.age:
            lines.append(f"Age: {p.age}")
        if p.height:
            lines.append(f"Height: {p.height:.2f} m")
        return "\n".join(lines)

    @agent.tool
    async def get_today(
        ctx: pydantic_ai.RunContext[CoachDeps],
    ) -> str:
        """Return today's date and the current ISO week's Monday–Sunday range.

        Parameters
        ----------
        ctx : pydantic_ai.RunContext[CoachDeps]
            Injected runtime context.

        Returns
        -------
        str
            Today's date and the current week boundaries (YYYY-MM-DD).
        """
        today = datetime.date.today()
        # ISO week: Monday = day 0
        monday = today - datetime.timedelta(days=today.weekday())
        sunday = monday + datetime.timedelta(days=6)
        return (
            f"Today: {today.isoformat()}\n"
            f"Current week: {monday.isoformat()} to {sunday.isoformat()}\n"
            f"Day of week: {today.strftime('%A')}"
        )

    @agent.tool
    async def get_this_week_activities(
        ctx: pydantic_ai.RunContext[CoachDeps],
    ) -> str:
        """Get all activities for the current ISO week (Mon–today), including
        sickness and injury entries.

        Parameters
        ----------
        ctx : pydantic_ai.RunContext[CoachDeps]
            Injected runtime context.

        Returns
        -------
        str
            All activities this week with health events prominently flagged.
        """
        _health_sports = {"sick", "injured"}
        today = datetime.date.today()
        monday = today - datetime.timedelta(days=today.weekday())
        from_date = monday.isoformat()
        to_date = today.isoformat()
        try:
            all_acts = ctx.deps.dataset.all_activities(
                user_id=ctx.deps.user_profile.user_id,
                dataset_name=ctx.deps.user_profile.dataset_name,
            )
            acts = [a for a in all_acts.values() if from_date <= a.when[:10] <= to_date]
            acts = sorted(acts, key=lambda a: a.when)
            if not acts:
                return f"No activities recorded this week ({from_date} to {to_date})."
            rows = []
            for a in acts:
                is_health = a.activity_type_key.lower() in _health_sports
                prefix = "[HEALTH EVENT] " if is_health else ""
                dist = f"{a.distance / 1000:.1f}km" if a.distance else "-"
                symptoms = ""
                if a.sickness_symptoms:
                    names = [
                        s.name if hasattr(s, "name") else str(s)
                        for s in a.sickness_symptoms
                    ]
                    symptoms = f" | symptoms: {', '.join(names)}"
                rows.append(
                    f"{prefix}{a.when[:10]} | {a.activity_type_key} | {a.name}"
                    f" | {dist} | {a.duration}{symptoms}"
                )
            return f"This week ({from_date} to {to_date}):\n" + "\n".join(rows)
        except Exception as exc:
            _logger.warning(
                "agent tool: get_this_week_activities failed", error=str(exc)
            )
            return f"Error: {exc}"

    @agent.tool
    async def get_health_history(
        ctx: pydantic_ai.RunContext[CoachDeps],
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> str:
        """Get health events: sickness days, injuries, and recorded symptoms.

        Covers both dedicated sick/injured activity entries AND sickness
        symptoms attached to regular training sessions.

        Parameters
        ----------
        ctx : pydantic_ai.RunContext[CoachDeps]
            Injected runtime context.
        from_date : str | None
            Start date YYYY-MM-DD. Defaults to 90 days ago.
        to_date : str | None
            End date YYYY-MM-DD. Defaults to today.

        Returns
        -------
        str
            Health events formatted as text.
        """
        _health_sports = {"sick", "injured"}
        try:
            if not from_date:
                from_date = (
                    datetime.date.today() - datetime.timedelta(days=90)
                ).isoformat()
            if not to_date:
                to_date = datetime.date.today().isoformat()
            all_acts = ctx.deps.dataset.all_activities(
                user_id=ctx.deps.user_profile.user_id,
                dataset_name=ctx.deps.user_profile.dataset_name,
            )
            rows = []
            for a in sorted(all_acts.values(), key=lambda x: x.when):
                if not (from_date <= a.when[:10] <= to_date):
                    continue
                # dedicated sick/injured activity entries
                if a.activity_type_key.lower() in _health_sports:
                    symptoms = ""
                    if a.sickness_symptoms:
                        names = [
                            s.name if hasattr(s, "name") else str(s)
                            for s in a.sickness_symptoms
                        ]
                        symptoms = f" | symptoms: {', '.join(names)}"
                    rows.append(
                        f"{a.when[:10]} | {a.activity_type_key.upper()} "
                        f"| {a.name}{symptoms}"
                    )
                    continue
                # sickness symptoms on regular training sessions
                if a.sickness_symptoms:
                    for s in a.sickness_symptoms:
                        name = s.name if hasattr(s, "name") else str(s)
                        rows.append(
                            f"{a.when[:10]} | symptom during {a.activity_type_key} "
                            f"| {name}"
                        )
            if not rows:
                return f"No health issues recorded between {from_date} and {to_date}."
            return "Health events:\n" + "\n".join(rows)
        except Exception as exc:
            _logger.warning("agent tool: get_health_history failed", error=str(exc))
            return f"Error: {exc}"

    @agent.tool
    async def get_sport_trends(
        ctx: pydantic_ai.RunContext[CoachDeps],
        sport: str,
        years: int = 5,
    ) -> str:
        """Get multi-year trends for a activity_type_key (year-by-year totals).

        Parameters
        ----------
        ctx : pydantic_ai.RunContext[CoachDeps]
            Injected runtime context.
        sport : str
            Sport name to analyse.
        years : int
            How many past years to include (default 5, max 30).

        Returns
        -------
        str
            Year-by-year totals for the activity_type_key.
        """
        years = min(years, 30)
        try:
            all_acts = ctx.deps.dataset.all_activities(
                user_id=ctx.deps.user_profile.user_id,
                dataset_name=ctx.deps.user_profile.dataset_name,
            )
            current_year = datetime.date.today().year
            first_year = current_year - years + 1
            acts = [
                a
                for a in all_acts.values()
                if a.activity_type_key.lower() == sport.lower()
                and int(a.when[:4]) >= first_year
            ]
            if not acts:
                return f"No {sport} data found for the last {years} years."
            by_year: dict[int, dict] = {}
            for a in acts:
                yr = int(a.when[:4])
                if yr not in by_year:
                    by_year[yr] = {"km": 0.0, "hours": 0.0, "count": 0}
                by_year[yr]["km"] += a.distance / 1000
                by_year[yr]["hours"] += a.duration_seconds / 3600
                by_year[yr]["count"] += 1
            lines = [f"{sport} trends ({first_year}–{current_year}):"]
            for yr in sorted(by_year.keys()):
                t = by_year[yr]
                lines.append(
                    f"  {yr}: {t['count']} sessions,"
                    f" {t['km']:.0f} km, {t['hours']:.1f} h"
                )
            return "\n".join(lines)
        except Exception as exc:
            _logger.warning("agent tool: get_sport_trends failed", error=str(exc))
            return f"Error: {exc}"

    return agent


#
# Sync runner for Flask routes
#


def run_agent(
    coach: ai_settings.ACoach,
    provider: ai_settings.AiProvider,
    model_name: str,
    encryption_key: str,
    user_profile: object,
    dataset: object,
    messages: list[dict],
) -> str:
    """Run the agent synchronously and return the markdown response string.

    Parameters
    ----------
    coach : ai_settings.ACoach
        Coach configuration.
    provider : ai_settings.AiProvider
        Provider configuration.
    model_name : str
        LLM model name.
    encryption_key : str
        Fernet key.
    user_profile : object
        User profile (settings.UserProfile).
    dataset : object
        Dataset handle (dataset.UserDataset).
    messages : list[dict]
        Chat history as list of {role, content} dicts.

    Returns
    -------
    str
        Markdown-formatted coaching response.

    Raises
    ------
    ValueError
        If no user message is found in the message list.
    pydantic_ai.exceptions.AgentRunError
        If the agent run fails (HTTP error, etc.).
    """
    # extract the last user message as the prompt
    user_message = ""
    for msg in messages:
        if msg["role"] == "user":
            user_message = msg["content"]

    if not user_message:
        raise ValueError("No user message found in message list")

    # pre-build athlete context and inject it into the prompt so the model always
    # has the data — local models (e.g. llama3.2 via Ollama) do not reliably use
    # the OpenAI function-calling protocol and would otherwise output raw JSON
    data_context = ai_context.build_user_context(
        user_profile, dataset, n_recent=coach.n_recent_activities
    )
    today = datetime.date.today()
    enriched_message = (
        f"[DATA CONTEXT — {today.isoformat()}]\n"
        f"{data_context}\n\n"
        f"[QUESTION]\n{user_message}"
    )

    _logger.info(
        "agent: starting run",
        coach=coach.name,
        provider_type=str(provider.type),
        model=model_name,
        prompt_len=len(enriched_message),
        context_len=len(data_context),
    )
    agent = build_agent(coach, provider, model_name, encryption_key)
    deps = CoachDeps(user_profile=user_profile, dataset=dataset)

    try:
        result = agent.run_sync(enriched_message, deps=deps)
    except pydantic_ai.exceptions.UnexpectedModelBehavior as exc:
        _logger.error(
            "agent: unexpected model behavior — likely malformed structured output",
            coach=coach.name,
            model=model_name,
            error=exc.message,
            response_body=exc.body,
        )
        raise
    except pydantic_ai.exceptions.ModelHTTPError as exc:
        _logger.error(
            "agent: HTTP error from model provider",
            coach=coach.name,
            model=model_name,
            status_code=exc.status_code,
            error=exc.message,
            response_body=str(exc.body) if exc.body else None,
        )
        raise
    except pydantic_ai.exceptions.AgentRunError as exc:
        cause_str = str(exc.__cause__) if exc.__cause__ else None
        _logger.error(
            "agent: run failed",
            coach=coach.name,
            model=model_name,
            error_type=type(exc).__name__,
            error=str(exc),
            cause=cause_str,
        )
        raise
    except Exception as exc:
        _logger.error(
            "agent: unexpected error",
            coach=coach.name,
            model=model_name,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise

    _logger.info(
        "agent: run completed",
        coach=coach.name,
        model=model_name,
        response_len=len(result.output),
    )
    return result.output


def format_response_as_markdown(response: str) -> str:
    """Return the markdown response string unchanged (kept for API compatibility).

    Parameters
    ----------
    response : str
        Markdown response returned by run_agent.

    Returns
    -------
    str
        Same string, unchanged.
    """
    return response
