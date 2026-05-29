# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import datetime
import enum
import itertools
import json
import math
from typing import Any

from bokeh import embed as bokeh_embed
from bokeh import layouts as bokeh_layouts
from bokeh import models as bokeh_models
from bokeh import plotting as bokeh_plt
from bokeh import transform as bokeh_transform
from bokeh.models import ColumnDataSource
from bokeh.palettes import Category10_10 as bokeh_palette
from bokeh.palettes import Viridis256 as bokeh_viridis256

from mytral import app_logger
from mytral import cals
from mytral import commons
from mytral import settings
from mytral import stats
from mytral import utils
from mytral import views
from mytral.backends import entities
from mytral.recordings.models import RecordingData

BOKEH_WEEK_DAYS = ["Sun", "Sat", "Fri", "Thu", "Wed", "Tue", "Mon"]
VIEW_WIDTH_DEFAULT = 1100
VIEW_WIDTH_MOBILE = 500


class ChartType(enum.Enum):
    KM = "km"
    SUM_KM = "sum_km"
    KG = "kg"
    SUM_KG = "sum_kg"
    HOUR = "hour"
    SUM_HOUR = "sum_hour"
    WEIGHT = "weight"
    RESTING_HR = "resting_hr"


#
# helper functions
#


def _apply_y_axis_formatter(fig, aspect: commons.StatsAspect) -> None:
    """apply y-axis formatter based on aspect type."""
    match aspect:
        case commons.StatsAspect.DURATION:
            fig.yaxis.formatter = bokeh_models.CustomJSTickFormatter(
                code="""
                    var h = Math.floor(tick / 3600);
                    var m = Math.floor((tick % 3600) / 60);
                    var s = Math.floor(tick % 60);
                    var hh = h + 'h';
                    var mm = (m < 10 ? '0' : '') + m + "'";
                    var ss = (s < 10 ? '0' : '') + s + '"';
                    return hh + mm + ss;
                """
            )
        case commons.StatsAspect.KGS:
            fig.yaxis.formatter = bokeh_models.CustomJSTickFormatter(
                code="return tick + ' kg';"
            )
        case commons.StatsAspect.DISTANCE:
            fig.yaxis.formatter = bokeh_models.CustomJSTickFormatter(
                code="return tick + ' km';"
            )


def _apply_y_axis_formatter_for_chart_type(fig, chart_type: ChartType) -> None:
    """apply y-axis formatter based on chart type."""
    if chart_type == ChartType.WEIGHT:
        fig.yaxis.formatter = bokeh_models.CustomJSTickFormatter(
            code="return tick.toFixed(1) + ' kg';"
        )
        return
    if chart_type == ChartType.RESTING_HR:
        fig.yaxis.formatter = bokeh_models.CustomJSTickFormatter(
            code="return tick + ' BPM';"
        )
        return
    aspect = None
    if chart_type in [ChartType.HOUR, ChartType.SUM_HOUR]:
        aspect = commons.StatsAspect.DURATION
    elif chart_type in [ChartType.KG, ChartType.SUM_KG]:
        aspect = commons.StatsAspect.KGS
    elif chart_type in [ChartType.KM, ChartType.SUM_KM]:
        aspect = commons.StatsAspect.DISTANCE
    if aspect is not None:
        _apply_y_axis_formatter(fig, aspect)


def _create_line_with_data_source(
    fig, x: list, y: list, aspect: commons.StatsAspect, color: str, **kwargs
) -> bokeh_models.GlyphRenderer:
    """create a line with optional data source for duration tooltips."""
    if commons.StatsAspect.DURATION == aspect:
        return fig.line(
            color=color,
            source=ColumnDataSource(
                {
                    "x": x,
                    "y": y,
                    "strtime": [cals.seconds_to_chart_time(s) for s in y],
                }
            ),
            **kwargs,
        )
    else:
        return fig.line(x, y, color=color, **kwargs)


def _add_hover_tool_with_tooltips(
    fig, aspect: commons.StatsAspect, renderers: list, mode: str = "vline"
) -> None:
    """add hover tool with appropriate tooltips based on aspect type."""
    match aspect:
        case commons.StatsAspect.DURATION:
            tooltips = "@strtime"
        case commons.StatsAspect.DISTANCE:
            tooltips = "@y{int} km"
        case commons.StatsAspect.KGS:
            tooltips = "@y{int} kg"
        case commons.StatsAspect.ACTIVITIES:
            tooltips = "@y{int} activities"
        case _:
            tooltips = "@y{int}"

    fig.add_tools(
        bokeh_models.HoverTool(tooltips=tooltips, renderers=renderers, mode=mode)
    )


#
# demo charts
#


def demo() -> tuple[str, Any]:
    fig = bokeh_plt.figure(title="Example data")
    fig.line([1, 2, 3, 4], [2, 4, 6, 8])
    script, div = bokeh_embed.components(fig)

    return script, div


#
# production charts
#


def symptoms_in_time(
    symptoms: settings.UserSymptoms,
    activities: list[entities.ActivityEntity],
    is_mobile_view: bool = False,
) -> tuple[str, Any]:
    """Scatter plot of the symptoms in time:

    - x-axis: date
    - y-axis: symptom & its occurrence in time

    """
    fig = bokeh_plt.figure(
        title="Symptoms in time",
        x_axis_type="datetime",
        background_fill_color="#fafafa",
        toolbar_location="below" if not is_mobile_view else None,
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550,
    )
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    # map: number -> label, collect dates for each symptom
    y_labels = {}
    symptom_dates = {}

    for symptom_key, symptom in symptoms.symptoms_by_key.items():
        symptom_dates[symptom_key] = []

    for activity in activities:
        if activity.sickness_symptoms:
            for ss in activity.sickness_symptoms:
                if ss.symptom in symptom_dates:
                    date_obj = datetime.datetime(
                        activity.when_year,
                        activity.when_month,
                        activity.when_day,
                    )
                    symptom_dates[ss.symptom].append(date_obj)

    symptom_count = 0
    for symptom_key, dates in sorted(symptom_dates.items()):
        if dates:
            symptom_count += 1
            symptom_obj = symptoms.symptoms_by_key.get(symptom_key)
            symptom_name = symptom_obj.name if symptom_obj else symptom_key
            y_labels[symptom_count] = symptom_name

            y = [symptom_count] * len(dates)
            fig.circle(dates, y, size=8, color="red", alpha=0.6, line_color="darkred")

    if is_mobile_view:
        y_labels = {k: utils.string_ellipsis(y_labels[k]) for k in y_labels}

    if y_labels:
        fig.yaxis.ticker = list(y_labels.keys())
        fig.yaxis.major_label_overrides = y_labels
        fig.xaxis.formatter = bokeh_models.DatetimeTickFormatter(years="%B %Y")
    else:
        fig.text(
            x=[datetime.datetime(2020, 1, 1)],
            y=[1],
            text=["No symptom data available"],
            text_font_size="14pt",
            text_color="gray",
            text_align="center",
        )

    script, div = bokeh_embed.components(fig)

    return script, div


def me_symptoms_scatter(
    injuries: list[dict],
    symptoms_registry: settings.UserSymptoms,
    year: int,
    is_mobile_view: bool = False,
) -> tuple[str, Any] | tuple[None, None]:
    """Scatter plot of symptom health over time for the /me page.

    - x-axis: date of occurrence
    - y-axis: health percentage (0-100 %)
    - color: unique color per symptom type
    - size: constant 14 px circles
    - legend: one entry per symptom type
    - tooltips: date, symptom name, health %, body part, side
    - range tool: navigation strip below the main figure

    Parameters
    ----------
    injuries : list[dict]
        pre-computed injury records from _get_active_injuries
    symptoms_registry : settings.UserSymptoms
        user symptom type registry for name lookup
    year : int
        currently selected year (0 = all years)
    is_mobile_view : bool, optional
        render a narrower, toolbar-free variant for mobile

    Returns
    -------
    tuple[str, Any]
        (bokeh script, bokeh div) ready for template injection
    """
    if not injuries:
        return None, None

    # assign a stable color to each unique symptom key
    unique_keys = sorted({inj["symptom"] for inj in injuries})
    color_cycle = list(bokeh_palette) + [
        "#e377c2",
        "#7f7f7f",
        "#bcbd22",
        "#17becf",
        "#aec7e8",
        "#ffbb78",
        "#98df8a",
        "#ff9896",
    ]
    symptom_color = {
        key: color_cycle[i % len(color_cycle)] for i, key in enumerate(unique_keys)
    }

    def _symptom_name(key: str) -> str:
        obj = symptoms_registry.symptoms_by_key.get(key)
        return obj.name if obj else key

    # build one ColumnDataSource per symptom for clean legend entries
    year_label = "All Years" if year == 0 else str(year)
    title = f"Symptom Health Over Time — {year_label}"

    width = VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT

    # default visible window depends on the selected year
    today = datetime.datetime.now()
    current_year = today.year
    if year == 0 or year == current_year:
        # all-years view or current year: show last 12 months
        x_range_start = today - datetime.timedelta(days=365)
        x_range_end = today + datetime.timedelta(days=15)
    else:
        # specific past year: show full Jan 1 – Dec 31 of that year
        x_range_start = datetime.datetime(year, 1, 1)
        x_range_end = datetime.datetime(year, 12, 31)

    fig = bokeh_plt.figure(
        title=title,
        x_axis_type="datetime",
        x_range=(x_range_start, x_range_end),
        y_range=(-5, 105),
        background_fill_color="#fafafa",
        toolbar_location="above" if not is_mobile_view else None,
        width=width,
        height=420,
        tools="pan,wheel_zoom,reset,save" if not is_mobile_view else "",
    )
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None
    fig.yaxis.axis_label = "Health %"
    fig.yaxis.formatter = bokeh_models.CustomJSTickFormatter(code="return tick + '%';")
    fig.xaxis.formatter = bokeh_models.DatetimeTickFormatter(
        days="%b %d",
        months="%b %Y",
        years="%Y",
    )
    fig.xgrid.grid_line_color = "#e9ecef"
    fig.ygrid.grid_line_color = "#e9ecef"

    # horizontal reference lines
    for pct, color, label in [
        (100, "#2fb344", "Full health"),
        (75, "#f59f00", ""),
        (50, "#e67e22", ""),
        (0, "#d63939", "Severe"),
    ]:
        fig.line(
            x=[datetime.datetime(2000, 1, 1), datetime.datetime(2100, 1, 1)],
            y=[pct, pct],
            line_color=color,
            line_alpha=0.25,
            line_width=1,
            line_dash="dashed",
        )

    hover_renderers = []
    select_renderers_data = []

    for sym_key in unique_keys:
        sym_injuries = [inj for inj in injuries if inj["symptom"] == sym_key]
        if not sym_injuries:
            continue

        dates = [
            datetime.datetime(
                inj["activity_year"], inj["activity_month"], inj["activity_day"]
            )
            for inj in sym_injuries
        ]
        health_vals = [inj["health"] for inj in sym_injuries]
        body_parts = [
            (inj.get("body_part") or "—").replace("_", " ").title()
            for inj in sym_injuries
        ]
        sides = [inj.get("side") or "—" for inj in sym_injuries]
        date_strs = [d.strftime("%d %b %Y") for d in dates]
        sym_names = [_symptom_name(sym_key)] * len(dates)

        source = ColumnDataSource(
            data=dict(
                x=dates,
                y=health_vals,
                symptom=sym_names,
                date_str=date_strs,
                body_part=body_parts,
                side=sides,
            )
        )

        color = symptom_color[sym_key]
        renderer = fig.circle(
            x="x",
            y="y",
            source=source,
            size=14,
            color=color,
            alpha=0.80,
            line_color="white",
            line_width=1.5,
            legend_label=_symptom_name(sym_key),
        )
        hover_renderers.append(renderer)
        select_renderers_data.append((source, color))

    fig.add_tools(
        bokeh_models.HoverTool(
            renderers=hover_renderers,
            tooltips=[
                ("Symptom", "@symptom"),
                ("Date", "@date_str"),
                ("Health", "@y{0}%"),
                ("Body part", "@body_part"),
                ("Side", "@side"),
            ],
            point_policy="follow_mouse",
        )
    )

    if fig.legend:
        fig.legend.location = "top_left"
        fig.legend.click_policy = "hide"
        fig.legend.background_fill_alpha = 0.85
        fig.legend.border_line_color = "#dee2e6"
        fig.legend.label_text_font_size = "11px"

    if is_mobile_view:
        script, div = bokeh_embed.components(fig)
        return script, div

    # range-tool navigation strip
    select = bokeh_plt.figure(
        title="Drag the selection box to zoom the chart above",  # IMPROVE make constant
        height=110,  # IMPROVE make this constant
        width=width,
        y_range=fig.y_range,
        x_axis_type="datetime",
        y_axis_type=None,
        tools="",
        toolbar_location=None,
        background_fill_color="#efefef",  # IMPROVE: make this constant
    )
    select.sizing_mode = "scale_width"
    select.title.text_font_size = "10px"
    select.title.text_color = "#6c757d"
    select.xaxis.formatter = bokeh_models.DatetimeTickFormatter(
        days="%b %d", months="%b %Y", years="%Y"
    )

    for source, color in select_renderers_data:
        select.circle(
            x="x",
            y="y",
            source=source,
            size=5,
            color=color,
            alpha=0.5,
            line_color=None,
        )
    select.ygrid.grid_line_color = None

    range_tool = bokeh_models.RangeTool(x_range=fig.x_range, start_gesture="pan")
    range_tool.overlay.fill_color = "#206bc4"
    range_tool.overlay.fill_alpha = 0.15
    select.add_tools(range_tool)

    layout = bokeh_layouts.column(fig, select, sizing_mode="scale_width")
    script, div = bokeh_embed.components(layout)
    return script, div


def gear_in_time(
    user_gear: settings.UserGear,
    gear_stats: stats.UserGearStats,
    is_mobile_view: bool = False,
) -> tuple[str, Any]:
    fig = bokeh_plt.figure(
        title="Gear usage in time",
        y_axis_type="datetime",
        background_fill_color="#fafafa",
        toolbar_location="below" if not is_mobile_view else None,
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550,
    )
    # autofit width
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    # map: number -> label
    y_labels = {}

    gear_count = 0
    for e, g_key in enumerate(user_gear.gear_by_key):
        stat = gear_stats.stats(g_key)
        # check if stat exists and has valid date range
        if stat and stat.stat_from and stat.stat_to:
            gear_count += 1

            x = []
            y = []

            y_labels[gear_count] = user_gear.gear_by_key[g_key].name
            y.append(gear_count)
            t_split = stat.stat_from.split("/")
            x.append(
                datetime.datetime(int(t_split[0]), int(t_split[1]), int(t_split[2]))
            )

            y.append(gear_count)
            t_split = stat.stat_to.split("/")
            x.append(
                datetime.datetime(int(t_split[0]), int(t_split[1]), int(t_split[2]))
            )

            fig.line(
                x,
                y,
                color="green",
                line_cap="round",
                line_width=3,
            )

    if is_mobile_view:
        y_labels = {k: utils.string_ellipsis(y_labels[k]) for k in y_labels}

    # only set labels if we have data
    if y_labels:
        fig.yaxis.ticker = list(y_labels.keys())
        fig.yaxis.major_label_overrides = y_labels
        fig.xaxis.formatter = bokeh_models.DatetimeTickFormatter(years="%B %Y")
    else:
        # add text annotation when no data
        fig.text(
            x=[datetime.datetime(2020, 1, 1)],
            y=[1],
            text=["No gear usage data available"],
            text_font_size="14pt",
            text_color="gray",
            text_align="center",
        )

    script, div = bokeh_embed.components(fig)

    return script, div


