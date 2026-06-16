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
"""Insight card builders for the Banister model.

Body-lines markup convention used by the ``trimp-insight-card`` macro::

    "## Section Title"   → section header (horizontal rule + label)
    "@@label|val|pct|hex" → gauge bar (pct 0..100 pre-computed)
    ""                   → vertical spacer
    other                → body paragraph
"""

import datetime

from mytral.backends import entities as entities_mod
from mytral.metrics.banister import _entities


def _pct_rank(value: float, all_values: list[float]) -> float:
    """Return percentile rank of value within all_values (0-100, higher is better)."""
    if not all_values:
        return 50.0
    below = sum(1 for v in all_values if v < value)
    return below / len(all_values) * 100.0


def _gauge_pct(value: float, vmin: float, vmax: float) -> int:
    """Return a 0..100 integer percentage for a gauge bar."""
    if vmax <= vmin:
        return 50
    pct = (value - vmin) / (vmax - vmin) * 100.0
    return max(0, min(100, int(round(pct))))


def _gauge(label: str, value: float, vmin: float, vmax: float, color: str) -> str:
    """Build a gauge-bar markup line."""
    display = f"{value:+.0f}" if vmin < 0 else f"{value:.0f}"
    return f"@@{label}|{display}|{_gauge_pct(value, vmin, vmax)}|{color}"


def _describe_performance_zone(perf: float) -> tuple[str, str, str]:
    """Return (badge_text, color_hex, explanation) for a performance value."""
    if perf > 20.0:
        return (
            "FRESH",
            "#2fb344",
            "Your fitness significantly outweighs your fatigue. "
            "This is the ideal window for a race or high-quality session — "
            "your body has absorbed recent training and is ready to perform.",
        )
    if perf >= 0.0:
        return (
            "OPTIMAL",
            "#2fb344",
            "Training load is balanced: fitness gains are keeping pace "
            "with fatigue. You can maintain this rhythm or push harder.",
        )
    if perf >= -20.0:
        return (
            "TIRED",
            "#f59f00",
            "Short-term fatigue is slightly outpacing fitness. "
            "This is normal after hard blocks — a lighter day or two "
            "will bring you back to optimal.",
        )
    return (
        "OVERREACHED",
        "#d63939",
        "Fatigue is significantly ahead of fitness. Your injury risk "
        "is elevated and training quality will suffer. "
        "Prioritize recovery: easy sessions, sleep, and nutrition.",
    )


def _build_state_card(
    latest: _entities.BanisterRow, rows: list[_entities.BanisterRow]
) -> _entities.InsightCard:
    """Build the current-state insight card with badges and gauges."""
    state_label = latest.diagnosis.capitalize()
    zone_badge, zone_color, zone_explanation = _describe_performance_zone(
        latest.performance
    )

    all_perf = [r.performance for r in rows]
    all_fit = [r.fitness for r in rows]
    all_fat = [r.fatigue for r in rows]
    perf_pct = _pct_rank(latest.performance, all_perf)
    perf_min = min(all_perf) if all_perf else 0.0
    perf_max = max(all_perf) if all_perf else 0.0
    fit_min = min(all_fit) if all_fit else 0.0
    fit_max = max(all_fit) if all_fit else 0.0
    fat_min = min(all_fat) if all_fat else 0.0
    fat_max = max(all_fat) if all_fat else 0.0

    lines = [
        "## Your Performance",
        _gauge("Performance", latest.performance, perf_min, perf_max, zone_color),
        (
            f"Your predicted performance is {latest.performance:+.0f} — "
            f"historical range {perf_min:+.0f} to {perf_max:+.0f}. "
            f"You are at the {perf_pct:.0f}th percentile."
        ),
        zone_explanation,
        "",
        "## Your Fitness (green)",
        _gauge("Fitness", latest.fitness, fit_min, fit_max, "#2fb344"),
        (
            f"Fitness is {latest.fitness:.0f} (range {fit_min:.0f}–{fit_max:.0f}). "
            "This is your 42-day chronic load — it builds slowly (τ≈42d) and "
            "decays slowly. Higher is better: it means your aerobic engine is growing."
        ),
        "",
        "## Your Fatigue (red)",
        _gauge("Fatigue", latest.fatigue, fat_min, fat_max, "#d63939"),
        (
            f"Fatigue is {latest.fatigue:.0f} (range {fat_min:.0f}–{fat_max:.0f}). "
            "This is your 7-day acute load — it rises fast after hard sessions "
            "(τ≈7d) and fades fast with rest."
        ),
        "",
        "## The Math",
        (
            "k1 = 1.0 (fitness gain) vs k2 = 2.0 (fatigue penalty). "
            "Fatigue hurts performance ~2× more than fitness helps it — "
            "it takes ~2 easy days to offset 1 hard day. "
            "Recovery days with TRIMP below 25 earn a negative impulse "
            "that actively reduces fatigue (Busso 2002)."
        ),
    ]

    return _entities.InsightCard(
        kind="state",
        title=f"Current State: {state_label}",
        body_lines=lines,
        zone_badge=zone_badge,
        zone_color=zone_color,
    )


