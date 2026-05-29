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
import datetime

import structlog

MAX_CONTEXT_CHARS = 24_000

_logger = structlog.get_logger()


def _fmt_symptom(s) -> str:
    """Return human-readable symptom string from SicknessSymptomEntity."""
    parts = []
    if hasattr(s, "body_part") and s.body_part:
        parts.append(s.body_part)
    if hasattr(s, "side") and s.side:
        parts.append(s.side)
    if hasattr(s, "health") and s.health:
        parts.append(f"health={s.health}%")
    return " ".join(parts) if parts else str(s)


def build_user_context(user_profile, dataset, n_recent: int = 15) -> str:
    """Return structured plain-text training summary for LLM system prompt.

    Parameters
    ----------
    user_profile : settings.UserProfile
        User profile with personal data.
    dataset : UsersDataset
        Dataset for accessing activities, goals, symptoms.
    n_recent : int
        Number of recent activities to include.

    Returns
    -------
    str
        Structured plain-text training context for LLM.
    """
    sections = []
    _health_sports = {"sick", "injured"}

    # athlete profile section
    profile_lines = [f"Athlete: {user_profile.user}"]
    if user_profile.age:
        profile_lines.append(f"Age: {user_profile.age}")
    if user_profile.height:
        profile_lines.append(f"Height: {user_profile.height:.2f} m")
    sections.append("## ATHLETE PROFILE\n" + "\n".join(profile_lines))

    # load all activities once — reused for multiple sections below
    sorted_acts = []
    try:
        all_acts = dataset.all_activities(
            user_id=user_profile.user_id,
            dataset_name=user_profile.dataset_name,
        )
        sorted_acts = sorted(all_acts.values(), reverse=True, key=lambda x: x.when)
    except Exception as exc:
        _logger.warning("context: failed to load activities", error=str(exc))

    # this week section (Mon–today) — always included, flagging health events
    if sorted_acts:
        today = datetime.date.today()
        monday = today - datetime.timedelta(days=today.weekday())
        week_acts = [a for a in sorted_acts if a.when[:10] >= monday.isoformat()]
        if week_acts:
            week_rows = []
            for a in reversed(week_acts):
                prefix = (
                    "[HEALTH] " if a.activity_type_key.lower() in _health_sports else ""
                )
                dist = f"{a.distance / 1000:.1f} km" if a.distance else "-"
                dur = a.duration if a.duration else "-"
                symptoms = ""
                if a.sickness_symptoms:
                    names = [_fmt_symptom(s) for s in a.sickness_symptoms]
                    symptoms = f" | symptoms: {', '.join(names)}"
                week_rows.append(
                    f"- {prefix}{a.when[:10]} | {a.activity_type_key} | {a.name}"
                    f" | {dist} | {dur}{symptoms}"
                )
            sections.append(
                f"## THIS WEEK ({monday.isoformat()} – {today.isoformat()})\n"
                + "\n".join(week_rows)
            )

    # health section — placed before recent activities so truncation never cuts it
    if sorted_acts:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=90)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        symptom_rows = []
        for a in sorted(sorted_acts, key=lambda x: x.when):
            if a.when[:10] < cutoff_str:
                continue
            # dedicated sick/injured activity entries
            if a.activity_type_key.lower() in _health_sports:
                symptoms = ""
                if a.sickness_symptoms:
                    names = [_fmt_symptom(s) for s in a.sickness_symptoms]
                    symptoms = f" | symptoms: {', '.join(names)}"
                symptom_rows.append(
                    f"- {a.when[:10]} | {a.activity_type_key.upper()} "
                    f"| {a.name}{symptoms}"
                )
            elif a.sickness_symptoms:
                for s in a.sickness_symptoms:
                    name = _fmt_symptom(s)
                    symptom_rows.append(
                        f"- {a.when[:10]} | symptom during {a.activity_type_key} "
                        f"| {name}"
                    )
        if symptom_rows:
            sections.append("## HEALTH (last 90 days)\n" + "\n".join(symptom_rows))

    # goals section
    try:
        user_goals = dataset.list_goals(user_id=user_profile.user_id)
        goals = list(user_goals.goals_by_key.values())
        if goals:
            rows = [
                f"- {g.name} | {g.activity_type} | {g.description}"
                for g in goals
                if not g.done
            ]
            if rows:
                sections.append("## GOALS\n" + "\n".join(rows))
    except Exception as exc:
        _logger.warning("context: failed to load goals", error=str(exc))

    # recent activities section (kept last — truncation hits here first)
    if sorted_acts:
        recent = sorted_acts[:n_recent]
        rows = []
        for a in recent:
            prefix = (
                "[HEALTH] " if a.activity_type_key.lower() in _health_sports else ""
            )
            dist = f"{a.distance / 1000:.1f} km" if a.distance else "-"
            dur = a.duration if a.duration else "-"
            hr = str(a.avg_hr) if a.avg_hr else "-"
            rows.append(
                f"- {prefix}{a.when[:10]} | {a.activity_type_key} | {a.name}"
                f" | {dist} | {dur} | HR: {hr}"
            )
        sections.append(f"## RECENT ACTIVITIES (last {n_recent})\n" + "\n".join(rows))

    # personal bests section — also kept late, can be truncated
    if sorted_acts:
        by_sport: dict[str, list] = {}
        for a in sorted_acts:
            if a.distance > 0:
                by_sport.setdefault(a.activity_type_key, []).append(a)
        pb_rows = []
        for activity_type_key, acts in sorted(by_sport.items()):
            top5 = sorted(acts, key=lambda x: x.distance, reverse=True)[:5]
            for a in top5:
                dist = f"{a.distance / 1000:.1f} km"
                pb_rows.append(f"- {activity_type_key} | {dist} | {a.when[:10]}")
        if pb_rows:
            sections.append(
                "## PERSONAL BESTS (top 5 per activity_type_key by distance)\n"
                + "\n".join(pb_rows)
            )

    context = "\n\n".join(sections)

    # truncate if too long, dropping oldest activities
    if len(context) > MAX_CONTEXT_CHARS:
        _logger.warning(
            "context: truncating context to fit token budget",
            length=len(context),
            max_chars=MAX_CONTEXT_CHARS,
        )
        context = context[:MAX_CONTEXT_CHARS]

    return context