def exercises_in_time(
    exercises: settings.UserExercises,
    activities: list[entities.ActivityEntity],
    is_mobile_view: bool = False,
) -> tuple[str, Any]:
    """Scatter plot of exercises in time:

    - x-axis: date
    - y-axis: exercise & its occurrence in time

    """
    fig = bokeh_plt.figure(
        title="Exercises in time",
        x_axis_type="datetime",
        background_fill_color="#fafafa",
        toolbar_location="below" if not is_mobile_view else None,
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550,
    )
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    y_labels = {}
    exercise_dates = {}

    for exercise_key, exercise in exercises.exercise_by_key.items():
        exercise_dates[exercise_key] = []

    for activity in activities:
        if activity.exercises:
            for ex in activity.exercises:
                if ex.name in exercise_dates:
                    date_obj = datetime.datetime(
                        activity.when_year,
                        activity.when_month,
                        activity.when_day,
                    )
                    exercise_dates[ex.name].append(date_obj)

    exercise_count = 0
    for exercise_key, dates in sorted(exercise_dates.items()):
        if dates:
            exercise_count += 1
            exercise_obj = exercises.exercise_by_key.get(exercise_key)
            exercise_name = exercise_obj.name if exercise_obj else exercise_key
            y_labels[exercise_count] = exercise_name

            y = [exercise_count] * len(dates)
            fig.circle(dates, y, size=8, color="blue", alpha=0.6, line_color="darkblue")

    if is_mobile_view:
        y_labels = {k: utils.string_ellipsis(y_labels[k]) for k in y_labels}

    if y_labels:
        fig.yaxis.ticker = list(y_labels.keys())
        fig.yaxis.major_label_overrides = y_labels
        fig.xaxis.formatter = bokeh_models.DatetimeTickFormatter(years="%B %Y")
    else:
        fig.text(
            x=[datetime.datetime(2020, 1, 1)],
            y=[1],
            text=["No exercise data available"],
            text_font_size="14pt",
            text_color="gray",
            text_align="center",
        )

    script, div = bokeh_embed.components(fig)

    return script, div


def laps_in_time(
    laps: settings.UserLaps,
    activities: list[entities.ActivityEntity],
    is_mobile_view: bool = False,
) -> tuple[str, Any]:
    """Scatter plot of laps in time:

    - x-axis: date
    - y-axis: lap type & its occurrence in time

    """
    fig = bokeh_plt.figure(
        title="Laps & Routes in time",
        x_axis_type="datetime",
        background_fill_color="#fafafa",
        toolbar_location="below" if not is_mobile_view else None,
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550,
    )
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    y_labels = {}
    lap_dates = {}

    for lap_key, lap in laps.lap_by_key.items():
        lap_dates[lap_key] = []

    for activity in activities:
        if activity.laps:
            for lap in activity.laps:
                if lap.name in lap_dates:
                    date_obj = datetime.datetime(
                        activity.when_year,
                        activity.when_month,
                        activity.when_day,
                    )
                    lap_dates[lap.name].append(date_obj)

    lap_count = 0
    for lap_key, dates in sorted(lap_dates.items()):
        if dates:
            lap_count += 1
            lap_obj = laps.lap_by_key.get(lap_key)
            lap_name = lap_obj.name if lap_obj else lap_key
            y_labels[lap_count] = lap_name

            y = [lap_count] * len(dates)
            fig.circle(
                dates, y, size=8, color="orange", alpha=0.6, line_color="darkorange"
            )

    if is_mobile_view:
        y_labels = {k: utils.string_ellipsis(y_labels[k]) for k in y_labels}

    if y_labels:
        fig.yaxis.ticker = list(y_labels.keys())
        fig.yaxis.major_label_overrides = y_labels
        fig.xaxis.formatter = bokeh_models.DatetimeTickFormatter(years="%B %Y")
    else:
        fig.text(
            x=[datetime.datetime(2020, 1, 1)],
            y=[1],
            text=["No lap data available"],
            text_font_size="14pt",
            text_color="gray",
            text_align="center",
        )

    script, div = bokeh_embed.components(fig)

    return script, div


def outfits_in_time(
    outfits: settings.UserOutfits,
    activities: list[entities.ActivityEntity],
    is_mobile_view: bool = False,
) -> tuple[str, Any]:
    """Scatter plot of outfits in time:

    - x-axis: date
    - y-axis: outfit & its occurrence in time

    """
    fig = bokeh_plt.figure(
        title="Outfits in time",
        x_axis_type="datetime",
        background_fill_color="#fafafa",
        toolbar_location="below" if not is_mobile_view else None,
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550,
    )
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    y_labels = {}
    outfit_dates = {}

    for outfit_key in outfits.outfits_by_key:
        outfit_dates[outfit_key] = []

    for activity in activities:
        if hasattr(activity, "outfit") and activity.outfit:
            if activity.outfit in outfit_dates:
                date_obj = datetime.datetime(
                    activity.when_year,
                    activity.when_month,
                    activity.when_day,
                )
                outfit_dates[activity.outfit].append(date_obj)

    outfit_count = 0
    for outfit_key, dates in sorted(outfit_dates.items()):
        if dates:
            outfit_count += 1
            outfit_obj = outfits.outfits_by_key.get(outfit_key)
            outfit_name = outfit_obj.name if outfit_obj else outfit_key
            y_labels[outfit_count] = outfit_name

            y = [outfit_count] * len(dates)
            fig.circle(dates, y, size=8, color="purple", alpha=0.6, line_color="indigo")

    if is_mobile_view:
        y_labels = {k: utils.string_ellipsis(y_labels[k]) for k in y_labels}

    if y_labels:
        fig.yaxis.ticker = list(y_labels.keys())
        fig.yaxis.major_label_overrides = y_labels
        fig.xaxis.formatter = bokeh_models.DatetimeTickFormatter(years="%B %Y")
    else:
        fig.text(
            x=[datetime.datetime(2020, 1, 1)],
            y=[1],
            text=["No outfit data available"],
            text_font_size="14pt",
            text_color="gray",
            text_align="center",
        )

    script, div = bokeh_embed.components(fig)

    return script, div


def activity_types_in_time(
    activity_types: settings.UserActivityTypes,
    activities: list[entities.ActivityEntity],
    is_mobile_view: bool = False,
) -> tuple[str, Any]:
    """Scatter plot of activity types in time:

    - x-axis: date
    - y-axis: activity type & its occurrence in time

    """
    fig = bokeh_plt.figure(
        title="Activity Types in time",
        x_axis_type="datetime",
        background_fill_color="#fafafa",
        toolbar_location="below" if not is_mobile_view else None,
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550,
    )
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    y_labels = {}
    activity_type_dates = {}

    for at_key, at in activity_types.activity_types_by_key.items():
        activity_type_dates[at_key] = []

    for activity in activities:
        if activity.activity_type_key in activity_type_dates:
            date_obj = datetime.datetime(
                activity.when_year,
                activity.when_month,
                activity.when_day,
            )
            activity_type_dates[activity.activity_type_key].append(date_obj)

    at_count = 0
    for at_key, dates in sorted(activity_type_dates.items()):
        if dates:
            at_count += 1
            at_obj = activity_types.activity_types_by_key.get(at_key)
            at_name = at_obj.name if at_obj else at_key
            y_labels[at_count] = at_name

            y = [at_count] * len(dates)
            fig.circle(
                dates, y, size=8, color="green", alpha=0.6, line_color="darkgreen"
            )

    if is_mobile_view:
        y_labels = {k: utils.string_ellipsis(y_labels[k]) for k in y_labels}

    if y_labels:
        fig.yaxis.ticker = list(y_labels.keys())
        fig.yaxis.major_label_overrides = y_labels
        fig.xaxis.formatter = bokeh_models.DatetimeTickFormatter(years="%B %Y")
    else:
        fig.text(
            x=[datetime.datetime(2020, 1, 1)],
            y=[1],
            text=["No activity type data available"],
            text_font_size="14pt",
            text_color="gray",
            text_align="center",
        )

    script, div = bokeh_embed.components(fig)

    return script, div


def active_in_week(
    activities: list[entities.ActivityEntity],
    activities_weekdays: dict[str, str],
    activity_types: settings.UserActivityTypes,
    is_mobile_view: bool = False,
):
    """Activities within week chart:

    - x-axis: days as strings - Mon, Tue, ...
    - y-axis: time of day (datetime.time(hour, minute))

    Parameters
    ----------
    activities : list[entities.ActivityEntity]
        Activities to be displayed in the chart.
    activities_weekdays : dict[str, str]
        Activities with weekdays - map: activity key -> weekday as string.
    activity_types : settings.UserActivityTypes
        User activity types.
    is_mobile_view : bool
        True if the chart is rendered for mobile view.

    """
    # TODO filter out non-activity_type_key activities
    data: dict[str, list] = {
        "day": [],
        "time": [],
    }
    # use arbitrary reference date for time plotting
    ref_date = datetime.date(2000, 1, 1)
    for a in activities:
        if (
            activity_types.is_sport(a.activity_type_key)
            and a.key in activities_weekdays
        ):
            data["day"].append(activities_weekdays[a.key])
            # convert time to datetime for bokeh datetime axis
            time_obj = datetime.time(a.when_hour, a.when_minute)
            data["time"].append(datetime.datetime.combine(ref_date, time_obj))

    source = bokeh_models.ColumnDataSource(data)

    fig = bokeh_plt.figure(
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=500,
        y_range=BOKEH_WEEK_DAYS,
        x_axis_type="datetime",
        title="Activities within Week",
        toolbar_location="below" if not is_mobile_view else None,
    )
    # autofit width
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    fig.scatter(
        x="time",
        y=bokeh_transform.jitter("day", width=0.6, range=fig.y_range),
        source=source,
        color="green",
        alpha=0.3,
    )

    fig.xaxis.formatter.days = "%Hh"
    fig.x_range.range_padding = 0
    fig.ygrid.grid_line_color = None

    script, div = bokeh_embed.components(fig)

    return script, div


def demo_active_in_week():
    from bokeh.models import ColumnDataSource
    from bokeh.plotting import figure
    from bokeh.sampledata.commits import data
    from bokeh.transform import jitter

    source = ColumnDataSource(data)

    p = figure(
        width=800,
        height=300,
        y_range=BOKEH_WEEK_DAYS,
        x_axis_type="datetime",
        title="Activities within Week",
        toolbar_location="below",
    )

    p.scatter(
        x="time", y=jitter("day", width=0.6, range=p.y_range), source=source, alpha=0.3
    )

    p.xaxis.formatter.days = "%Hh"
    p.x_range.range_padding = 0
    p.ygrid.grid_line_color = None

    script, div = bokeh_embed.components(p)

    return script, div


def _build_overlay_chart(
    rec: RecordingData,
    athlete_metrics: settings.AthleteMetrics | None = None,
) -> tuple[str, Any] | None:
    """Build the overlay (multi-axis) timeseries chart from pre-parsed records."""
    timestamps = rec.timestamps
    hr_values = rec.hr_values
    speed_values = rec.speed_values
    cadence_values = rec.cadence_values
    altitude_values = rec.altitude_values
    power_values = rec.power_values
    has_speed = rec.has_speed
    has_cadence = rec.has_cadence
    has_altitude = rec.has_altitude
    has_power = rec.has_power

    # convert None → NaN for Bokeh (avoids gaps rendering as zero)
    def _nan(v):
        return float("nan") if v is None else v

    hr_plot = [_nan(v) for v in hr_values]
    speed_plot = [_nan(v) for v in speed_values]
    cadence_plot = [_nan(v) for v in cadence_values]
    altitude_plot = [_nan(v) for v in altitude_values]
    power_plot = [_nan(v) for v in power_values]

    source = ColumnDataSource(
        data=dict(
            ts=timestamps,
            hr=hr_plot,
            speed=speed_plot,
            cadence=cadence_plot,
            altitude=altitude_plot,
            power=power_plot,
        )
    )

    fig = bokeh_plt.figure(
        height=640,
        sizing_mode="stretch_width",
        x_axis_type="datetime",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        toolbar_location="above",
        title="Heart Rate Timeseries",
    )
    # set default range to 90 minutes
    if timestamps:
        start_ts = timestamps[0]
        end_ts = start_ts + datetime.timedelta(minutes=90)
        # ensure end_ts does not exceed actual data if it's shorter,
        # but RangeTool typically handles clipping if we just set the range.
        # Actually, setting it to 90m even if shorter is fine for a zoom tool.
        fig.x_range.start = start_ts
        fig.x_range.end = (
            min(end_ts, timestamps[-1]) if timestamps[-1] > start_ts else end_ts
        )
    fig.toolbar.logo = None

    # ensure y-range covers at least the zones if metrics are available
    if athlete_metrics and athlete_metrics.e_z5_high > 0:
        hr_vals = [v for v in hr_values if v is not None and v > 0]
        hr_max = max(hr_vals) if hr_vals else 150
        y_max = max(hr_max, athlete_metrics.e_z5_high) * 1.05
        fig.y_range = bokeh_models.Range1d(start=0, end=y_max)

    # draw HR zones as background rectangles
    if athlete_metrics:
        zone_boundaries = [
            (athlete_metrics.e_z1_low, athlete_metrics.e_z1_high),
            (athlete_metrics.e_z2_low, athlete_metrics.e_z2_high),
            (athlete_metrics.e_z3_low, athlete_metrics.e_z3_high),
            (athlete_metrics.e_z4_low, athlete_metrics.e_z4_high),
            (athlete_metrics.e_z5_low, athlete_metrics.e_z5_high),
        ]
        for i, (low, high) in enumerate(zone_boundaries):
            if high > 0:
                fig.add_layout(
                    bokeh_models.BoxAnnotation(
                        bottom=low,
                        top=high,
                        fill_alpha=0.1,
                        fill_color=HR_ZONE_COLORS[i],
                        level="underlay",
                    )
                )

    # primary y-axis: HR (bpm)
    fig.yaxis.axis_label = "Heart Rate (bpm)"
    hr_line = fig.line(
        "ts",
        "hr",
        source=source,
        color="#e03131",
        line_width=2,
        legend_label="HR (bpm)",
    )

    extra_renderers = []

    if has_speed:
        fig.extra_y_ranges["speed"] = bokeh_models.Range1d(
            start=0,
            end=max((v for v in speed_values if v is not None), default=50) * 1.15,
        )
        fig.add_layout(
            bokeh_models.LinearAxis(y_range_name="speed", axis_label="Speed (km/h)"),
            "right",
        )
        speed_line = fig.line(
            "ts",
            "speed",
            source=source,
            color="#1971c2",
            line_width=1.5,
            legend_label="Speed (km/h)",
            y_range_name="speed",
        )
        extra_renderers.append(speed_line)

    if has_altitude:
        alt_vals = [v for v in altitude_values if v is not None]
        alt_min = min(alt_vals) if alt_vals else 0
        alt_max = max(alt_vals) if alt_vals else 100
        fig.extra_y_ranges["altitude"] = bokeh_models.Range1d(
            start=alt_min - 10, end=alt_max + 10
        )
        fig.add_layout(
            bokeh_models.LinearAxis(y_range_name="altitude", axis_label="Altitude (m)"),
            "right",
        )
        alt_line = fig.line(
            "ts",
            "altitude",
            source=source,
            color="#2f9e44",
            line_width=1.5,
            legend_label="Altitude (m)",
            y_range_name="altitude",
        )
        extra_renderers.append(alt_line)

    if has_cadence:
        fig.extra_y_ranges["cadence"] = bokeh_models.Range1d(
            start=0,
            end=max((v for v in cadence_values if v is not None), default=120) * 1.2,
        )
        cad_line = fig.line(
            "ts",
            "cadence",
            source=source,
            color="#f08c00",
            line_width=1.5,
            legend_label="Cadence (rpm)",
            y_range_name="cadence",
        )
        extra_renderers.append(cad_line)

    if has_power:
        pwr_vals = [v for v in power_values if v is not None]
        pwr_max = max(pwr_vals) if pwr_vals else 300
        # cap power scale at 2000 W (reasonable ceiling for cycling)
        pwr_max = min(pwr_max * 1.15, 2000)
        fig.extra_y_ranges["power"] = bokeh_models.Range1d(start=0, end=pwr_max)
        fig.add_layout(
            bokeh_models.LinearAxis(y_range_name="power", axis_label="Power (W)"),
            "right",
        )
        pwr_line = fig.line(
            "ts",
            "power",
            source=source,
            color="#9c36b5",
            line_width=1.5,
            legend_label="Power (W)",
            y_range_name="power",
        )
        extra_renderers.append(pwr_line)

    tooltips = [("Time", "@ts{%H:%M:%S}"), ("HR", "@hr bpm")]
    if has_speed:
        tooltips.append(("Speed", "@speed km/h"))
    if has_cadence:
        tooltips.append(("Cadence", "@cadence rpm"))
    if has_altitude:
        tooltips.append(("Altitude", "@altitude m"))
    if has_power:
        tooltips.append(("Power", "@power W"))

    hover = bokeh_models.HoverTool(
        renderers=[hr_line],
        tooltips=tooltips,
        formatters={"@ts": "datetime"},
        mode="vline",
    )
    fig.add_tools(hover)

    fig.legend.location = "top_left"
    fig.legend.click_policy = "hide"
    fig.xaxis.axis_label = "Time"
    fig.xgrid.grid_line_color = "#e9ecef"
    fig.ygrid.grid_line_color = "#e9ecef"
    fig.outline_line_color = None

    # range tool
    select = bokeh_plt.figure(
        title="Drag the selection box to zoom the chart above",
        height=100,
        sizing_mode="stretch_width",
        y_range=fig.y_range,
        x_axis_type="datetime",
        y_axis_type=None,
        tools="",
        toolbar_location=None,
        background_fill_color="#efefef",
    )
    select.line("ts", "hr", source=source, color="#e03131", line_width=1)
    select.ygrid.grid_line_color = None
    select.outline_line_color = None

    range_tool = bokeh_models.RangeTool(x_range=fig.x_range, start_gesture="pan")
    range_tool.overlay.fill_color = "#206bc4"
    range_tool.overlay.fill_alpha = 0.15
    select.add_tools(range_tool)

    layout = bokeh_layouts.column(fig, select, sizing_mode="stretch_width")

    return bokeh_embed.components(layout)