def _build_best_form_card(
    rows: list[_entities.BanisterRow], annotations: list
) -> _entities.InsightCard | None:
    """Build the best-race-form insight card with buildup explanation."""
    peak_annotations = [a for a in annotations if a.kind == "peak"]
    if not peak_annotations:
        return None
    peak = peak_annotations[0]
    peak_idx = next((i for i, r in enumerate(rows) if r.date == peak.date), None)
    if peak_idx is None:
        return None
    peak_row = rows[peak_idx]

    buildup_start = max(0, peak_idx - 42)
    buildup_rows = rows[buildup_start:peak_idx]
    buildup_days_with_trimp = [r for r in buildup_rows if r.trimp > 10.0]
    avg_trimp = (
        sum(r.trimp for r in buildup_days_with_trimp) / len(buildup_days_with_trimp)
        if buildup_days_with_trimp
        else 0.0
    )
    hard_count = sum(1 for r in buildup_rows if r.trimp > 100.0)

    # gauge: where does peak perf sit in the history?
    all_perf = [r.performance for r in rows]
    perf_min = min(all_perf)
    perf_max = max(all_perf)

    lines = [
        _gauge("Peak Performance", peak.value, perf_min, perf_max, "#fab005"),
        (
            f"On {peak.date.isoformat()}, your predicted performance hit "
            f"{peak.value:+.0f} — the highest in your recorded history. "
            f"Fitness was {peak_row.fitness:.0f}, fatigue was {peak_row.fatigue:.0f}."
        ),
        "",
        "## How You Got There",
        (
            f"The 42 days leading up to this peak: "
            f"{len(buildup_days_with_trimp)} training sessions, "
            f"average TRIMP {avg_trimp:.0f}, "
            f"{hard_count} hard sessions (TRIMP > 100)."
        ),
        (
            "This is the classic Banister pattern: a 6-week block of consistent "
            "training builds fitness (τ≈42d), then a short taper lets fatigue "
            "dissipate (τ≈7d) while fitness stays high. "
            f"To replicate: aim for ~{avg_trimp:.0f} avg daily TRIMP over 6 weeks, "
            "then taper 5–7 days before your A-race."
        ),
    ]
    return _entities.InsightCard(
        kind="best_form",
        title=f"Best Race Form Ever: {peak.date.isoformat()}",
        body_lines=lines,
        annotation_id=peak.id,
        zone_badge=f"+{peak.value:.0f}",
        zone_color="#fab005",
    )


def _build_overreaching_card(
    annotations: list,
) -> _entities.InsightCard | None:
    """Build the overreaching-episodes insight card."""
    overreach_annotations = [a for a in annotations if a.kind == "overreach"]
    if not overreach_annotations:
        return None

    count = len(overreach_annotations)
    lines: list[str] = [
        (
            f"We detected {count} episode(s) where your performance dropped "
            f"below -20 and stayed there for 4+ days — the clinical definition "
            f"of overreaching."
        ),
        (
            "Overreaching means fatigue has accumulated faster than your body "
            "can recover. Functional overreaching is part of planned overload, "
            "but sustained overreaching can lead to overtraining syndrome."
        ),
        "",
        "## Episodes",
    ]
    for oa in overreach_annotations[:3]:
        lines.append(
            f"• {oa.date.isoformat()} — {oa.label}. "
            "Check for life stress, poor sleep, or illness around this period."
        )
    return _entities.InsightCard(
        kind="overreaching",
        title=f"Overreaching Episodes: {count} detected",
        body_lines=lines,
        zone_badge=str(count),
        zone_color="#d63939",
    )


