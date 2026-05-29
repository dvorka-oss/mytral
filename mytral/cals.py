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
import math
import time

#
# calendar constants
#

WEEKDAY_INDEX_2_STR = {
    0: "Mon",
    1: "Tue",
    2: "Wed",
    3: "Thu",
    4: "Fri",
    5: "Sat",
    6: "Sun",
}

MONTH_INDEX_2_STR = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}

MONTH_STR_2_INDEX = {v: k for k, v in MONTH_INDEX_2_STR.items()}

FALLBACK_YEAR = 2000
FALLBACK_MONTH = 1
FALLBACK_DAY = 1

#
# calendar utils: date and  time
#


def get_week_day(year: int, month: int, day: int) -> int:
    """Find out whether the date is Monday, Tuesday, ..."""
    return datetime.date(year, month, day).weekday()  # Mon=0 ... Sun=6


def get_week_of_year(year: int, month: int, day: int) -> int:
    """Find out which week in the year is the date."""
    return datetime.date(year, month, day).isocalendar()[1]


def get_day_of_year(year: int, month: int, day: int) -> int:
    """Find out which day in the year is the date."""
    return datetime.date(year, month, day).timetuple().tm_yday


def get_yesterday(year: int, month: int, day: int) -> tuple[int, int, int]:
    d = datetime.date(year, month, day)
    d -= datetime.timedelta(days=1)

    return d.year, d.month, d.day


def get_tomorrow(year: int, month: int, day: int) -> tuple[int, int, int]:
    d = datetime.date(year, month, day)
    d += datetime.timedelta(days=1)

    return d.year, d.month, d.day


def get_monday(year: int, month: int, day: int) -> tuple[int, int, int]:
    """Get the Monday of the week where the date is."""
    while get_week_day(year, month, day) != 0:
        year, month, day = get_yesterday(year, month, day)

    return year, month, day


def get_sunday(year: int, month: int, day: int) -> tuple[int, int, int]:
    """Get the Sunday of the week where the date is."""
    while get_week_day(year, month, day) != 6:
        year, month, day = get_tomorrow(year, month, day)

    return year, month, day


def get_last_month(year: int = 0, month: int = 0) -> tuple[int, int]:
    if not month and not year:
        now = datetime.datetime.now()
        year = now.year
        month = now.month
    if month == 1:
        return year - 1, 12

    return year, month - 1


def get_same_day_in_another_year(
    week_number: int, week_day: int, target_year: int
) -> tuple[int, int, int]:
    """Get the same day ~ same week number and week day - in given year.

    Parameters
    ----------
    week_number : int
      Week number (1 - 53) in which to find the day.
    week_day : int
      Week day (0 - 6) which to ind in year.
    target_year : int
      Year for which to return the date.

    Returns
    -------
    tuple[int, int, int]
      Year, month, day.

    """
    # get the first day of the year
    d = datetime.date(target_year, 1, 1)
    # find the first Monday of the year
    while d.weekday() != week_day:
        d += datetime.timedelta(days=1)

    # find the first Monday of the week
    while d.isocalendar()[1] != week_number:
        d += datetime.timedelta(days=7)

    return d.year, d.month, d.day


def is_leap_year(year: int) -> bool:
    """Does year have 29th February?"""
    if year % 4 == 0 and year % 100 != 0 or year % 400 == 0:
        return True
    return False


def str_time_to_seconds(s: str) -> int:
    """Concert time string 00:00:00 to seconds."""
    if isinstance(s, str):
        if ":" in s:
            hh, mm, ss = s.split(":")
            return int(float(hh) * 3600 + float(mm) * 60 + float(ss))

        s = s.replace(",", "")

    return int(float(s) if not math.isnan(float(s)) else 0.0)


def seconds_to_tuple(seconds: int) -> tuple[int, int, int]:
    """Convert seconds to tuple (hours, minutes, seconds)."""
    return (
        int(seconds // 3600),
        int((seconds % 3600) // 60),
        int(seconds % 60),
    )


def seconds_to_str_time(seconds: int, colons_separator: bool = False) -> str:
    """Get times as hh:mm:ss from seconds."""
    h, m, s = seconds_to_tuple(seconds)
    return f"{h:}:{m:02}:{s:02}" if colons_separator else f"{h}h{m:02}m{s:02}s"


def seconds_to_chart_time(seconds: int | float) -> str:
    """Get time as HHhMM'SS" from seconds for chart display."""
    h, m, s = seconds_to_tuple(int(seconds))
    return f"{h}h{m:02}'{s:02}\""


def tuple_to_str_date(time_tuple: tuple | None = None, seconds: int = 0):
    """Get date time as string from the tuple.

    Parameters
    ----------
    seconds:
      Seconds.
    time_tuple:
      Time tuple

      (
        tm_year,tm_mon,tm_mday,
        tm_hour,tm_min,tm_sec,
        tm_wday,tm_yday,tm_isdst
      )
    """
    time_tuple = time_tuple or time.localtime(seconds)
    return time.strftime("%Y-%m-%d %H:%M:%S", time_tuple)


def get_age(year: int, month: int, day: int) -> int:
    """Get aget in years."""
    born = datetime.datetime(year, month, day)
    today = datetime.date.today()

    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def get_age_at(
    born_year: int,
    born_month: int,
    born_day: int,
    year: int,
    month: int = 12,
    day: int = 30,
) -> int:
    """Get age in years on the specific day."""
    if born_year and born_month and born_day:
        at_date = datetime.datetime(year, month, day)
        age = at_date.year - born_year
        if at_date.month < born_month or (
            at_date.month == born_month and at_date.day < born_day
        ):
            age -= 1

        return age
    return 0


def week_to_date(year: int, week: int, week_day: int) -> datetime.datetime:
    """Convert week date to date.

    Parameters
    ----------
    year : int
        Year.
    week : int
        Week number within the year.
    week_day : int
        Week day - Monday is 0, Sunday is 6.

    Returns
    -------
    datetime.datetime
        Date.

    """
    if week_day == 6:
        week_day = 0
    else:
        week_day += 1
    return datetime.datetime.strptime(f"{year}-W{week}-{week_day}", "%Y-W%W-%w")


def days_between_dates(from_date: str, to_date: str) -> int:
    """Return the number of dates between two dates like "2023-01-25" and
    "2025-02-21".
    """
    d1 = datetime.datetime.strptime(from_date, "%Y-%m-%d")
    d2 = datetime.datetime.strptime(to_date, "%Y-%m-%d")

    delta = d2 - d1

    return delta.days