def activity_fit_chart(
    recording: RecordingData,
    athlete_metrics: settings.AthleteMetrics | None = None,
) -> tuple[str, Any] | None:
    """Build a Bokeh overlay timeseries chart from a RecordingData instance.

    Renders a multi-line chart with heart rate as the primary series, plus
    optional speed (km/h), cadence, and altitude series when those channels
    are present.

    Parameters
    ----------
    recording : RecordingData
        Pre-parsed recording data loaded via load_parquet().
    athlete_metrics : settings.AthleteMetrics | None
        Optional athlete metrics for HR zones.

    Returns
    -------
    tuple[str, Any] | None
        ``(script, div)`` Bokeh embed components, or ``None`` when the
        recording has no usable samples.
    """
    if not recording.timestamps:
        return None
    return _build_overlay_chart(recording, athlete_metrics=athlete_metrics)


def _build_ridge_chart(
    rec: RecordingData,
    athlete_metrics: settings.AthleteMetrics | None = None,
) -> tuple[str, Any] | None:
    """Build the ridge (swimlane) chart from pre-parsed records."""
    timestamps = rec.timestamps
    hr_values = rec.hr_values
    speed_values = rec.speed_values
    cadence_values = rec.cadence_values
    altitude_values = rec.altitude_values
    has_speed = rec.has_speed
    has_cadence = rec.has_cadence
    has_altitude = rec.has_altitude
    cadence_values = rec.cadence_values
    altitude_values = rec.altitude_values
    has_speed = rec.has_speed
    has_cadence = rec.has_cadence
    has_altitude = rec.has_altitude

    def _nan(v):
        return float("nan") if v is None else v

    # channel definitions: (field, raw_values, label, unit, color)
    all_channels = [
        ("hr", hr_values, "Heart Rate", "bpm", "#e03131"),
        ("speed", speed_values, "Speed", "km/h", "#1971c2"),
        ("cadence", cadence_values, "Cadence", "rpm", "#f08c00"),
        ("altitude", altitude_values, "Altitude", "m", "#2f9e44"),
    ]
    present_flags = [True, has_speed, has_cadence, has_altitude]
    channels = [ch for ch, present in zip(all_channels, present_flags) if present]

    # precompute y ranges per channel so baselines can go into the shared source
    def _y_range(raw: list, field: str) -> tuple[float, float, float]:
        finite = [v for v in raw if v is not None]
        y_min = float(min(finite)) if finite else 0.0
        y_max = float(max(finite)) if finite else 1.0
        # ensure HR range covers zones
        if field == "hr" and athlete_metrics and athlete_metrics.e_z5_high > y_max:
            y_max = float(athlete_metrics.e_z5_high)
        y_pad = (y_max - y_min) * 0.12 or 5.0
        return y_min, y_max, y_pad

    y_ranges: dict[str, tuple[float, float, float]] = {
        field: _y_range(raw, field) for field, raw, *_ in channels
    }

    # build source with channel data and per-channel fill baselines
    source_data: dict = {"ts": timestamps}
    for field, raw, *_ in channels:
        source_data[field] = [_nan(v) for v in raw]
        y_min, _, y_pad = y_ranges[field]
        source_data[f"{field}_base"] = [y_min - y_pad] * len(timestamps)

    source = ColumnDataSource(data=source_data)

    # shared x-range across all panels
    x_range = bokeh_models.Range1d(
        start=timestamps[0],
        end=min(timestamps[0] + datetime.timedelta(minutes=90), timestamps[-1]),
        bounds=(timestamps[0], timestamps[-1]),
    )

    _SWIMLANE_HEIGHT = 200
    _TOOLS = "pan,wheel_zoom,box_zoom,reset,save"

    panels: list[bokeh_plt.figure] = []

    for i, (field, _raw, label, unit, color) in enumerate(channels):
        is_first = i == 0
        is_last = i == len(channels) - 1

        y_min, y_max, y_pad = y_ranges[field]

        panel = bokeh_plt.figure(
            height=_SWIMLANE_HEIGHT,
            sizing_mode="stretch_width",
            x_range=x_range,
            y_range=bokeh_models.Range1d(y_min - y_pad, y_max + y_pad),
            x_axis_type="datetime",
            tools=_TOOLS if is_first else "pan,wheel_zoom,reset",
            toolbar_location="above" if is_first else None,
        )
        if is_first:
            panel.toolbar.logo = None

        # draw HR zones if this is the HR panel
        if field == "hr" and athlete_metrics:
            zone_boundaries = [
                (athlete_metrics.e_z1_low, athlete_metrics.e_z1_high),
                (athlete_metrics.e_z2_low, athlete_metrics.e_z2_high),
                (athlete_metrics.e_z3_low, athlete_metrics.e_z3_high),
                (athlete_metrics.e_z4_low, athlete_metrics.e_z4_high),
                (athlete_metrics.e_z5_low, athlete_metrics.e_z5_high),
            ]
            for j, (low, high) in enumerate(zone_boundaries):
                if high > 0:
                    panel.add_layout(
                        bokeh_models.BoxAnnotation(
                            bottom=low,
                            top=high,
                            fill_alpha=0.1,
                            fill_color=HR_ZONE_COLORS[j],
                            level="underlay",
                        )
                    )

        # filled area under the line — y1 references a source field (required by Bokeh)
        panel.varea(
            x="ts",
            y1=f"{field}_base",
            y2=field,
            source=source,
            fill_color=color,
            fill_alpha=0.15,
        )
        line = panel.line(
            "ts",
            field,
            source=source,
            color=color,
            line_width=1.8,
        )

        # y-axis label on the left
        panel.yaxis.axis_label = f"{label}\n({unit})"
        panel.yaxis.axis_label_text_font_size = "11px"
        panel.yaxis.minor_tick_line_color = None
        panel.xgrid.grid_line_color = "#e9ecef"
        panel.ygrid.grid_line_color = "#e9ecef"
        panel.outline_line_color = None

        # suppress x-axis tick labels on all but the last panel
        if not is_last:
            panel.xaxis.major_label_text_font_size = "0pt"
            panel.xaxis.axis_line_color = "#dee2e6"
            panel.xaxis.major_tick_line_color = "#dee2e6"
        else:
            panel.xaxis.axis_label = "Time"

        panels.append((panel, line))

    # shared Span instance — all CrosshairTool instances update the same model,
    # so hovering any swimlane draws the vertical line across every panel
    shared_vspan = bokeh_models.Span(
        dimension="height",
        line_color="#868e96",
        line_alpha=0.6,
        line_width=1,
    )

    # all-channel tooltip shown by every panel — uses shared ColumnDataSource
    all_tooltips = [("Time", "@ts{%H:%M:%S}")]
    for f, _r, lbl, u, _ in channels:
        all_tooltips.append((lbl, f"@{f} {u}"))

    for panel, line in panels:
        crosshair = bokeh_models.CrosshairTool(overlay=shared_vspan)
        panel.add_tools(crosshair)
        hover = bokeh_models.HoverTool(
            renderers=[line],
            tooltips=all_tooltips,
            formatters={"@ts": "datetime"},
            mode="vline",
        )
        panel.add_tools(hover)

    panel_figs = [p for p, _ in panels]

    # mini range-selector (hr line only) — shows full activity, box = current viewport
    select = bokeh_plt.figure(
        title="Drag the selection box to zoom the chart above",
        height=110,
        sizing_mode="stretch_width",
        x_axis_type="datetime",
        y_axis_type=None,
        tools="",
        toolbar_location=None,
        background_fill_color="#efefef",
    )
    select.line("ts", "hr", source=source, color="#e03131", line_width=1)
    select.ygrid.grid_line_color = None
    select.outline_line_color = None
    select.title.text_font_size = "11px"
    select.title.text_color = "#868e96"

    range_tool = bokeh_models.RangeTool(x_range=x_range, start_gesture="pan")
    range_tool.overlay.fill_color = "#206bc4"
    range_tool.overlay.fill_alpha = 0.15
    select.add_tools(range_tool)

    layout = bokeh_layouts.column(
        *panel_figs, select, sizing_mode="stretch_width", spacing=2
    )
    return bokeh_embed.components(layout)


def activity_fit_chart_ridge(
    recording: RecordingData,
    athlete_metrics: settings.AthleteMetrics | None = None,
) -> tuple[str, Any] | None:
    """Build a Bokeh ridge (swimlane) chart from a RecordingData instance.

    Each data channel (heart rate, speed, cadence, altitude) gets its own
    horizontally-linked panel stacked vertically.  Only channels present in the
    recording are included.  A mini range-selector sits below all panels.

    Parameters
    ----------
    recording : RecordingData
        Pre-parsed recording data loaded via load_parquet().
    athlete_metrics : settings.AthleteMetrics | None
        Optional athlete metrics for HR zones.

    Returns
    -------
    tuple[str, Any] | None
        ``(script, div)`` Bokeh embed components, or ``None`` when the
        recording has no usable samples.
    """
    if not recording.timestamps:
        return None
    return _build_ridge_chart(recording, athlete_metrics=athlete_metrics)


# HR zone palette matching Tabler CSS classes used in athlete-metrics-get.html:
# Z1 bg-green-lt, Z2 bg-teal-lt, Z3 bg-yellow-lt, Z4 bg-orange-lt, Z5 bg-red-lt
HR_ZONE_COLORS: list[str] = [
    "#2fb344",  # Z1 Recovery  (Tabler green)
    "#0ca678",  # Z2 Aerobic   (Tabler teal)
    "#f59f00",  # Z3 Tempo     (Tabler yellow)
    "#f76707",  # Z4 Threshold (Tabler orange)
    "#d63939",  # Z5 Anaerobic (Tabler red)
]
HR_ZONE_LABELS: list[str] = [
    "Z1 Recovery",
    "Z2 Aerobic",
    "Z3 Tempo",
    "Z4 Threshold",
    "Z5 Anaerobic",
]

POWER_ZONE_COLORS: list[str] = [
    "#2fb344",  # PZ1 Recovery      (Tabler green)
    "#0ca678",  # PZ2 Endurance     (Tabler teal)
    "#f59f00",  # PZ3 Tempo         (Tabler yellow)
    "#f76707",  # PZ4 Threshold     (Tabler orange)
    "#d63939",  # PZ5 VO2Max        (Tabler red)
    "#ae3ec9",  # PZ6 Anaerobic     (Tabler purple)
    "#6c757d",  # PZ7 Neuromuscular (Tabler gray)
]
POWER_ZONE_LABELS: list[str] = [
    "PZ1 Recovery",
    "PZ2 Endurance",
    "PZ3 Tempo",
    "PZ4 Threshold",
    "PZ5 VO2Max",
    "PZ6 Anaerobic",
    "PZ7 Neuromuscular",
]