def _build_pbs_card(
    annotations: list, rows: list[_entities.BanisterRow]
) -> _entities.InsightCard | None:
    """Build the personal-bests insight card with range context."""
    lines: list[str] = []

    fitness_pb = next((a for a in annotations if a.kind == "fitness_pb"), None)
    if fitness_pb:
        all_fit = [r.fitness for r in rows]
        lines.append("## Fitness PB")
        lines.append(
            _gauge(
                "Fitness PB",
                fitness_pb.value,
                min(all_fit),
                max(all_fit),
                "#2fb344",
            )
        )
        lines.append(
            f"Highest chronic training load: {fitness_pb.value:.0f} "
            f"on {fitness_pb.date.isoformat()}. "
            "Reflects the peak of your aerobic base development."
        )
        lines.append("")

    peak_annotations = [a for a in annotations if a.kind == "peak"]
    if peak_annotations:
        all_perf = [r.performance for r in rows]
        lines.append("## Best Race Form")
        lines.append(
            _gauge(
                "Race Form PB",
                peak_annotations[0].value,
                min(all_perf),
                max(all_perf),
                "#fab005",
            )
        )
        lines.append(
            f"{peak_annotations[0].value:+.0f} on "
            f"{peak_annotations[0].date.isoformat()} — "
            "your best predicted performance day."
        )
        lines.append("")

    overreach_annotations = [a for a in annotations if a.kind == "overreach"]
    if overreach_annotations:
        all_perf = [r.performance for r in rows]
        worst = min(overreach_annotations, key=lambda a: a.value)
        lines.append("## Most Fatigued")
        lines.append(
            _gauge(
                "Fatigue Trough",
                worst.value,
                min(all_perf),
                max(all_perf),
                "#d63939",
            )
        )
        lines.append(
            f"{worst.value:+.0f} on {worst.date.isoformat()} — "
            "your deepest fatigue trough."
        )
        lines.append("")

    if not lines:
        return None

    # global context
    all_perf = [r.performance for r in rows]
    avg_perf = sum(all_perf) / len(all_perf) if all_perf else 0.0
    pct_positive = (
        sum(1 for p in all_perf if p > 0) / len(all_perf) * 100 if all_perf else 0.0
    )
    lines.append("## Your Baseline")
    lines.append(
        f"Average performance: {avg_perf:+.0f}. "
        f"You have been in positive territory (fresh/optimal) "
        f"{pct_positive:.0f}% of the time."
    )

    return _entities.InsightCard(
        kind="pbs",
        title="Personal Bests & Benchmarks",
        body_lines=lines,
        zone_badge=f"{pct_positive:.0f}% positive",
        zone_color="#2fb344" if pct_positive >= 50 else "#f59f00",
    )