def _build_hr_zones_chart(
    rec: RecordingData,
    athlete_metrics: settings.AthleteMetrics,
) -> tuple[str, Any] | None:
    """Build a horizontal bar chart showing time spent in each HR zone.

    Each sample in the FIT file represents one second of activity. HR values
    are classified into zones Z1–Z5 using the athlete's resolved e_z* boundaries.
    The chart uses the same colour scheme as the Athlete Metrics page.

    Parameters
    ----------
    rec : RecordingData
        Pre-parsed FIT record data.
    athlete_metrics : settings.AthleteMetrics
        Athlete metrics with resolved e_z* zone boundaries.

    Returns
    -------
    tuple[str, Any] | None
        ``(script, div)`` Bokeh embed components, or ``None`` when no valid HR
        data is present.
    """
    zone_boundaries = [
        (athlete_metrics.e_z1_low, athlete_metrics.e_z1_high),
        (athlete_metrics.e_z2_low, athlete_metrics.e_z2_high),
        (athlete_metrics.e_z3_low, athlete_metrics.e_z3_high),
        (athlete_metrics.e_z4_low, athlete_metrics.e_z4_high),
        (athlete_metrics.e_z5_low, athlete_metrics.e_z5_high),
    ]

    # count seconds per zone (1 FIT record ≈ 1 second)
    zone_seconds = [0, 0, 0, 0, 0]
    valid_hr = False
    for hr in rec.hr_values:
        if hr is None or hr <= 0:
            continue
        valid_hr = True
        for i, (low, high) in enumerate(zone_boundaries):
            if low <= hr <= high:
                zone_seconds[i] += 1
                break

    if not valid_hr:
        return None

    # convert seconds to minutes for readability
    zone_minutes = [s / 60.0 for s in zone_seconds]
    total_seconds = sum(zone_seconds)

    # reversed so Z1 appears at the bottom and Z5 at the top
    y_range = HR_ZONE_LABELS[::-1]

    source = ColumnDataSource(
        data=dict(
            zones=HR_ZONE_LABELS,
            minutes=zone_minutes,
            seconds=zone_seconds,
            colors=HR_ZONE_COLORS,
        )
    )

    # annotate total time in the title
    total_min = total_seconds / 60.0
    total_h = int(total_min // 60)
    total_m = int(total_min % 60)
    if total_h:
        time_str = f"Total HR data: {total_h}h {total_m:02d}min"
    else:
        time_str = f"Total HR data: {total_m} min"

    fig = bokeh_plt.figure(
        y_range=y_range,
        height=280,
        sizing_mode="stretch_width",
        tools="save",
        toolbar_location="above",
        title=f"Time in Heart Rate Zones — {time_str}",
    )
    fig.toolbar.logo = None

    fig.hbar(
        y="zones",
        right="minutes",
        left=0,
        height=0.6,
        source=source,
        color="colors",
        line_color="white",
        line_width=1,
    )

    hover = bokeh_models.HoverTool(
        tooltips=[
            ("Zone", "@zones"),
            ("Time", "@minutes{0.1f} min"),
        ]
    )
    fig.add_tools(hover)

    fig.xaxis.axis_label = "Time (minutes)"
    fig.ygrid.grid_line_color = None
    fig.xgrid.grid_line_color = "#e9ecef"
    fig.outline_line_color = None

    return bokeh_embed.components(fig)


def _build_cadence_histogram_chart(rec: RecordingData) -> tuple[str, Any] | None:
    """Build a horizontal cadence histogram with 10 equal-width bins.

    Bins span from 0 to the maximum observed cadence value, divided into 10
    equal intervals. Zero/None cadence samples are excluded from binning.

    Parameters
    ----------
    rec : RecordingData
        Pre-parsed FIT record data.

    Returns
    -------
    tuple[str, Any] | None
        ``(script, div)`` Bokeh embed components, or ``None`` when the
        activity contains no valid cadence data.
    """
    cadence_clean = [c for c in rec.cadence_values if c is not None and c > 0]
    if not cadence_clean:
        return None

    cad_max = max(cadence_clean)
    if cad_max <= 0:
        return None

    num_bins = 10
    bin_width = cad_max / num_bins
    edges = [i * bin_width for i in range(num_bins + 1)]
    counts = [0] * num_bins

    for c in cadence_clean:
        idx = int(c / bin_width)
        # clamp the maximum value into the last bin
        if idx >= num_bins:
            idx = num_bins - 1
        counts[idx] += 1

    # convert counts (seconds) to minutes
    minutes = [cnt / 60.0 for cnt in counts]
    bottoms = edges[:-1]
    tops = edges[1:]
    labels = [f"{int(lo)}–{int(hi)}" for lo, hi in zip(bottoms, tops)]

    # display highest cadence bin at the top
    y_range = labels[::-1]

    source = ColumnDataSource(
        data=dict(
            label=labels,
            minutes=minutes,
        )
    )

    fig = bokeh_plt.figure(
        y_range=y_range,
        height=320,
        sizing_mode="stretch_width",
        tools="save",
        toolbar_location="above",
        title="Cadence Distribution",
    )
    fig.toolbar.logo = None

    fig.hbar(
        y="label",
        right="minutes",
        left=0,
        height=0.6,
        source=source,
        color="#206bc4",
        alpha=0.85,
        line_color="white",
        line_width=1,
    )

    hover = bokeh_models.HoverTool(
        tooltips=[
            ("Cadence", "@label rpm"),
            ("Time", "@minutes{0.1f} min"),
        ]
    )
    fig.add_tools(hover)

    fig.xaxis.axis_label = "Time (minutes)"
    fig.yaxis.axis_label = "Cadence (rpm)"
    fig.ygrid.grid_line_color = None
    fig.xgrid.grid_line_color = "#e9ecef"
    fig.outline_line_color = None

    return bokeh_embed.components(fig)


def _build_power_zones_chart(
    rec: RecordingData,
    athlete_metrics: settings.AthleteMetrics,
) -> tuple[str, Any] | None:
    """Build a horizontal bar chart showing time spent in each power zone.

    Each sample in the FIT file represents one second of activity. Power values
    are classified into zones PZ1–PZ7 using the athlete's resolved e_pz* boundaries.

    Parameters
    ----------
    rec : RecordingData
        Pre-parsed FIT record data.
    athlete_metrics : settings.AthleteMetrics
        Athlete metrics with resolved e_pz* zone boundaries.

    Returns
    -------
    tuple[str, Any] | None
        ``(script, div)`` Bokeh embed components, or ``None`` when no valid power
        data is present.
    """
    zone_boundaries = [
        (athlete_metrics.e_pz1_low, athlete_metrics.e_pz1_high),
        (athlete_metrics.e_pz2_low, athlete_metrics.e_pz2_high),
        (athlete_metrics.e_pz3_low, athlete_metrics.e_pz3_high),
        (athlete_metrics.e_pz4_low, athlete_metrics.e_pz4_high),
        (athlete_metrics.e_pz5_low, athlete_metrics.e_pz5_high),
        (athlete_metrics.e_pz6_low, athlete_metrics.e_pz6_high),
        (athlete_metrics.e_pz7_low, athlete_metrics.e_pz7_high),
    ]

    # check if power zones are properly set (any boundary > 0)
    if not any(high > 0 for _, high in zone_boundaries):
        return None

    # count seconds per zone (1 FIT record ≈ 1 second)
    zone_seconds = [0, 0, 0, 0, 0, 0, 0]
    valid_power = False
    for pwr in rec.power_values:
        if pwr is None or pwr <= 0:
            continue
        valid_power = True
        for i, (low, high) in enumerate(zone_boundaries):
            if low <= pwr <= high:
                zone_seconds[i] += 1
                break

    if not valid_power:
        return None

    # convert seconds to minutes for readability
    zone_minutes = [s / 60.0 for s in zone_seconds]
    total_seconds = sum(zone_seconds)

    # reversed so PZ1 appears at the bottom and PZ7 at the top
    y_range = POWER_ZONE_LABELS[::-1]

    source = ColumnDataSource(
        data=dict(
            zones=POWER_ZONE_LABELS,
            minutes=zone_minutes,
            seconds=zone_seconds,
            colors=POWER_ZONE_COLORS,
        )
    )

    # annotate total time in the title
    total_min = total_seconds / 60.0
    total_h = int(total_min // 60)
    total_m = int(total_min % 60)
    if total_h:
        time_str = f"Total power data: {total_h}h {total_m:02d}min"
    else:
        time_str = f"Total power data: {total_m} min"

    fig = bokeh_plt.figure(
        y_range=y_range,
        height=340,
        sizing_mode="stretch_width",
        tools="save",
        toolbar_location="above",
        title=f"Time in Power Zones — {time_str}",
    )
    fig.toolbar.logo = None

    fig.hbar(
        y="zones",
        right="minutes",
        left=0,
        height=0.6,
        source=source,
        color="colors",
        line_color="white",
        line_width=1,
    )

    hover = bokeh_models.HoverTool(
        tooltips=[
            ("Zone", "@zones"),
            ("Time", "@minutes{0.1f} min"),
        ]
    )
    fig.add_tools(hover)

    fig.xaxis.axis_label = "Time (minutes)"
    fig.ygrid.grid_line_color = None
    fig.xgrid.grid_line_color = "#e9ecef"
    fig.outline_line_color = None

    return bokeh_embed.components(fig)


def _build_power_curve_chart(
    rec: RecordingData,
) -> tuple[str, Any] | None:
    """Build a power curve (peak power vs duration) chart.

    Computes the maximum rolling average power for each duration from 1 second
    to the nearest completed hour of the activity (minimum 1 hour). For example:
    - 30 min activity → shows 1s to 30min
    - 1h 15min activity → shows 1s to 1h
    - 2h 30min activity → shows 1s to 2h
    - 5h activity → shows 1s to 5h

    Parameters
    ----------
    rec : RecordingData
        Pre-parsed FIT record data.

    Returns
    -------
    tuple[str, Any] | None
        ``(script, div)`` Bokeh embed components, or ``None`` when no valid power
        data is present.
    """
    power_clean = [p for p in rec.power_values if p is not None and p > 0]
    if not power_clean:
        return None

    activity_length_sec = len(power_clean)  # seconds
    activity_hours = activity_length_sec / 3600.0

    # Determine maximum duration: nearest completed hour, minimum 1 hour
    if activity_hours < 1.0:
        max_duration_sec = activity_length_sec
    else:
        max_duration_sec = int(activity_hours) * 3600

    # Build durations list: 1s, 5s, 10s, 30s, 1m, 5m, 10m, 20m, 1h, 2h, ...
    durations_sec = [1, 5, 10, 30, 60, 300, 600, 1200, 3600]
    # Add hour boundaries up to max_duration
    for hours in range(2, int(max_duration_sec / 3600) + 1):
        durations_sec.append(hours * 3600)

    # Filter to durations not exceeding activity length
    durations_sec = [d for d in durations_sec if d <= activity_length_sec]

    if not durations_sec:
        return None

    max_powers = []
    for duration in durations_sec:
        # compute rolling average for each window
        max_avg = 0.0
        for i in range(activity_length_sec - duration + 1):
            avg = sum(power_clean[i : i + duration]) / duration
            if avg > max_avg:
                max_avg = avg
        max_powers.append(max_avg)

    # format duration labels for display
    duration_labels = []
    for d in durations_sec:
        if d < 60:
            duration_labels.append(f"{d}s")
        elif d < 3600:
            duration_labels.append(f"{d // 60}m")
        else:
            duration_labels.append(f"{d // 3600}h")

    source = ColumnDataSource(
        data=dict(
            duration=duration_labels,
            power=max_powers,
            duration_sort=durations_sec,
        )
    )

    fig = bokeh_plt.figure(
        x_range=duration_labels,
        height=300,
        sizing_mode="stretch_width",
        tools="save,pan,wheel_zoom,box_zoom,reset",
        toolbar_location="above",
        title="Power Curve (Peak Power by Duration)",
    )
    fig.toolbar.logo = None

    fig.line(
        x="duration",
        y="power",
        source=source,
        line_width=2,
        color="#9c36b5",
        legend_label="Peak Power",
    )
    fig.scatter(
        x="duration",
        y="power",
        source=source,
        size=6,
        color="#9c36b5",
        line_color="white",
        line_width=1,
    )

    hover = bokeh_models.HoverTool(
        tooltips=[
            ("Duration", "@duration"),
            ("Peak Power", "@power{0} W"),
        ]
    )
    fig.add_tools(hover)

    fig.xaxis.axis_label = "Duration"
    fig.yaxis.axis_label = "Power (watts)"
    fig.xgrid.grid_line_color = "#e9ecef"
    fig.ygrid.grid_line_color = "#e9ecef"
    fig.outline_line_color = None
    fig.legend.location = "top_right"

    return bokeh_embed.components(fig)


def _build_power_ts_chart(rec: RecordingData) -> tuple[str, Any] | None:
    """Build a power time-series chart.

    Renders a line chart of power (watts) over activity duration.

    Parameters
    ----------
    rec : RecordingData
        Pre-parsed recording data loaded via load_parquet().

    Returns
    -------
    tuple[str, Any] | None
        ``(script, div)`` Bokeh embed components, or ``None`` when the
        recording has no usable power samples.
    """
    if not rec.timestamps or not rec.power_values:
        return None

    power_clean = [p if p is not None else float("nan") for p in rec.power_values]
    if not any(p is not None and p > 0 for p in rec.power_values):
        return None

    pwr_vals = [v for v in rec.power_values if v is not None and v > 0]
    pwr_max = max(pwr_vals) if pwr_vals else 300
    pwr_max = min(pwr_max * 1.15, 2000)

    source = ColumnDataSource(
        data=dict(
            ts=rec.timestamps,
            power=power_clean,
        )
    )

    fig = bokeh_plt.figure(
        x_axis_type="datetime",
        height=300,
        sizing_mode="stretch_width",
        tools="save,pan,wheel_zoom,box_zoom,reset",
        toolbar_location="above",
        title="Power Over Time",
    )
    fig.toolbar.logo = None

    fig.line(
        "ts",
        "power",
        source=source,
        line_width=2,
        color="#9c36b5",
        legend_label="Power (W)",
    )

    hover = bokeh_models.HoverTool(
        tooltips=[
            ("Time", "@ts{%H:%M:%S}"),
            ("Power", "@power{0} W"),
        ],
        formatters={"@ts": "datetime"},
        mode="vline",
    )
    fig.add_tools(hover)

    fig.xaxis.axis_label = "Time"
    fig.yaxis.axis_label = "Power (watts)"
    fig.y_range = bokeh_models.Range1d(start=0, end=pwr_max)
    fig.xgrid.grid_line_color = "#e9ecef"
    fig.ygrid.grid_line_color = "#e9ecef"
    fig.outline_line_color = None
    fig.legend.location = "top_right"

    return bokeh_embed.components(fig)


def _build_hr_ts_chart(
    rec: RecordingData,
    athlete_metrics: settings.AthleteMetrics | None = None,
) -> tuple[str, Any] | None:
    """Build a heart rate time-series chart.

    Renders a line chart of heart rate (bpm) over activity duration.

    Parameters
    ----------
    rec : RecordingData
        Pre-parsed recording data loaded via load_parquet().
    athlete_metrics : settings.AthleteMetrics | None
        Resolved athlete metrics with populated e_z* zone boundaries.

    Returns
    -------
    tuple[str, Any] | None
        ``(script, div)`` Bokeh embed components, or ``None`` when the
        recording has no usable HR samples.
    """
    if not rec.timestamps or not rec.hr_values:
        return None

    hr_clean = [h if h is not None else float("nan") for h in rec.hr_values]
    if not any(h is not None and h > 0 for h in rec.hr_values):
        return None

    hr_vals = [v for v in rec.hr_values if v is not None and v > 0]
    hr_max = max(hr_vals) if hr_vals else 150
    # ensure hr_max is at least as high as Z5 high if metrics are available
    if athlete_metrics and athlete_metrics.e_z5_high > hr_max:
        hr_max = athlete_metrics.e_z5_high
    hr_max = hr_max * 1.1

    source = ColumnDataSource(
        data=dict(
            ts=rec.timestamps,
            hr=hr_clean,
        )
    )

    fig = bokeh_plt.figure(
        x_axis_type="datetime",
        height=300,
        sizing_mode="stretch_width",
        tools="save,pan,wheel_zoom,box_zoom,reset",
        toolbar_location="above",
        title="Heart Rate Over Time",
    )
    fig.toolbar.logo = None

    # draw HR zones as background rectangles
    if athlete_metrics:
        zone_boundaries = [
            (athlete_metrics.e_z1_low, athlete_metrics.e_z1_high),
            (athlete_metrics.e_z2_low, athlete_metrics.e_z2_high),
            (athlete_metrics.e_z3_low, athlete_metrics.e_z3_high),
            (athlete_metrics.e_z4_low, athlete_metrics.e_z4_high),
            (athlete_metrics.e_z5_low, athlete_metrics.e_z5_high),
        ]
        for i, (low, high) in enumerate(zone_boundaries):
            if high > 0:
                fig.add_layout(
                    bokeh_models.BoxAnnotation(
                        bottom=low,
                        top=high,
                        fill_alpha=0.1,
                        fill_color=HR_ZONE_COLORS[i],
                        level="underlay",
                    )
                )

    fig.line(
        "ts",
        "hr",
        source=source,
        line_width=2,
        color="#e03131",
        legend_label="Heart Rate (bpm)",
    )

    hover = bokeh_models.HoverTool(
        tooltips=[
            ("Time", "@ts{%H:%M:%S}"),
            ("HR", "@hr{0} bpm"),
        ],
        formatters={"@ts": "datetime"},
        mode="vline",
    )
    fig.add_tools(hover)

    fig.xaxis.axis_label = "Time"
    fig.yaxis.axis_label = "Heart Rate (bpm)"
    fig.y_range = bokeh_models.Range1d(start=0, end=hr_max)
    fig.xgrid.grid_line_color = "#e9ecef"
    fig.ygrid.grid_line_color = "#e9ecef"
    fig.outline_line_color = None
    fig.legend.location = "top_right"

    return bokeh_embed.components(fig)


def _build_speed_cadence_ts_chart(rec: RecordingData) -> tuple[str, Any] | None:
    """Build a speed and cadence time-series chart.

    Renders a dual-axis line chart of speed (km/h) and cadence (rpm) over activity
    duration. Speed on left axis, cadence on right axis.

    Parameters
    ----------
    rec : RecordingData
        Pre-parsed recording data loaded via load_parquet().

    Returns
    -------
    tuple[str, Any] | None
        ``(script, div)`` Bokeh embed components, or ``None`` when the
        recording has neither speed nor cadence data.
    """
    if not rec.timestamps:
        return None

    has_speed = rec.has_speed and any(v is not None for v in rec.speed_values)
    has_cadence = rec.has_cadence and any(v is not None for v in rec.cadence_values)

    if not has_speed and not has_cadence:
        return None

    def _nan(v):
        return float("nan") if v is None else v

    speed_clean = [_nan(v) for v in rec.speed_values]
    cadence_clean = [_nan(v) for v in rec.cadence_values]

    source = ColumnDataSource(
        data=dict(
            ts=rec.timestamps,
            speed=speed_clean,
            cadence=cadence_clean,
        )
    )

    fig = bokeh_plt.figure(
        x_axis_type="datetime",
        height=300,
        sizing_mode="stretch_width",
        tools="save,pan,wheel_zoom,box_zoom,reset",
        toolbar_location="above",
        title="Speed and Cadence Over Time",
    )
    fig.toolbar.logo = None

    # plot speed on primary (left) y-axis
    if has_speed:
        speed_vals = [v for v in rec.speed_values if v is not None]
        speed_max = max(speed_vals) if speed_vals else 50
        speed_max = speed_max * 1.15

        fig.line(
            "ts",
            "speed",
            source=source,
            line_width=2,
            color="#1971c2",
            legend_label="Speed (km/h)",
        )
        fig.y_range = bokeh_models.Range1d(start=0, end=speed_max)
        fig.yaxis.axis_label = "Speed (km/h)"

    # plot cadence on secondary (right) y-axis
    if has_cadence:
        cadence_vals = [v for v in rec.cadence_values if v is not None]
        cadence_max = max(cadence_vals) if cadence_vals else 120
        cadence_max = cadence_max * 1.2

        fig.extra_y_ranges["cadence"] = bokeh_models.Range1d(start=0, end=cadence_max)
        fig.add_layout(
            bokeh_models.LinearAxis(y_range_name="cadence", axis_label="Cadence (rpm)"),
            "right",
        )

        fig.line(
            "ts",
            "cadence",
            source=source,
            line_width=2,
            color="#f08c00",
            y_range_name="cadence",
            legend_label="Cadence (rpm)",
        )

    tooltips = [("Time", "@ts{%H:%M:%S}")]
    if has_speed:
        tooltips.append(("Speed", "@speed{0.0} km/h"))
    if has_cadence:
        tooltips.append(("Cadence", "@cadence{0} rpm"))

    hover = bokeh_models.HoverTool(
        tooltips=tooltips,
        formatters={"@ts": "datetime"},
        mode="vline",
    )
    fig.add_tools(hover)

    fig.xaxis.axis_label = "Time"
    fig.xgrid.grid_line_color = "#e9ecef"
    fig.ygrid.grid_line_color = "#e9ecef"
    fig.outline_line_color = None
    fig.legend.location = "top_right"

    return bokeh_embed.components(fig)


def activity_fit_charts(
    recording: RecordingData,
    athlete_metrics: settings.AthleteMetrics | None = None,
) -> tuple[
    tuple[str, Any] | None,
    tuple[str, Any] | None,
    tuple[str, Any] | None,
    tuple[str, Any] | None,
    tuple[str, Any] | None,
    tuple[str, Any] | None,
    tuple[str, Any] | None,
    tuple[str, Any] | None,
    tuple[str, Any] | None,
]:
    """Build all recording-based charts from a RecordingData instance.

    Parameters
    ----------
    recording : RecordingData
        Pre-parsed recording data loaded via load_parquet().
    athlete_metrics : settings.AthleteMetrics | None
        Resolved athlete metrics with populated e_z* zone boundaries. Required
        for the HR zones and power zones charts; when ``None`` those results
        are ``None``.

    Returns
    -------
    tuple[tuple | None, ...] (9 elements)
        ``(overlay, ridge, hr_zones, cadence_hist, power_zones, power_curve,
           power_ts, hr_ts, speed_cadence_ts)``
        — each element is either ``(script, div)`` or ``None`` when the
        recording has no usable samples or the required data is unavailable.
    """
    if not recording.timestamps:
        return None, None, None, None, None, None, None, None, None

    overlay = _build_overlay_chart(recording, athlete_metrics=athlete_metrics)
    ridge = _build_ridge_chart(recording, athlete_metrics=athlete_metrics)

    hr_zones = None
    power_zones = None
    if athlete_metrics is not None:
        hr_zones = _build_hr_zones_chart(recording, athlete_metrics)
        power_zones = _build_power_zones_chart(recording, athlete_metrics)

    cadence_hist = _build_cadence_histogram_chart(recording)
    power_curve = _build_power_curve_chart(recording)
    power_ts = _build_power_ts_chart(recording)
    hr_ts = _build_hr_ts_chart(recording, athlete_metrics=athlete_metrics)
    speed_cadence_ts = _build_speed_cadence_ts_chart(recording)

    return (
        overlay,
        ridge,
        hr_zones,
        cadence_hist,
        power_zones,
        power_curve,
        power_ts,
        hr_ts,
        speed_cadence_ts,
    )


def demo_time_series():
    import numpy as np
    from bokeh.layouts import column
    from bokeh.models import ColumnDataSource
    from bokeh.models import RangeTool
    from bokeh.plotting import figure
    from bokeh.sampledata.stocks import AAPL

    dates = np.array(AAPL["date"], dtype=np.datetime64)
    source = ColumnDataSource(data=dict(date=dates, close=AAPL["adj_close"]))

    p = figure(
        height=300,
        width=800,
        tools="xpan",
        toolbar_location="below",
        x_axis_type="datetime",
        x_axis_location="above",
        background_fill_color="#efefef",
        x_range=(dates[1500], dates[2500]),
    )

    p.line("date", "close", source=source)
    p.yaxis.axis_label = "Price"

    select = figure(
        title=(
            "Drag the middle and edges of the selection box to change the range above"
        ),
        height=130,
        width=800,
        y_range=p.y_range,
        x_axis_type="datetime",
        y_axis_type=None,
        tools="",
        toolbar_location="below",
        background_fill_color="#efefef",
    )

    range_tool = RangeTool(x_range=p.x_range, start_gesture="pan")
    range_tool.overlay.fill_color = "navy"
    range_tool.overlay.fill_alpha = 0.2

    select.line("date", "close", source=source)
    select.ygrid.grid_line_color = None
    select.add_tools(range_tool)

    # show(column(p, select))
    script, div = bokeh_embed.components(column(p, select))

    return script, div


def fig_grid_2_html(fig_or_grid) -> tuple[str, Any]:
    script, div = bokeh_embed.components(fig_or_grid)

    return script, div


def last_vs_this_year(
    aspect: commons.StatsAspect, user_id: str, ds, is_mobile_view: bool = False
) -> tuple[str, Any]:
    #
    #  data
    #
    activity_types = ds.list_activity_types(user_id=user_id)

    this_year = datetime.datetime.now().year
    this_as = ds.list_activities(
        user_id=user_id,
        dataset_name=ds.profile(user_id).dataset_name,
        filter_year=this_year,
    )
    # get totals for the aspect
    this_stats = stats.ActivitiesStats(this_as)
    this_data = this_stats.get_year_totals(aspect=aspect, activity_types=activity_types)

    last_year = this_year - 1
    last_as = ds.list_activities(
        user_id=user_id,
        dataset_name=ds.profile(user_id).dataset_name,
        filter_year=last_year,
    )
    last_stats = stats.ActivitiesStats(last_as)
    last_data = last_stats.get_year_totals(aspect=aspect, activity_types=activity_types)

    llast_year = last_year - 1
    llast_as = ds.list_activities(
        user_id=user_id,
        dataset_name=ds.profile(user_id).dataset_name,
        filter_year=llast_year,
    )
    llast_stats = stats.ActivitiesStats(llast_as)
    llast_data = llast_stats.get_year_totals(
        aspect=aspect, activity_types=activity_types
    )

    #
    #  chart
    #

    fig = bokeh_plt.figure(
        title=f"This year vs. last year {aspect.name.lower()}",
        x_axis_label="week",
        toolbar_location="below" if not is_mobile_view else None,
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550,
    )
    # autofit width
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    # set custom x-axis labels
    fig.xaxis.ticker = list(range(1, 12))
    fig.xaxis.major_label_overrides = cals.MONTH_INDEX_2_STR

    _apply_y_axis_formatter(fig, aspect)

    # last last
    x = list(llast_data.keys())
    y = list(llast_data.values())
    if commons.StatsAspect.DISTANCE == aspect:
        y = [v / 1000.0 for v in y]
    color = "gray"
    llast_w = _create_line_with_data_source(
        fig, x, y, aspect, color, alpha=0.5, legend_label="last last year"
    )
    fig.scatter(x, y, color=color)

    # last
    y = list(last_data.values())
    if commons.StatsAspect.DISTANCE == aspect:
        y = [v / 1000.0 for v in y]
    color = "black"
    last_w = _create_line_with_data_source(
        fig, x, y, aspect, color, alpha=0.5, legend_label="last year"
    )
    fig.scatter(x, y, color=color)

    # this
    y = list(this_data.values())
    if commons.StatsAspect.DISTANCE == aspect:
        y = [v / 1000.0 for v in y]
    color = "green"
    this_w = _create_line_with_data_source(
        fig, x, y, aspect, color, line_width=2, legend_label="this year"
    )
    fig.scatter(x, y, color=color)

    if is_mobile_view:
        fig.legend.visible = False
    else:
        fig.legend.location = "top_left"

    _add_hover_tool_with_tooltips(fig, aspect, [llast_w, last_w, this_w])

    script, div = bokeh_embed.components(fig)

    return script, div


def last_vs_this_month(
    aspect: commons.StatsAspect, user_id: str, ds, is_mobile_view: bool = False
) -> tuple[str, Any] | tuple[None, None]:
    #
    #  data
    #
    now = datetime.datetime.now()

    activity_types = ds.list_activity_types(user_id=user_id)

    this_year = now.year
    this_month = now.month
    this_as = ds.list_activities(
        user_id=user_id,
        dataset_name=ds.profile(user_id).dataset_name,
        filter_year=this_year,
        filter_month=this_month,
    )
    # get monthly totals for the aspect
    this_stats = stats.ActivitiesStats(this_as)
    this_data = this_stats.get_month_totals(
        aspect=aspect, activity_types=activity_types
    )

    last_year, last_month = cals.get_last_month()
    last_as = ds.list_activities(
        user_id=user_id,
        dataset_name=ds.profile(user_id).dataset_name,
        filter_year=last_year,
        filter_month=last_month,
    )
    # get monthly totals for the aspect
    last_stats = stats.ActivitiesStats(last_as)
    last_data = last_stats.get_month_totals(
        aspect=aspect, activity_types=activity_types
    )

    llast_year, llast_month = cals.get_last_month(year=last_year, month=last_month)
    llast_as = ds.list_activities(
        user_id=user_id,
        dataset_name=ds.profile(user_id).dataset_name,
        filter_year=llast_year,
        filter_month=llast_month,
    )
    # get monthly totals for the aspect
    llast_stats = stats.ActivitiesStats(llast_as)
    llast_data = llast_stats.get_month_totals(
        aspect=aspect, activity_types=activity_types
    )

    # hide chart when all three months have no data
    if (
        not any(this_data.values())
        and not any(last_data.values())
        and not any(llast_data.values())
    ):
        return None, None

    #
    #  chart
    #

    fig = bokeh_plt.figure(
        title=f"This month vs. last month {aspect.name.lower()}",
        x_axis_label="week",
        toolbar_location="below",
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550,
    )
    # autofit width
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    _apply_y_axis_formatter(fig, aspect)

    # last last
    x = list(llast_data.keys())
    y = list(llast_data.values())
    if commons.StatsAspect.DISTANCE == aspect:
        y = [v / 1000.0 for v in y]
    color = "gray"
    llast_w = _create_line_with_data_source(
        fig, x, y, aspect, color, alpha=0.5, legend_label="last last month"
    )
    fig.scatter(x, y, color=color)

    # last
    y = list(last_data.values())
    if commons.StatsAspect.DISTANCE == aspect:
        y = [v / 1000.0 for v in y]
    color = "black"
    last_w = _create_line_with_data_source(
        fig, x, y, aspect, color, alpha=0.5, legend_label="last month"
    )
    fig.scatter(x, y, color=color)

    # this
    y = list(this_data.values())
    if commons.StatsAspect.DISTANCE == aspect:
        y = [v / 1000.0 for v in y]
    color = "green"
    this_w = _create_line_with_data_source(
        fig, x, y, aspect, color, line_width=2, legend_label="this month"
    )
    fig.scatter(x, y, color=color)

    if is_mobile_view:
        fig.legend.visible = False
    else:
        fig.legend.location = "top_left"

    _add_hover_tool_with_tooltips(fig, aspect, [llast_w, last_w, this_w])

    script, div = bokeh_embed.components(fig)

    return script, div


def last_vs_this_week(
    heatmap: views.CalendarHeatmap,
    aspect: commons.StatsAspect,
    is_mobile_view: bool = False,
) -> tuple[str, Any]:
    data = heatmap.vs_week_stats(aspect=aspect)

    fig = bokeh_plt.figure(
        title=f"This week vs. last week {aspect.name.lower()}",
        x_axis_label="week",
        toolbar_location="below" if not is_mobile_view else None,
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550,
    )
    # autofit width
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    # set custom x-axis labels
    fig.xaxis.ticker = list(range(1, 8))
    fig.xaxis.major_label_overrides = {
        1: "Mon",
        2: "Tue",
        3: "Wed",
        4: "Thu",
        5: "Fri",
        6: "Sat",
        7: "Sun",
    }

    _apply_y_axis_formatter(fig, aspect)

    # last
    x = list(range(1, 8))
    y = list(itertools.accumulate(data[0]))
    color = "gray"
    last_w = _create_line_with_data_source(
        fig, x, y, aspect, color, alpha=0.5, legend_label="last week"
    )
    fig.scatter(x, y, color=color)

    # this
    y = list(itertools.accumulate(data[1]))
    color = "green"
    this_w = _create_line_with_data_source(
        fig, x, y, aspect, color, line_width=2, legend_label="this week"
    )
    fig.scatter(x, y, color=color)

    if is_mobile_view:
        fig.legend.visible = False
    else:
        fig.legend.location = "top_left"

    _add_hover_tool_with_tooltips(fig, aspect, [last_w, this_w])

    script, div = bokeh_embed.components(fig)

    return script, div


def last_vs_this_week_homepage(
    aspect: commons.StatsAspect,
    activities: list[entities.ActivityEntity],
    activity_types: settings.UserActivityTypes,
    is_mobile_view: bool = False,
) -> tuple[str, Any] | tuple[None, None]:
    """Efficiently calculate this week vs. past weeks (cumulative) from activities.

    This function shows 3 weeks: this week, last week, and last last week.
    It is designed to be fast and not use CalendarHeatmap.
    """
    today = datetime.date.today()
    # this week Mon-Sun
    this_mon = today - datetime.timedelta(days=today.weekday())

    def get_week_totals(start_date: datetime.date):
        end_date = start_date + datetime.timedelta(days=6)
        # map: weekday (0-6) -> value
        totals = {i: 0.0 for i in range(7)}
        for a in activities:
            a_date = datetime.date(a.when_year, a.when_month, a.when_day)
            if start_date <= a_date <= end_date:
                if activity_types.is_sport(a.activity_type_key):
                    val = 0.0
                    if aspect == commons.StatsAspect.DISTANCE:
                        val = a.distance / 1000.0
                    elif aspect == commons.StatsAspect.DURATION:
                        val = a.duration_seconds
                    elif aspect == commons.StatsAspect.KGS:
                        val = a.exercise_kgs
                    else:
                        val = 1.0  # count
                    totals[a_date.weekday()] += val

        # return accumulated values for Mon-Sun
        return list(itertools.accumulate([totals[i] for i in range(7)]))

    this_data = get_week_totals(this_mon)
    last_mon = this_mon - datetime.timedelta(days=7)
    last_data = get_week_totals(last_mon)
    llast_mon = last_mon - datetime.timedelta(days=7)
    llast_data = get_week_totals(llast_mon)

    # hide chart when all three weeks have no data
    if not any(this_data) and not any(last_data) and not any(llast_data):
        return None, None

    #
    #  chart
    #
    fig = bokeh_plt.figure(
        title=f"This week vs. past weeks {aspect.name.lower()}",
        x_axis_label="week",
        toolbar_location="below" if not is_mobile_view else None,
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550,
    )
    # autofit width
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    # set custom x-axis labels
    fig.xaxis.ticker = list(range(1, 8))
    fig.xaxis.major_label_overrides = {
        1: "Mon",
        2: "Tue",
        3: "Wed",
        4: "Thu",
        5: "Fri",
        6: "Sat",
        7: "Sun",
    }

    _apply_y_axis_formatter(fig, aspect)

    x = list(range(1, 8))

    # last last
    color = "lightgray"
    llast_w = _create_line_with_data_source(
        fig, x, llast_data, aspect, color, alpha=0.5, legend_label="last last week"
    )
    fig.scatter(x, llast_data, color=color)

    # last
    color = "gray"
    last_w = _create_line_with_data_source(
        fig, x, last_data, aspect, color, alpha=0.5, legend_label="last week"
    )
    fig.scatter(x, last_data, color=color)

    # this
    color = "green"
    this_w = _create_line_with_data_source(
        fig, x, this_data, aspect, color, line_width=2, legend_label="this week"
    )
    fig.scatter(x, this_data, color=color)

    if is_mobile_view:
        fig.legend.visible = False
    else:
        fig.legend.location = "top_left"

    _add_hover_tool_with_tooltips(fig, aspect, [llast_w, last_w, this_w])

    script, div = bokeh_embed.components(fig)

    return script, div


def radar_plot(user_id: str, ds, is_mobile_view: bool = False) -> tuple[str, Any]:
    """Radar plot comparing 3 recent years across 3 aspects (distance, duration, kgs).

    Vertices represent months (12 total).
    Jan is at top (90 deg), Feb is 60 deg, etc. (clockwise).

    Data is normalized per aspect (max across all 3 years = 1.0).

    """
    now = datetime.datetime.now()
    this_year = now.year
    years = [this_year, this_year - 1, this_year - 2]
    aspects = [
        commons.StatsAspect.DISTANCE,
        commons.StatsAspect.DURATION,
        commons.StatsAspect.KGS,
    ]

    # colors
    # distance: blue
    # duration: green
    # kgs: orange
    aspect_colors = {
        commons.StatsAspect.DISTANCE: "#206bc4",  # blue
        commons.StatsAspect.DURATION: "#2fb344",  # green
        commons.StatsAspect.KGS: "#f59f00",  # orange
    }

    # alphas for years: this=0.5, last=0.3, last-last=0.1
    year_alphas = {
        this_year: 0.5,
        this_year - 1: 0.3,
        this_year - 2: 0.1,
    }

    # get data
    activity_types = ds.list_activity_types(user_id=user_id)
    dataset_name = ds.profile(user_id).dataset_name

    all_data = {}  # (aspect, year) -> {month: value}
    aspect_max = {aspect: 0.01 for aspect in aspects}  # avoid division by zero
    has_data = False

    for year in years:
        activities = ds.list_activities(
            user_id=user_id,
            dataset_name=dataset_name,
            filter_year=year,
        )
        # get non-cumulative totals for the year
        stats_obj = stats.ActivitiesStats(activities)
        for aspect in aspects:
            year_totals = stats_obj.get_year_totals(
                aspect=aspect, activity_types=activity_types, cumulative=False
            )
            # convert DISTANCE to km if needed (StatsAspect.DISTANCE returns meters)
            if aspect == commons.StatsAspect.DISTANCE:
                year_totals = {m: v / 1000.0 for m, v in year_totals.items()}
            # convert DURATION to hours
            elif aspect == commons.StatsAspect.DURATION:
                year_totals = {m: v / 3600.0 for m, v in year_totals.items()}

            all_data[(aspect, year)] = year_totals
            # update max for normalization
            for val in year_totals.values():
                if val > 0:
                    has_data = True
                if val > aspect_max[aspect]:
                    aspect_max[aspect] = val

    if not has_data:
        return None, None

    # angles: Jan at 90 deg, February at 60 deg... (clockwise)
    # math.pi/2 is 90 deg (Jan)
    # -2*math.pi/12 is -30 deg per month
    month_angles = [
        math.pi / 2.0 - (m - 1) * (2.0 * math.pi / 12.0) for m in range(1, 13)
    ]

    fig = bokeh_plt.figure(
        title="Recent Years Comparison",
        x_axis_type=None,
        y_axis_type=None,
        toolbar_location=None,
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550 if not is_mobile_view else 400,
        match_aspect=True,
    )
    # autofit width
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None
    fig.x_range.range_padding = 0.2
    fig.y_range.range_padding = 0.2
    fig.grid.grid_line_color = None
    fig.outline_line_color = None

    # add circular grid lines
    for radius in [0.2, 0.4, 0.6, 0.8, 1.0]:
        fig.circle(0, 0, radius=radius, fill_color=None, line_color="silver")

    # add radial lines and month labels
    for m in range(1, 13):
        angle = month_angles[m - 1]
        x = [0, math.cos(angle)]
        y = [0, math.sin(angle)]
        fig.line(x, y, color="silver", line_dash="dashed")
        # labels
        label_radius = 1.15
        fig.text(
            x=[label_radius * math.cos(angle)],
            y=[label_radius * math.sin(angle)],
            text=[cals.MONTH_INDEX_2_STR[m]],
            text_align="center",
            text_baseline="middle",
        )

    # plot polygons
    hover_renderers = []
    for aspect in aspects:
        color = aspect_colors[aspect]
        for year in years:
            alpha = year_alphas[year]
            year_totals = all_data[(aspect, year)]

            # normalize and convert to Cartesian
            x_vals = []
            y_vals = []
            hover_values = []
            for m in range(1, 13):
                val = year_totals.get(m, 0.0)
                norm_val = val / aspect_max[aspect]
                angle = month_angles[m - 1]
                x_vals.append(norm_val * math.cos(angle))
                y_vals.append(norm_val * math.sin(angle))

                # prepare human-friendly value for tooltip
                if aspect == commons.StatsAspect.DISTANCE:
                    hover_val = f"{val:.1f} km"
                elif aspect == commons.StatsAspect.DURATION:
                    hover_val = cals.seconds_to_str_time(int(val * 3600))
                else:  # kgs
                    hover_val = f"{int(val)} kg"
                hover_values.append(hover_val)

            # close the polygon for the patch
            x_patch = x_vals + [x_vals[0]]
            y_patch = y_vals + [y_vals[0]]

            fig.patch(
                x_patch,
                y_patch,
                color=color,
                alpha=alpha,
                line_color=color,
                line_width=2 if year == this_year else 1,
                legend_label=f"{aspect.name.lower()} {year}",
            )

            # markers and tooltips: only for non-zero values
            x_markers = []
            y_markers = []
            hover_values_filtered = []
            months_filtered = []
            for i in range(len(x_vals)):
                # we use a small threshold to avoid floating point issues if any
                val = year_totals.get(i + 1, 0.0)
                if val > 0.001:
                    x_markers.append(x_vals[i])
                    y_markers.append(y_vals[i])
                    hover_values_filtered.append(hover_values[i])
                    months_filtered.append(cals.MONTH_INDEX_2_STR[i + 1])

            if x_markers:
                marker_source = ColumnDataSource(
                    {
                        "x": x_markers,
                        "y": y_markers,
                        "val": hover_values_filtered,
                        "year": [str(year)] * len(x_markers),
                        "aspect": [aspect.name.lower()] * len(x_markers),
                        "month": months_filtered,
                    }
                )
                # markers
                r = fig.scatter(
                    "x",
                    "y",
                    source=marker_source,
                    color=color,
                    size=6,
                    alpha=alpha + 0.4 if alpha + 0.4 <= 1.0 else 1.0,
                )
                hover_renderers.append(r)

    fig.legend.location = "top_left"
    fig.legend.click_policy = "hide"
    fig.legend.label_text_font_size = "8pt"
    if is_mobile_view:
        fig.legend.visible = False

    # hover tool - only for markers
    hover = bokeh_models.HoverTool(
        renderers=hover_renderers,
        tooltips=[
            ("Year", "@year"),
            ("Aspect", "@aspect"),
            ("Month", "@month"),
            ("Value", "@val"),
        ],
    )
    # hit_dilation: expand the hit area around markers for better user experience
    for r in hover_renderers:
        r.glyph.hit_dilation = 5
    fig.add_tools(hover)

    script, div = bokeh_embed.components(fig)

    return script, div


def home_grid(
    ds_stats: stats.UserDatasetStats, is_mobile_view: bool = False
) -> tuple[str, Any]:
    x = list(range(11))
    y1 = [10 - i for i in x]
    y2 = [abs(i - 5) for i in x]

    s1 = total_km_per_year(
        ds_stats=ds_stats,
        activity_types=None,  # demo function, no activity types available
        is_mobile_view=is_mobile_view,
    )

    s2 = bokeh_plt.figure(
        title="",
        x_axis_label="Week",
        y_axis_label="Last year vs. this year (weeks)",
        background_fill_color="#fafafa",
    )
    s2.triangle(x, y1, size=12, alpha=0.8, color="#c02942")

    s3 = bokeh_plt.figure(
        title="",
        x_axis_label="Day",
        y_axis_label="Last week vs. this week (days)",
        background_fill_color="#fafafa",
    )
    s3.square(x, y2, size=12, alpha=0.8, color="#d95b43")

    s4 = bokeh_plt.figure(
        title="",
        x_axis_label="Day",
        y_axis_label="Last month vs. this month (days)",
        background_fill_color="#fafafa",
    )
    s4.square(x, y2, size=12, alpha=0.8, color="#d95b43")

    # make a grid
    grid = bokeh_layouts.gridplot([[s3, s4], [s1, s2]], width=600, height=400)

    script, div = bokeh_embed.components(grid)

    return script, div


def year_kms_per_week(
    x: list, y: list, accumulate: bool = False, is_mobile_view: bool = False
) -> tuple[str, Any]:
    fig = bokeh_plt.figure(
        title="Year km per week",
        x_axis_label="week",
        y_axis_label="km",
        toolbar_location="below" if not is_mobile_view else None,
    )
    # autofit width
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    if accumulate:
        y = list(itertools.accumulate(y))

    color = "green"
    this_w = fig.line(
        line_width=2,
        color=color,
        legend_label="this year",
        source=ColumnDataSource({"x": x, "y": y}),
    )
    fig.scatter(x, y, color=color)

    if is_mobile_view:
        fig.legend.visible = False
    else:
        fig.legend.location = "top_left"

    fig.add_tools(
        bokeh_models.HoverTool(
            tooltips="@y{int}",  # force int - avoid sci notation
            renderers=[this_w],
            mode="vline",
        )
    )

    script, div = bokeh_embed.components(fig)

    return script, div


def _attribute_per_week(
    activities: list[entities.ActivityEntity],
    attribute_name: str,
    title: str,
    unit: str,
    chart_type: ChartType,
    label: str,
    is_mobile_view: bool = False,
) -> Any:
    """Create chart with attribute per week - for every week between min and max.

    Parameters
    ----------
    activities : list[entities.ActivityEntity]
      List of activities sorted by when date.
    attribute_name : str
      Name of the attribute to extract from activities.
    title : str
      Title of the chart.
    unit : str
      Unit of the attribute (e.g., kg, BPM).
    chart_type : ChartType
      Chart type for formatting.
    label : str
      Label for the tooltip.
    is_mobile_view : bool
        True if the chart is rendered for mobile view.

    """
    x = []
    y = []
    monday_dates = []

    if activities and len(activities) > 1:
        # map: year -> week -> value (0.0 default)
        data = {}

        activities.reverse()

        # initialize data
        min_year = activities[0].when_year
        max_year = activities[-1].when_year
        meta = {year: None for year in range(min_year, max_year + 1)}
        for year in meta:
            data[year] = {week: 0.0 for week in range(1, 54)}

        # index data by year and week
        for a in activities:
            year = a.when_year
            week = datetime.date(year, a.when_month, a.when_day).isocalendar()[1]
            value = getattr(a, attribute_name)
            if value:
                current = data[year][week]
                # min value for both weight and resting HR
                if current == 0.0 or value < current:
                    data[year][week] = value

        for year in meta:
            for week in data[year]:
                x.append(year + week / 100.0)
                y.append(data[year][week])
                # calculate Monday date for this week
                monday_year, monday_month, monday_day = (
                    cals.get_same_day_in_another_year(
                        week_number=week, week_day=0, target_year=year
                    )
                )
                monday_dates.append(f"{monday_year}/{monday_month}/{monday_day}")

        # crop 0.0 values front/end
        prefix_0s = 0
        suffix_0s = 0
        # count 0s at the beginning of y list
        for i in range(len(y)):
            if y[i] == 0.0:
                prefix_0s += 1
            else:
                break
        # count 0s at the end of y list
        for i in range(len(y) - 1, -1, -1):
            if y[i] == 0.0:
                suffix_0s += 1
            else:
                break
        # apply cropping only if there are leading/trailing zeros
        if prefix_0s > 0 or suffix_0s > 0:
            end_index = len(x) - suffix_0s if suffix_0s > 0 else len(x)
            x = x[prefix_0s:end_index]
            y = y[prefix_0s:end_index]
            monday_dates = monday_dates[prefix_0s:end_index]

        # floating average for 0 values
        new_y = []
        for e, yy in enumerate(y):
            if yy == 0.0:
                if e == 0:
                    new_y.append(y[e + 1])
                elif e == len(y) - 1:
                    new_y.append(y[e - 1])
                else:
                    v = (
                        (new_y[e - 1] + y[e + 1]) / 2.0
                        if y[e + 1] != 0.0
                        else new_y[e - 1]
                    )
                    new_y.append(v)
            else:
                new_y.append(yy)
        y = new_y

    fig = bokeh_plt.figure(
        title=title,
        x_axis_label="week",
        background_fill_color="#fafafa",
        toolbar_location="below" if not is_mobile_view else None,
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550,
    )
    # autofit width
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    # add unit unit to y-axis
    _apply_y_axis_formatter_for_chart_type(fig, chart_type)

    # set custom x-axis labels
    x_tickers = [i for i in range(len(x))]
    fig.xaxis.ticker = x_tickers
    # map: value(int) -> label(str)
    x_labels = {}
    for e, x_value in enumerate(x):
        x_labels[e] = f"{int(x_value)}w{int((x_value - int(x_value)) * 100.0) + 1}"
    all_x_labels = x_labels.copy()
    # show only 15 labels so they do NOT overlap
    sparsity = 5.0 if is_mobile_view else 15.0
    if len(x_labels) > sparsity:  # 2 years = 2*54 weeks
        show_every = int(len(x_labels) / sparsity)
        for e in range(len(x_labels)):
            if e % show_every != 0:
                x_labels[e] = ""
    fig.xaxis.major_label_overrides = x_labels

    color = "black"
    source = ColumnDataSource(
        {
            "x": x_tickers,
            "y": y,
            "label": [all_x_labels[label] for label in all_x_labels],
            "monday_date": monday_dates,
        }
    )
    lr = fig.line(
        color=color,
        line_cap="round",
        line_dash="solid",
        line_width=3,
        source=source,
        legend_label=label,
    )
    if not is_mobile_view:
        fig.scatter(x_tickers, y, color=color)
    hover_renderers = [lr]

    # add average and current lines
    avg_value = None
    current_value = None
    if y:
        non_zero_values = [val for val in y if val > 0]
        if non_zero_values:
            avg_value = sum(non_zero_values) / len(non_zero_values)
            current_value = non_zero_values[-1]

            x_min = x_tickers[0]
            x_max = x_tickers[-1]

            fig.line(
                [x_min, x_max],
                [avg_value, avg_value],
                line_color="red",
                line_dash="dashed",
                line_width=2,
                line_alpha=0.7,
                legend_label="average",
            )

            fig.line(
                [x_min, x_max],
                [current_value, current_value],
                line_color="green",
                line_dash="dashed",
                line_width=2,
                line_alpha=0.8,
                legend_label="current",
            )

    fig.legend.location = "top_left"
    fig.legend.click_policy = "hide"

    # add tooltip with average and current
    tooltip_items = [
        (label, f"@y{{0.f}} {unit}"),
        ("when", "@monday_date"),
    ]
    if avg_value is not None:
        tooltip_items.append(("average", f"{avg_value:.1f} {unit}"))
    if current_value is not None:
        tooltip_items.append(("current", f"{current_value:.1f} {unit}"))

    fig.add_tools(
        bokeh_models.HoverTool(
            # tooltip: force int to avoid scientific notation
            tooltips=tooltip_items,
            renderers=hover_renderers,
            mode="vline",  # vline hline mouse
        )
    )

    if is_mobile_view or len(x_tickers) < 20:
        return fig

    # default zoomed range: last 52 weeks (if possible)
    start_index = max(0, len(x_tickers) - 52 * 2)
    end_index = len(x_tickers) - 1
    # set the initial range of the main plot
    fig.x_range.start = start_index
    fig.x_range.end = end_index

    # add range tool for desktop view
    select = bokeh_plt.figure(
        title=(
            "Drag the middle and edges of the selection box to change the range above"
        ),
        height=130,
        width=VIEW_WIDTH_DEFAULT,
        y_range=fig.y_range,
        x_axis_type=None,
        y_axis_type=None,
        tools="",
        toolbar_location=None,
        background_fill_color="#efefef",
    )
    # autofit width
    select.sizing_mode = "scale_width"

    range_tool = bokeh_models.RangeTool(x_range=fig.x_range)
    range_tool.overlay.fill_color = "navy"
    range_tool.overlay.fill_alpha = 0.2

    # draw the same data on select plot
    select.line("x", "y", source=source, color=color, line_width=1)
    select.ygrid.grid_line_color = None
    select.add_tools(range_tool)

    return bokeh_layouts.column(fig, select, sizing_mode="scale_width")


def weight_per_week(
    activities: list[entities.ActivityEntity],
    is_mobile_view: bool = False,
) -> Any:
    """Create chart with weight per week."""
    return _attribute_per_week(
        activities=activities,
        attribute_name="weight",
        title="Minimum weight per week (kg)",
        unit="kg",
        chart_type=ChartType.WEIGHT,
        label="weight",
        is_mobile_view=is_mobile_view,
    )


def resting_hr_per_week(
    activities: list[entities.ActivityEntity],
    is_mobile_view: bool = False,
) -> Any:
    """Create chart with Resting HR per week."""
    return _attribute_per_week(
        activities=activities,
        attribute_name="min_hr",
        title="Minimum Resting HR per week (BPM)",
        unit="BPM",
        chart_type=ChartType.RESTING_HR,
        label="Resting HR",
        is_mobile_view=is_mobile_view,
    )


def total_km_per_year(
    ds_stats: stats.UserDatasetStats,
    activity_types: settings.UserActivityTypes = None,
    is_mobile_view: bool = False,
) -> Any:
    """Total km per year chart:

    x: year
    y: total km per year

    Parameters
    ----------
    ds_stats : stats.UserDatasetStats
        Dataset statistics
    activity_types : settings.UserActivityTypes
        Activity types for human-friendly names
    is_mobile_view : bool
        Whether to optimize for mobile view

    """
    colors = itertools.cycle(bokeh_palette)

    fig = bokeh_plt.figure(
        title="Total km per year",
        x_axis_label="year",
        y_axis_label="km" if not is_mobile_view else "",
        background_fill_color="#fafafa",
        toolbar_location="below" if not is_mobile_view else None,
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550,
    )
    # autofit width
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    # remove 0 years from the left x-axis side - years without any activities
    years = list(ds_stats.year.keys())
    years.sort()
    active_years = []
    skip_non_active = True
    for y in years:
        app_logger.debug(f"Year: {y} - {ds_stats.year[y].ukm}")
        if skip_non_active and ds_stats.year[y].ukm == 0:
            continue
        else:
            skip_non_active = False
            active_years.append(y)

    # x: year
    # y: total km per year
    # line: per-activity_type_key
    fig_data = {}
    for year in active_years:
        for s in ds_stats.total_m_per_activity_type:
            if s not in fig_data:
                fig_data[s] = {"x": [], "y": []}
            fig_data[s]["x"].append(year)
            fig_data[s]["y"].append(
                ds_stats.year[year].total_km_per_activity_type.get(s, 0)
            )

        s = "ukm"
        if s not in fig_data:
            fig_data[s] = {"x": [], "y": []}
        fig_data[s]["x"].append(year)
        fig_data[s]["y"].append(ds_stats.year[year].ukm)

    hover_renderers = []

    for s in fig_data:
        x = fig_data[s]["x"]
        y = fig_data[s]["y"]
        if y and not all(v == 0 for v in y):
            # TODO use MyTraL activity 2 color map
            color = "black" if s == "ukm" else next(colors)

            # use human-friendly activity_type_key name for legend
            if s == "ukm":
                display_name = "UKM"
            elif activity_types:
                display_name = activity_types.name(s)
            else:
                display_name = s

            lr = fig.line(
                legend_label=display_name,
                color=color,
                line_cap="round",
                line_dash="dotted" if s == "ukm" else "solid",
                line_width=3 if s == "ukm" else 2,
                source=ColumnDataSource(
                    {"x": x, "y": y, "label": [display_name for _ in x]}
                ),
            )
            fig.scatter(x, y, color=color, legend_label=display_name)
            hover_renderers.append(lr)

    fig.add_tools(
        bokeh_models.HoverTool(
            # tooltip: force int to avoid scientific notation
            tooltips="@label: @y{int} km in @x",
            renderers=hover_renderers,
            mode="vline",  # vline hline mouse
        )
    )

    # only configure legend if there are renderers with legends
    if hover_renderers:
        if is_mobile_view:
            fig.legend.visible = False
        else:
            fig.legend.location = "top_left"

        fig.legend.click_policy = "hide"

    if is_mobile_view or len(active_years) <= 10:
        return fig

    # default zoomed range: last 10 years
    start_year = active_years[-10]
    end_year = active_years[-1]
    # set the initial range of the main plot
    fig.x_range.start = start_year - 0.5
    fig.x_range.end = end_year + 0.5

    # add range tool for desktop view
    select = bokeh_plt.figure(
        title=(
            "Drag the middle and edges of the selection box to change the range above"
        ),
        height=130,
        width=VIEW_WIDTH_DEFAULT,
        y_range=fig.y_range,
        x_axis_type=None,
        y_axis_type=None,
        tools="",
        toolbar_location=None,
        background_fill_color="#efefef",
    )
    # autofit width
    select.sizing_mode = "scale_width"

    range_tool = bokeh_models.RangeTool(x_range=fig.x_range)
    range_tool.overlay.fill_color = "navy"
    range_tool.overlay.fill_alpha = 0.2

    # draw UKM (total) line on select plot for context
    if "ukm" in fig_data:
        select.line(
            fig_data["ukm"]["x"],
            fig_data["ukm"]["y"],
            color="black",
            line_width=1,
            line_dash="dotted",
        )

    select.ygrid.grid_line_color = None
    select.add_tools(range_tool)

    return bokeh_layouts.column(fig, select, sizing_mode="scale_width")


def _weekly_totals(
    cal_heatmap: views.CalendarHeatmap,
    year: int,
    chart_type: ChartType,
    cumulative: bool = False,
    is_mobile_view: bool = False,
) -> tuple[str, Any]:
    # determine chart title based on type
    if chart_type in [ChartType.HOUR, ChartType.SUM_HOUR]:
        chart_label = "duration"
    else:
        chart_label = chart_type.value

    # TODO remove colors = itertools.cycle(bokeh_palette)
    fig = bokeh_plt.figure(
        title=(f"{'Cumulative' if cumulative else 'Total'} {chart_label} per week"),
        x_axis_label="week",
        background_fill_color="#fafafa",
        toolbar_location=None,
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550,
    )
    fig.legend.click_policy = "hide"
    # autofit width
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None
    # apply y-axis formatter based on chart type
    _apply_y_axis_formatter_for_chart_type(fig, chart_type)
    # x: week number
    # y: total meters per week
    # line: ...
    if cal_heatmap.week_stats.get(year):
        _weeks = list(cal_heatmap.week_stats[year].keys())
        min_week = min(_weeks)
        max_week = len(_weeks) + 1 if min_week else len(_weeks) + 2
        if chart_type == ChartType.WEIGHT:
            fig_data = {
                ChartType.WEIGHT.value: {
                    "x": [i for i in range(min_week, max_week)],
                    "y": [0 for _ in range(min_week, max_week)],
                },
            }
        elif chart_type in [ChartType.HOUR, ChartType.SUM_HOUR]:
            fig_data = {
                "duration": {
                    "x": [i for i in range(min_week, max_week)],
                    "y": [0 for _ in range(min_week, max_week)],
                    "strtime": ["0h00'00\"" for _ in range(min_week, max_week)],
                }
            }
        elif chart_type in [ChartType.KG, ChartType.SUM_KG]:
            fig_data = {
                ChartType.KG.value: {
                    "x": [i for i in range(min_week, max_week)],
                    "y": [0 for _ in range(min_week, max_week)],
                }
            }
        else:
            fig_data = {
                ChartType.KM.value: {
                    "x": [i for i in range(min_week, max_week)],
                    "y": [0 for _ in range(min_week, max_week)],
                }
            }

        max_weight = 0.0
        for w in cal_heatmap.week_stats[year]:
            if chart_type == ChartType.WEIGHT:
                weight = cal_heatmap.week_stats[year][w].get(
                    views.CalendarHeatmap.KEY_WEIGHT, 0.0
                )
                max_weight = max(max_weight, weight)
                fig_data[ChartType.WEIGHT.value]["y"][w - 1] = weight
            elif chart_type in [ChartType.HOUR, ChartType.SUM_HOUR]:
                seconds = cal_heatmap.week_stats[year][w][
                    views.CalendarHeatmap.KEY_SECONDS
                ]
                fig_data["duration"]["y"][w - 1] = seconds
                fig_data["duration"]["strtime"][w - 1] = cals.seconds_to_chart_time(
                    seconds
                )
            elif chart_type in [ChartType.KG, ChartType.SUM_KG]:
                kgs = cal_heatmap.week_stats[year][w][views.CalendarHeatmap.KEY_KG]
                fig_data[ChartType.KG.value]["y"][w - 1] = kgs
            else:
                meters = cal_heatmap.week_stats[year][w][views.CalendarHeatmap.KEY_M]
                fig_data[ChartType.KM.value]["y"][w - 1] = meters / 1000.0

        # cumulative values
        if cumulative:
            cumulative_value = 0.0
            data_key = (
                "duration"
                if chart_type in [ChartType.HOUR, ChartType.SUM_HOUR]
                else chart_type.value
            )
            for e, v in enumerate(fig_data[data_key]["y"]):
                cumulative_value += v
                fig_data[data_key]["y"][e] = cumulative_value
                # update strtime for duration after cumulative calculation
                if chart_type in [ChartType.HOUR, ChartType.SUM_HOUR]:
                    fig_data["duration"]["strtime"][e] = cals.seconds_to_chart_time(
                        int(cumulative_value)
                    )

        # smooth weight
        if chart_type == ChartType.WEIGHT:
            last_weight = max_weight
            for e, w in enumerate(fig_data[ChartType.WEIGHT.value]["y"]):
                last_weight = fig_data[ChartType.WEIGHT.value]["y"][e] or last_weight
                fig_data[ChartType.WEIGHT.value]["y"][e] = last_weight

        app_logger.debug(f"fig_data: {json.dumps(fig_data, indent=2)}")

        ll = None
        for s in fig_data:
            x = fig_data[s]["x"]
            y = fig_data[s]["y"]
            if not all(v == 0 for v in y):
                color = "green"
                # for duration, use ColumnDataSource with strtime
                if chart_type in [ChartType.HOUR, ChartType.SUM_HOUR]:
                    source = ColumnDataSource(
                        {
                            "x": x,
                            "y": y,
                            "strtime": fig_data[s]["strtime"],
                        }
                    )
                    ll = fig.line(
                        color=color,
                        legend_label=s,
                        line_width=2,
                        source=source,
                    )
                    fig.scatter(
                        color=color,
                        legend_label=s,
                        source=source,
                    )
                else:
                    ll = fig.line(x, y, legend_label=s, color=color, line_width=2)
                    fig.scatter(x, y, legend_label=s, color=color, line_width=2)

        # add hover tool with appropriate tooltips
        match chart_type:
            case ChartType.HOUR | ChartType.SUM_HOUR:
                tooltips = "@strtime"
            case ChartType.KM | ChartType.SUM_KM:
                tooltips = "@y{int} km"
            case ChartType.KG | ChartType.SUM_KG:
                tooltips = "@y{int} kg"
            case ChartType.WEIGHT:
                tooltips = "@y{0.0} kg"
            case _:
                tooltips = "@y{int}"

        fig.add_tools(
            bokeh_models.HoverTool(
                tooltips=tooltips,
                renderers=[ll] if ll is not None else [],
                mode="vline",
            )
        )

        if is_mobile_view:
            fig.legend.visible = False
        else:
            fig.legend.location = "top_left"

    script, div = bokeh_embed.components(fig)

    return script, div


def total_km_per_week_in_year(
    cal_heatmap: views.CalendarHeatmap,
    year: int,
    cumulative: bool = False,
    is_mobile_view: bool = False,
) -> tuple[str, Any]:
    """Total **km** per week in given year chart:

    x: week
    y: total km per week

    """
    return _weekly_totals(
        cal_heatmap=cal_heatmap,
        year=year,
        chart_type=ChartType.KM,
        cumulative=cumulative,
        is_mobile_view=is_mobile_view,
    )


def total_hours_per_week_in_year(
    cal_heatmap: views.CalendarHeatmap,
    year: int,
    cumulative: bool = False,
    is_mobile_view: bool = False,
) -> tuple[str, Any]:
    """Total **hours** per week in given year chart:

    x: week
    y: total hours per week

    """
    return _weekly_totals(
        cal_heatmap=cal_heatmap,
        year=year,
        chart_type=ChartType.HOUR,
        cumulative=cumulative,
        is_mobile_view=is_mobile_view,
    )


def total_kg_per_week_in_year(
    cal_heatmap: views.CalendarHeatmap,
    year: int,
    cumulative: bool = False,
    is_mobile_view: bool = False,
) -> tuple[str, Any]:
    """Total **hours** per week in given year chart:

    x: week
    y: total kg per week

    """
    return _weekly_totals(
        cal_heatmap=cal_heatmap,
        year=year,
        chart_type=ChartType.KG,
        cumulative=cumulative,
        is_mobile_view=is_mobile_view,
    )


def average_weight_per_week_in_year(
    cal_heatmap: views.CalendarHeatmap, year: int, is_mobile_view: bool = False
) -> tuple[str, Any]:
    """Average **weight** per week in given year chart:

    x: week
    y: average weight per week

    """
    return _weekly_totals(
        cal_heatmap=cal_heatmap,
        year=year,
        chart_type=ChartType.WEIGHT,
        is_mobile_view=is_mobile_view,
    )


def year_over_year_performance(
    ds_stats: stats.UserDatasetStats, is_mobile_view: bool = False
) -> tuple[str, Any]:
    """Year-over-year performance trends chart showing multiple metrics.

    Creates a comprehensive multi-line chart with:
    - Activities count per year
    - UKM (Universal Kilometers) per year
    - Training hours per year
    - Average UKM per activity (intensity)

    Parameters
    ----------
    ds_stats : stats.UserDatasetStats
        Dataset statistics containing year-by-year data
    is_mobile_view : bool
        Whether to optimize for mobile view

    Returns
    -------
    tuple[str, Any]
        Bokeh script and div components

    """
    if not ds_stats.years or len(ds_stats.years) < 2:
        # need at least 2 years for trends
        return "", "<div><p>Not enough data for year-over-year analysis.</p></div>"

    years = sorted(ds_stats.years)

    # prepare data
    activities_data = []
    ukm_data = []
    hours_data = []
    avg_ukm_data = []

    for year in years:
        year_stats = ds_stats.year.get(year)
        if year_stats:
            activities_data.append(year_stats.activities_count)
            ukm_data.append(year_stats.ukm)
            hours_data.append(year_stats.us / 3600.0 if year_stats.us else 0)
            avg_ukm = (
                year_stats.ukm / year_stats.activities_count
                if year_stats.activities_count > 0
                else 0
            )
            avg_ukm_data.append(avg_ukm)

    # create comprehensive data source with all metrics
    source = ColumnDataSource(
        data={
            "years": years,
            "activities": activities_data,
            "ukm": [int(u) for u in ukm_data],
            "hours": [round(h, 1) for h in hours_data],
            "avg_ukm": [round(a, 1) for a in avg_ukm_data],
        }
    )

    # create figure
    fig = bokeh_plt.figure(
        title="Year-over-Year Performance Trends",
        x_axis_label="Year",
        y_axis_label="Scaled Metrics (hover for actual values)",
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=400,
        toolbar_location="below" if not is_mobile_view else None,
    )
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    # set x-axis to show years as integers
    fig.xaxis.ticker = years

    # calculate scaling factors to normalize all metrics to similar range
    max_activities = max(activities_data) if activities_data else 1
    ukm_scale = max_activities / max(ukm_data) if max(ukm_data) > 0 else 1
    hours_scale = max_activities / max(hours_data) if max(hours_data) > 0 else 1
    avg_scale = max_activities / max(avg_ukm_data) if max(avg_ukm_data) > 0 else 1

    # scale data for visualization
    ukm_scaled = [ukm * ukm_scale for ukm in ukm_data]
    hours_scaled = [h * hours_scale for h in hours_data]
    avg_scaled = [a * avg_scale for a in avg_ukm_data]

    # line 1: activities count
    fig.line(
        x="years",
        y="activities",
        line_width=2,
        color="#206bc4",
        legend_label="Activities",
        alpha=0.8,
        source=source,
    )
    fig.scatter(
        x="years",
        y="activities",
        size=8,
        color="#206bc4",
        alpha=0.8,
        source=source,
        legend_label="Activities",
    )

    # line 2: UKM (scaled)
    source.data["ukm_scaled"] = ukm_scaled
    fig.line(
        x="years",
        y="ukm_scaled",
        line_width=2,
        color="#2fb344",
        legend_label="UKM",
        alpha=0.8,
        source=source,
    )
    fig.scatter(
        x="years",
        y="ukm_scaled",
        size=8,
        color="#2fb344",
        alpha=0.8,
        source=source,
        legend_label="UKM",
    )

    # line 3: training hours (scaled)
    source.data["hours_scaled"] = hours_scaled
    fig.line(
        x="years",
        y="hours_scaled",
        line_width=2,
        color="#f59f00",
        legend_label="Hours",
        alpha=0.8,
        source=source,
    )
    fig.scatter(
        x="years",
        y="hours_scaled",
        size=8,
        color="#f59f00",
        alpha=0.8,
        source=source,
        legend_label="Hours",
    )

    # line 4: average UKM per activity (scaled)
    source.data["avg_scaled"] = avg_scaled
    fig.line(
        x="years",
        y="avg_scaled",
        line_width=2,
        color="#d63939",
        legend_label="Avg UKM/Activity",
        alpha=0.8,
        line_dash="dashed",
        source=source,
    )
    fig.scatter(
        x="years",
        y="avg_scaled",
        size=8,
        color="#d63939",
        alpha=0.8,
        source=source,
        legend_label="Avg UKM/Activity",
    )

    # configure legend
    if is_mobile_view:
        fig.legend.visible = False
    else:
        fig.legend.location = "top_left"
        fig.legend.click_policy = "hide"

    # add comprehensive hover tool showing all actual values
    hover = bokeh_models.HoverTool(
        tooltips=[
            ("Year", "@years"),
            ("Activities", "@activities"),
            ("UKM", "@ukm{0,0}"),
            ("Hours", "@hours{0.0}"),
            ("Avg UKM/Activity", "@avg_ukm{0.0}"),
        ],
        mode="vline",
    )
    fig.add_tools(hover)

    script, div = bokeh_embed.components(fig)

    return script, div


def activity_paces_by_distance(
    activities: list[entities.ActivityEntity],
    activity_types: settings.UserActivityTypes,
    filter_activity_type: str = "",
    is_mobile_view: bool = False,
) -> tuple[str, Any]:
    """Line chart showing pace trends grouped by distance bins.

    x-axis: activity date (time)
    y-axis: pace (minutes:seconds per km)
    Multiple lines: one per distance bin

    Distance bins:
    - 0-3km
    - 3.001-5km
    - 5.001-10km
    - 10.001-22km
    - 22.001-43km
    - 43km+

    Parameters
    ----------
    activities : list[entities.ActivityEntity]
        List of distance/endurance activities sorted by date.
    activity_types : settings.UserActivityTypes
        User activity types for filtering.
    filter_activity_type : str
        Filter by specific activity_type_key (activity type).
    is_mobile_view : bool
        True if rendering for mobile view.

    """
    # Define distance bins (in meters)
    bins = [
        (0, 3000, "0-3km"),
        (3001, 5000, "3-5km"),
        (5001, 10000, "5-10km"),
        (10001, 22000, "10-22km"),
        (22001, 43000, "22-43km"),
        (43001, float("inf"), "43km+"),
    ]

    # Organize activities by bin
    bin_activities = {bin_label: [] for _, _, bin_label in bins}

    for a in activities:
        # Skip non-distance/endurance activities
        if activity_types.is_meta(a.activity_type_key):
            continue
        # Apply activity_type_key filter if specified
        if filter_activity_type and a.activity_type_key != filter_activity_type:
            continue
        # Check if activity has distance and duration
        if not a.distance or not a.duration_seconds:
            continue

        # Calculate pace (minutes per km)
        pace_minutes_per_km = (a.duration_seconds / 60.0) / (a.distance / 1000.0)

        # Find appropriate bin
        for min_dist, max_dist, bin_label in bins:
            if min_dist < a.distance <= max_dist:
                bin_activities[bin_label].append(
                    {
                        "date": datetime.datetime(
                            a.when_year, a.when_month, a.when_day
                        ),
                        "pace": pace_minutes_per_km,
                        "activity": a,
                    }
                )
                break

    # Create Bokeh figure
    fig = bokeh_plt.figure(
        title="Pace Trends by Distance",
        x_axis_type="datetime",
        y_axis_label="Pace (min/km)",
        background_fill_color="#fafafa",
        toolbar_location="below" if not is_mobile_view else None,
        width=VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT,
        height=550,
    )
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    # Define colors for each bin
    colors = [
        "#206bc4",
        "#37b24d",
        "#f59f00",
        "#d6336c",
        "#9775fa",
        "#fd7e14",
    ]

    hover_renderers = []
    has_data = False

    # Draw lines for each bin with data
    for (min_dist, max_dist, bin_label), color in zip(bins, colors):
        data_points = bin_activities[bin_label]
        if not data_points:
            continue

        has_data = True
        # Sort by date
        data_points.sort(key=lambda x: x["date"])

        x_data = [p["date"] for p in data_points]
        y_data = [p["pace"] for p in data_points]

        source = ColumnDataSource(
            {
                "x": x_data,
                "y": y_data,
                "label": [bin_label for _ in x_data],
                "distance": [
                    f"{p['activity'].distance / 1000:.1f}" for p in data_points
                ],
            }
        )

        line = fig.line(
            x="x",
            y="y",
            source=source,
            legend_label=bin_label,
            color=color,
            line_width=2,
            alpha=0.8,
        )
        fig.scatter(
            x="x",
            y="y",
            source=source,
            legend_label=bin_label,
            color=color,
            size=6,
            alpha=0.6,
        )
        hover_renderers.append(line)

    if not has_data:
        # Add text annotation when no data
        fig.text(
            x=[datetime.datetime(2020, 1, 1)],
            y=[0.5],
            text=["No pace data available"],
            text_font_size="14pt",
            text_color="gray",
            text_align="center",
        )
    else:
        fig.add_tools(
            bokeh_models.HoverTool(
                tooltips=[
                    ("Bin", "@label"),
                    ("Pace", "@y{0.00} min/km"),
                    ("Distance", "@distance km"),
                    ("Date", "@x{%F}"),
                ],
                formatters={"@x": "datetime"},
                renderers=hover_renderers,
                mode="vline",
            )
        )

        if not is_mobile_view:
            fig.legend.location = "top_left"
            fig.legend.click_policy = "hide"
        else:
            fig.legend.visible = False

    script, div = bokeh_embed.components(fig)

    return script, div


def goals_eisenhower_matrix(
    goals: settings.UserGoals,
    activity_types: settings.UserActivityTypes,
    is_mobile_view: bool = False,
    zoom_level: float = 0.7,
) -> tuple[str, Any]:
    """Eisenhower matrix scatter plot for goals.

    Parameters
    ----------
    goals : settings.UserGoals
        user goals
    activity_types : settings.UserActivityTypes
        user activity types
    is_mobile_view : bool
        whether to render for mobile
    zoom_level : float
        zoom level for the chart (0.3 to 1.5)

    Returns
    -------
    tuple[str, Any]
        Bokeh script and div
    """
    base_width = VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT
    actual_width = int(base_width * zoom_level)
    actual_height = int(base_width * zoom_level)

    # create figure
    fig = bokeh_plt.figure(
        title="Eisenhower Matrix - Goal Prioritization",
        x_axis_label="Importance (%)",
        y_axis_label="Urgency (%)",
        background_fill_color="#fafafa",
        toolbar_location="below" if not is_mobile_view else None,
        width=actual_width,
        height=actual_height,
        x_range=(0, 100),
        y_range=(0, 100),
    )
    fig.toolbar.logo = None

    # add quadrant background boxes
    # Q4 (bottom-left): Not Urgent, Not Important
    fig.quad(
        top=50,
        bottom=0,
        left=0,
        right=50,
        color="#95a5a6",
        alpha=0.1,
        line_width=0,
    )
    # Q3 (top-left): Urgent, Not Important
    fig.quad(
        top=100,
        bottom=50,
        left=0,
        right=50,
        color="#ffe66d",
        alpha=0.15,
        line_width=0,
    )
    # Q2 (bottom-right): Not Urgent, Important
    fig.quad(
        top=50,
        bottom=0,
        left=50,
        right=100,
        color="#4ecdc4",
        alpha=0.15,
        line_width=0,
    )
    # Q1 (top-right): Urgent, Important
    fig.quad(
        top=100,
        bottom=50,
        left=50,
        right=100,
        color="#ff6b6b",
        alpha=0.2,
        line_width=0,
    )

    # add grid lines at 50% marks
    fig.line(
        [50, 50],
        [0, 100],
        line_width=2,
        color="gray",
        line_dash="dashed",
        alpha=0.5,
    )
    fig.line(
        [0, 100],
        [50, 50],
        line_width=2,
        color="gray",
        line_dash="dashed",
        alpha=0.5,
    )

    # add quadrant labels
    label_style = {
        "text_font_size": "12pt",
        "text_color": "gray",
        "text_alpha": 0.5,
        "text_font_style": "bold",
    }
    fig.text(x=[25], y=[75], text=["Q3: QUICK WINS"], **label_style)
    fig.text(x=[75], y=[75], text=["Q1: FOCUS NOW"], **label_style)
    fig.text(x=[25], y=[25], text=["Q4: RECONSIDER"], **label_style)
    fig.text(x=[75], y=[25], text=["Q2: PLAN & BUILD"], **label_style)

    # prepare data for goals (exclude done goals)
    active_goals = [g for g in goals.goals if not g.done]

    if active_goals:
        # convert to percentages and prepare data
        x_data = [g.importance * 100 for g in active_goals]
        y_data = [g.urgency * 100 for g in active_goals]
        names = [g.name for g in active_goals]

        # determine colors based on quadrant
        colors = []
        for g in active_goals:
            if g.urgency >= 0.5 and g.importance >= 0.5:
                colors.append("#ff6b6b")  # Q1: Red
            elif g.urgency < 0.5 and g.importance >= 0.5:
                colors.append("#4ecdc4")  # Q2: Blue
            elif g.urgency >= 0.5 and g.importance < 0.5:
                colors.append("#ffe66d")  # Q3: Yellow
            else:
                colors.append("#95a5a6")  # Q4: Gray

        # get activity type names for tooltips
        activity_names = []
        for g in active_goals:
            at = activity_types.activity_types_by_key.get(g.activity_type)
            activity_names.append(at.name if at else g.activity_type)

        # create ColumnDataSource for tooltips
        source = ColumnDataSource(
            data={
                "importance": x_data,
                "urgency": y_data,
                "name": names,
                "activity": activity_names,
                "color": colors,
            }
        )

        # plot goals as circles
        circles = fig.circle(
            "importance",
            "urgency",
            source=source,
            size=12,
            color="color",
            alpha=0.7,
            line_color="black",
            line_width=1,
        )

        # add hover tooltip
        hover = bokeh_models.HoverTool(
            renderers=[circles],
            tooltips=[
                ("Goal", "@name"),
                ("Activity", "@activity"),
                ("Urgency", "@urgency{0.0}%"),
                ("Importance", "@importance{0.0}%"),
            ],
        )
        fig.add_tools(hover)
    else:
        # no active goals - show message
        fig.text(
            x=[50],
            y=[50],
            text=["No active goals. Create your first goal!"],
            text_font_size="14pt",
            text_color="gray",
            text_align="center",
        )

    # format axes as percentages - use NumeralTickFormatter
    fig.xaxis.formatter = bokeh_models.NumeralTickFormatter(format="0")
    fig.yaxis.formatter = bokeh_models.NumeralTickFormatter(format="0")

    script, div = bokeh_embed.components(fig)
    return script, div


def weekday_activity_heatmap(
    weekday_activities_heatmap: dict,
    heatmap_sports: list,
    is_mobile_view: bool = False,
) -> tuple[str, Any]:
    """Topographic heatmap: weekdays (x) vs activity_types (y), color = activity count.

    Parameters
    ----------
    weekday_activities_heatmap : dict
        Map weekday -> activity_type_key -> (count, color_hex).
    heatmap_sports : list
        Sports sorted by total count descending.
    is_mobile_view : bool
        Render narrower chart for mobile viewports.

    Returns
    -------
    tuple[str, Any]
        Bokeh (script, div) pair.
    """
    weekdays = list(weekday_activities_heatmap.keys())
    # reverse so the most popular activity_type_key sits at the top
    sports = list(reversed(heatmap_sports))

    xs, ys, counts, labels = [], [], [], []
    for weekday in weekdays:
        for sport in sports:
            xs.append(weekday)
            ys.append(sport)
            count = weekday_activities_heatmap[weekday].get(sport, (0, "#ffffff"))[0]
            counts.append(count)
            labels.append(str(count) if count > 0 else "")

    max_count = max(counts) if counts else 1

    # Viridis256: dark blue/purple = low, bright yellow = high (topographic look)
    mapper = bokeh_models.LinearColorMapper(
        palette=bokeh_viridis256,
        low=0,
        high=max_count,
    )

    source = ColumnDataSource(dict(x=xs, y=ys, count=counts, label=labels))

    width = VIEW_WIDTH_MOBILE if is_mobile_view else VIEW_WIDTH_DEFAULT
    cell_height = max(40, min(70, 400 // max(len(sports), 1)))

    fig = bokeh_plt.figure(
        x_range=weekdays,
        y_range=sports,
        width=width,
        height=cell_height * len(sports) + 120,
        toolbar_location="below",
        title="Activity Frequency Heatmap — Weekday × Sport",
    )
    fig.sizing_mode = "scale_width"
    fig.toolbar.logo = None

    rects = fig.rect(
        x="x",
        y="y",
        width=0.95,
        height=0.95,
        source=source,
        fill_color={"field": "count", "transform": mapper},
        line_color="white",
        line_width=1,
    )

    # count labels inside cells
    fig.text(
        x="x",
        y="y",
        text="label",
        source=source,
        text_align="center",
        text_baseline="middle",
        text_font_size="11pt",
        text_color="white",
    )

    color_bar = bokeh_models.ColorBar(
        color_mapper=mapper,
        label_standoff=8,
        location=(0, 0),
        title="Activities",
    )
    fig.add_layout(color_bar, "right")

    hover = bokeh_models.HoverTool(
        renderers=[rects],
        tooltips=[
            ("Day", "@x"),
            ("Sport", "@y"),
            ("Activities", "@count"),
        ],
    )
    fig.add_tools(hover)

    fig.axis.axis_line_color = None
    fig.axis.major_tick_line_color = None
    fig.xaxis.major_label_text_font_size = "11pt"
    fig.yaxis.major_label_text_font_size = "11pt"
    fig.xgrid.grid_line_color = None
    fig.ygrid.grid_line_color = None

    script, div = bokeh_embed.components(fig)
    return script, div