def _build_projection_card(
    rows: list[_entities.BanisterRow],
    projection: list[_entities.BanisterRow],
    latest: _entities.BanisterRow,
) -> _entities.InsightCard | None:
    """Build the forward-projection insight card."""
    if not projection or len(rows) < 28:
        return None

    lookback = min(28, len(rows))
    mean_load = sum(r.trimp for r in rows[-lookback:]) / lookback

    lines: list[str] = [
        (
            f"If you maintain your recent average daily TRIMP of {mean_load:.0f} "
            f"(last {lookback} days), here is where your numbers go:"
        ),
        "",
    ]

    # add checkpoint lines with zone labels
    for d in [14, 28, 42]:
        if d <= len(projection):
            p = projection[d - 1]
            zone = _entities._classify_performance(p.performance)
            lines.append(f"## Day {d} → {zone.upper()}")
            lines.append(
                f"Fitness {p.fitness:.0f}  ·  Fatigue {p.fatigue:.0f}  ·  "
                f"Performance {p.performance:+.0f}"
            )
            lines.append("")

    # fitness PB tracking
    current_best_fit = max(r.fitness for r in rows)
    future_best_fit = max(p.fitness for p in projection)
    if future_best_fit > current_best_fit:
        pb_day = next(
            i + 1 for i, p in enumerate(projection) if p.fitness > current_best_fit
        )
        lines.append(
            f"✓ New Fitness PB in ~{pb_day} days "
            f"({future_best_fit:.0f} vs current {current_best_fit:.0f})."
        )

    # performance improvement tracking
    future_best_perf = max(p.performance for p in projection)
    if future_best_perf > latest.performance:
        perf_pb_day = next(
            i + 1
            for i, p in enumerate(projection)
            if p.performance > latest.performance
        )
        lines.append(
            f"✓ Performance improves from {latest.performance:+.0f} "
            f"to {future_best_perf:+.0f} by day {perf_pb_day}."
        )

    if latest.performance < 0:
        lines.append(
            "⚠ Performance is negative now — a recovery week "
            "would speed up your return to the optimal zone."
        )

    # future best perf for zone badge
    future_zone_badge, future_zone_color, _ = _describe_performance_zone(
        future_best_perf
    )
    return _entities.InsightCard(
        kind="projection",
        title="Projection (repeating your recent load pattern)",
        body_lines=lines,
        zone_badge=future_zone_badge,
        zone_color=future_zone_color,
    )


def _build_race_window_card(
    rows: list[_entities.BanisterRow], projection: list[_entities.BanisterRow]
) -> _entities.InsightCard | None:
    """Build the optimal-race-window insight card."""
    if not projection or len(rows) < 28:
        return None
    cross_day = None
    for i, p in enumerate(projection):
        if p.performance >= 0:
            cross_day = i + 1
            break
    if not cross_day:
        return None
    cross_date = projection[cross_day - 1].date
    peak_in_proj = max(p.performance for p in projection)
    peak_day = next(
        i + 1 for i, p in enumerate(projection) if p.performance == peak_in_proj
    )
    peak_date = projection[peak_day - 1].date
    return _entities.InsightCard(
        kind="race_window",
        title="Optimal Race Window",
        body_lines=[
            (
                f"Performance crosses into positive around Day {cross_day} "
                f"({cross_date.isoformat()}) — your form becomes race-ready."
            ),
            (
                f"Projected peak: +{peak_in_proj:.0f} on Day {peak_day} "
                f"({peak_date.isoformat()}). "
                f"Target this day for your A-race."
            ),
            (
                f"Race window: {cross_date.isoformat()} – "
                f"{cross_date + datetime.timedelta(days=9)}."
            ),
            "",
            (
                "The model runs your recent average load forward 56 days. "
                "With constant load, fitness keeps accumulating while fatigue "
                "stays steady — performance eventually crosses into positive. "
                "The exact date depends on your current fitness/fatigue gap."
            ),
        ],
        zone_badge=f"Day {cross_day}",
        zone_color="#206bc4",
    )


def compute_insights(
    rows: list[_entities.BanisterRow],
    projection: list[_entities.BanisterRow],
    annotations: list,
    user_history: list[entities_mod.ActivityEntity] | None = None,
) -> list[_entities.InsightCard]:
    """Build the insight cards for the global page."""
    if not rows:
        return []

    cards: list[_entities.InsightCard] = []
    cards.append(_build_state_card(rows[-1], rows))

    best_form = _build_best_form_card(rows, annotations)
    if best_form:
        cards.append(best_form)

    overreaching = _build_overreaching_card(annotations)
    if overreaching:
        cards.append(overreaching)

    pbs = _build_pbs_card(annotations, rows)
    if pbs:
        cards.append(pbs)

    projection_card = _build_projection_card(rows, projection, rows[-1])
    if projection_card:
        cards.append(projection_card)

    race_window = _build_race_window_card(rows, projection)
    if race_window:
        cards.append(race_window)

    return cards
