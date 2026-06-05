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
"""3D impulse-response metrics based on CP/W′/Pmax and strain score.

References
----------
Equations follow `FEATURE_3D_IRM_METRIC_SUITE.2503.14841v2.pdf`:

- Eq.4 MPA model
- Eq.8-10 system power contributions
- Eq.11-13 strain coefficient/rate/score
- Eq.17 style exponential impulse-response update
"""

import dataclasses
import datetime
import math

from mytral.recordings import models as recording_models

SECONDS_PER_HOUR = 3600.0
MAX_SAMPLE_DT_SECONDS = 10.0

DEFAULT_W_PRIME_JOULES = 18000.0
DEFAULT_PMAX_MULTIPLIER = 1.8
DEFAULT_MIN_PMAX_WATTS = 400.0


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


@dataclasses.dataclass
class PowerModelParams:
    """Power-duration model parameters.

    Parameters
    ----------
    cp_watts : float
        Critical power (W).
    w_prime_joules : float
        Work prime capacity (J).
    pmax_watts : float
        Maximal sprint power (W).
    """

    cp_watts: float
    w_prime_joules: float
    pmax_watts: float

    def validate(self) -> None:
        """Validate parameter relationships."""
        if self.cp_watts <= 0:
            raise ValueError("CP must be > 0.")
        if self.w_prime_joules <= 0:
            raise ValueError("W′ must be > 0.")
        if self.pmax_watts <= self.cp_watts:
            raise ValueError("Pmax must be greater than CP.")


@dataclasses.dataclass
class IrmDimensionParams:
    """Impulse-response parameters for one dimension."""

    k1: float = 1.0
    k2: float = 1.5
    tau1_days: float = 42.0
    tau2_days: float = 7.0
    readiness_scale: float = 1.0


@dataclasses.dataclass
class Irm3dParams:
    """Impulse-response settings for CP/W′/Pmax dimensions."""

    cp: IrmDimensionParams = dataclasses.field(default_factory=IrmDimensionParams)
    w_prime: IrmDimensionParams = dataclasses.field(default_factory=IrmDimensionParams)
    pmax: IrmDimensionParams = dataclasses.field(default_factory=IrmDimensionParams)


@dataclasses.dataclass
class SecondStrain:
    """Per-sample strain decomposition."""

    kstrain: float
    ss_total: float
    ss_cp: float
    ss_w_prime: float
    ss_pmax: float


@dataclasses.dataclass
class WorkoutStrainBreakdown:
    """Workout-level strain decomposition."""

    activity_key: str
    date: datetime.date
    ss_total: float
    ss_cp: float
    ss_w_prime: float
    ss_pmax: float
    min_mpa_watts: float
    max_power_watts: float
    near_limit_seconds: float
    samples: int


@dataclasses.dataclass
class DailyStrainRow:
    """Daily aggregated strain values."""

    date: datetime.date
    ss_total: float
    ss_cp: float
    ss_w_prime: float
    ss_pmax: float
    workouts: int
    near_limit_seconds: float
    min_mpa_watts: float


@dataclasses.dataclass
class Irm3dStateRow:
    """Per-day 3D impulse-response state."""

    date: datetime.date
    load_cp: float
    load_w_prime: float
    load_pmax: float
    cp_fitness: float
    cp_fatigue: float
    cp_readiness: float
    w_prime_fitness: float
    w_prime_fatigue: float
    w_prime_readiness: float
    pmax_fitness: float
    pmax_fatigue: float
    pmax_readiness: float
    cp_watts: float
    w_prime_joules: float
    pmax_watts: float


@dataclasses.dataclass
class Irm3dTimeseries:
    """Per-second 3D IRM time series for a single workout.

    All lists have the same length (one entry per power sample).
    Timestamps are Python datetime objects for chart axis labelling.
    """

    timestamps: list[datetime.datetime]
    power_watts: list[float]
    mpa_watts: list[float]
    w_prime_expended_joules: list[float]
    kstrain: list[float]
    ss_total: list[float]
    ss_cp: list[float]
    ss_w_prime: list[float]
    ss_pmax: list[float]


def compute_mpa(
    model_params: PowerModelParams, w_prime_expended_joules: float
) -> float:
    """Compute maximum power available (MPA), Eq.4."""
    model_params.validate()
    ratio = _clamp(w_prime_expended_joules / model_params.w_prime_joules, 0.0, 1.0)
    return model_params.pmax_watts - (
        (model_params.pmax_watts - model_params.cp_watts) * ratio
    )


def compute_system_power_contrib(
    power_watts: float,
    model_params: PowerModelParams,
) -> tuple[float, float, float]:
    """Compute CP/W′/Pmax power shares, Eq.8-10.

    Returns
    -------
    tuple[float, float, float]
        ``(cp_share_w, w_prime_share_w, pmax_share_w)``.
    """
    model_params.validate()

    power = max(0.0, power_watts)
    if power <= model_params.cp_watts:
        return power, 0.0, 0.0

    delta = power - model_params.cp_watts
    pmax_share = (delta * delta) / (model_params.pmax_watts - model_params.cp_watts)
    pmax_share = _clamp(pmax_share, 0.0, delta)
    w_prime_share = max(0.0, delta - pmax_share)
    return model_params.cp_watts, w_prime_share, pmax_share


def compute_kstrain(
    power_watts: float,
    mpa_watts: float,
    model_params: PowerModelParams,
) -> float:
    """Compute strain coefficient, Eq.11."""
    model_params.validate()
    power = _clamp(power_watts, 0.0, model_params.pmax_watts)
    mpa = _clamp(mpa_watts, model_params.cp_watts, model_params.pmax_watts)

    numerator = model_params.pmax_watts - mpa + model_params.cp_watts
    denominator = model_params.pmax_watts - power + model_params.cp_watts
    if denominator <= 0:
        return 1.0
    return max(0.0, numerator / denominator)


def compute_second_strain(
    power_watts: float,
    mpa_watts: float,
    model_params: PowerModelParams,
) -> SecondStrain:
    """Compute one-second strain decomposition, Eq.11-13."""
    model_params.validate()

    power = _clamp(power_watts, 0.0, model_params.pmax_watts)
    if power <= 0:
        return SecondStrain(
            kstrain=0.0,
            ss_total=0.0,
            ss_cp=0.0,
            ss_w_prime=0.0,
            ss_pmax=0.0,
        )

    kstrain = compute_kstrain(
        power_watts=power, mpa_watts=mpa_watts, model_params=model_params
    )
    strain_rate = kstrain * power
    ss_scale = (
        model_params.pmax_watts / (model_params.cp_watts * model_params.cp_watts)
    ) * (100.0 / SECONDS_PER_HOUR)
    ss_total = strain_rate * ss_scale

    cp_share, w_prime_share, pmax_share = compute_system_power_contrib(
        power_watts=power,
        model_params=model_params,
    )
    ss_cp = ss_total * (cp_share / power)
    ss_w_prime = ss_total * (w_prime_share / power)
    ss_pmax = ss_total * (pmax_share / power)
    return SecondStrain(
        kstrain=kstrain,
        ss_total=ss_total,
        ss_cp=ss_cp,
        ss_w_prime=ss_w_prime,
        ss_pmax=ss_pmax,
    )


def _sample_dt_seconds(
    recording_data: recording_models.RecordingData,
    sample_index: int,
    previous_timestamp: datetime.datetime | None,
) -> tuple[float, datetime.datetime | None]:
    """Resolve sample duration in seconds for integration."""
    if sample_index >= len(recording_data.timestamps):
        return 1.0, previous_timestamp

    timestamp = recording_data.timestamps[sample_index]
    if previous_timestamp is None:
        return 1.0, timestamp

    dt_seconds = (timestamp - previous_timestamp).total_seconds()
    if dt_seconds <= 0:
        return 0.0, timestamp
    return min(dt_seconds, MAX_SAMPLE_DT_SECONDS), timestamp


def compute_workout_strain_from_recording(
    recording_data: recording_models.RecordingData,
    model_params: PowerModelParams,
    activity_key: str,
    activity_date: datetime.date,
    near_limit_ratio: float = 0.9,
) -> WorkoutStrainBreakdown | None:
    """Compute workout SS decomposition from power timeseries."""
    model_params.validate()
    if not recording_data.has_power or not recording_data.power_values:
        return None

    w_prime_expended = 0.0
    ss_total = 0.0
    ss_cp = 0.0
    ss_w_prime = 0.0
    ss_pmax = 0.0
    near_limit_seconds = 0.0
    min_mpa = model_params.pmax_watts
    max_power = 0.0
    sample_count = 0

    previous_timestamp: datetime.datetime | None = None

    for i, power_value in enumerate(recording_data.power_values):
        if power_value is None:
            continue
        if not math.isfinite(power_value):
            continue

        dt_seconds, previous_timestamp = _sample_dt_seconds(
            recording_data=recording_data,
            sample_index=i,
            previous_timestamp=previous_timestamp,
        )
        if dt_seconds <= 0:
            continue

        power = _clamp(float(power_value), 0.0, model_params.pmax_watts)
        if power > model_params.cp_watts:
            w_prime_expended += (power - model_params.cp_watts) * dt_seconds
            w_prime_expended = min(w_prime_expended, model_params.w_prime_joules)

        mpa = compute_mpa(
            model_params=model_params,
            w_prime_expended_joules=w_prime_expended,
        )
        min_mpa = min(min_mpa, mpa)
        max_power = max(max_power, power)

        second_strain = compute_second_strain(
            power_watts=power,
            mpa_watts=mpa,
            model_params=model_params,
        )
        ss_total += second_strain.ss_total * dt_seconds
        ss_cp += second_strain.ss_cp * dt_seconds
        ss_w_prime += second_strain.ss_w_prime * dt_seconds
        ss_pmax += second_strain.ss_pmax * dt_seconds
        if mpa > 0 and power / mpa >= near_limit_ratio:
            near_limit_seconds += dt_seconds
        sample_count += 1

    if sample_count == 0:
        return None

    return WorkoutStrainBreakdown(
        activity_key=activity_key,
        date=activity_date,
        ss_total=ss_total,
        ss_cp=ss_cp,
        ss_w_prime=ss_w_prime,
        ss_pmax=ss_pmax,
        min_mpa_watts=min_mpa,
        max_power_watts=max_power,
        near_limit_seconds=near_limit_seconds,
        samples=sample_count,
    )


def compute_workout_irm3d_timeseries(
    recording_data: recording_models.RecordingData,
    model_params: PowerModelParams,
) -> Irm3dTimeseries | None:
    """Compute per-second 3D IRM time series for a single workout recording.

    Unlike ``compute_workout_strain_from_recording`` which returns aggregated
    totals, this function retains every sample so that time-series charts can
    be rendered (power, MPA, W′ expended, kstrain, and the SS breakdown).

    Parameters
    ----------
    recording_data : RecordingData
        Parsed recording with power values and timestamps.
    model_params : PowerModelParams
        CP / W′ / Pmax parameters for the athlete.

    Returns
    -------
    Irm3dTimeseries or None
        Per-second arrays, or None if the recording has no power data.
    """
    model_params.validate()
    if not recording_data.has_power or not recording_data.power_values:
        return None

    w_prime_expended = 0.0
    sample_count = 0

    # per-sample output arrays
    timestamps: list[datetime.datetime] = []
    power_watts: list[float] = []
    mpa_watts_list: list[float] = []
    w_prime_list: list[float] = []
    kstrain_list: list[float] = []
    ss_total_list: list[float] = []
    ss_cp_list: list[float] = []
    ss_w_prime_list: list[float] = []
    ss_pmax_list: list[float] = []

    previous_timestamp: datetime.datetime | None = None

    for i, power_value in enumerate(recording_data.power_values):
        if power_value is None:
            continue
        if not math.isfinite(power_value):
            continue

        dt_seconds, previous_timestamp = _sample_dt_seconds(
            recording_data=recording_data,
            sample_index=i,
            previous_timestamp=previous_timestamp,
        )
        if dt_seconds <= 0:
            continue

        power = _clamp(float(power_value), 0.0, model_params.pmax_watts)
        if power > model_params.cp_watts:
            w_prime_expended += (power - model_params.cp_watts) * dt_seconds
            w_prime_expended = min(w_prime_expended, model_params.w_prime_joules)

        mpa = compute_mpa(
            model_params=model_params,
            w_prime_expended_joules=w_prime_expended,
        )
        second_strain = compute_second_strain(
            power_watts=power,
            mpa_watts=mpa,
            model_params=model_params,
        )

        # timestamp for this sample
        if i < len(recording_data.timestamps):
            ts = recording_data.timestamps[i]
        else:
            ts = previous_timestamp or datetime.datetime.min
        timestamps.append(ts)

        power_watts.append(power)
        mpa_watts_list.append(mpa)
        w_prime_list.append(w_prime_expended)
        kstrain_list.append(second_strain.kstrain)
        ss_total_list.append(second_strain.ss_total)
        ss_cp_list.append(second_strain.ss_cp)
        ss_w_prime_list.append(second_strain.ss_w_prime)
        ss_pmax_list.append(second_strain.ss_pmax)
        sample_count += 1

    if sample_count == 0:
        return None

    return Irm3dTimeseries(
        timestamps=timestamps,
        power_watts=power_watts,
        mpa_watts=mpa_watts_list,
        w_prime_expended_joules=w_prime_list,
        kstrain=kstrain_list,
        ss_total=ss_total_list,
        ss_cp=ss_cp_list,
        ss_w_prime=ss_w_prime_list,
        ss_pmax=ss_pmax_list,
    )


def aggregate_daily_strain(
    workout_rows: list[WorkoutStrainBreakdown],
) -> list[DailyStrainRow]:
    """Aggregate workout strain rows into daily rows with date gaps filled."""
    if not workout_rows:
        return []

    by_day: dict[datetime.date, DailyStrainRow] = {}
    for row in workout_rows:
        day_row = by_day.get(row.date)
        if day_row is None:
            day_row = DailyStrainRow(
                date=row.date,
                ss_total=0.0,
                ss_cp=0.0,
                ss_w_prime=0.0,
                ss_pmax=0.0,
                workouts=0,
                near_limit_seconds=0.0,
                min_mpa_watts=row.min_mpa_watts,
            )
            by_day[row.date] = day_row

        day_row.ss_total += row.ss_total
        day_row.ss_cp += row.ss_cp
        day_row.ss_w_prime += row.ss_w_prime
        day_row.ss_pmax += row.ss_pmax
        day_row.workouts += 1
        day_row.near_limit_seconds += row.near_limit_seconds
        day_row.min_mpa_watts = min(day_row.min_mpa_watts, row.min_mpa_watts)

    first_day = min(by_day.keys())
    last_day = max(by_day.keys())
    result: list[DailyStrainRow] = []
    current_day = first_day

    while current_day <= last_day:
        existing = by_day.get(current_day)
        if existing is not None:
            result.append(existing)
        else:
            result.append(
                DailyStrainRow(
                    date=current_day,
                    ss_total=0.0,
                    ss_cp=0.0,
                    ss_w_prime=0.0,
                    ss_pmax=0.0,
                    workouts=0,
                    near_limit_seconds=0.0,
                    min_mpa_watts=0.0,
                )
            )
        current_day += datetime.timedelta(days=1)

    return result


def _impulse_step(
    load_value: float,
    previous_fitness: float,
    previous_fatigue: float,
    dimension_params: IrmDimensionParams,
) -> tuple[float, float, float]:
    """Run one-day impulse-response update for one dimension."""
    fitness_decay = math.exp(-1.0 / dimension_params.tau1_days)
    fatigue_decay = math.exp(-1.0 / dimension_params.tau2_days)

    fitness = (previous_fitness * fitness_decay) + (load_value * (1.0 - fitness_decay))
    fatigue = (previous_fatigue * fatigue_decay) + (load_value * (1.0 - fatigue_decay))
    readiness = (dimension_params.k1 * fitness) - (dimension_params.k2 * fatigue)
    return fitness, fatigue, readiness


def convert_state_to_cp_wprime_pmax(
    state_row: Irm3dStateRow,
    model_params: PowerModelParams,
    irm_params: Irm3dParams,
) -> tuple[float, float, float]:
    """Convert IR readiness states to CP/W′/Pmax signatures."""
    cp_watts = max(
        0.0,
        model_params.cp_watts
        + (state_row.cp_readiness * irm_params.cp.readiness_scale),
    )
    w_prime_joules = max(
        0.0,
        model_params.w_prime_joules
        + (state_row.w_prime_readiness * irm_params.w_prime.readiness_scale),
    )
    pmax_watts = max(
        0.0,
        model_params.pmax_watts
        + (state_row.pmax_readiness * irm_params.pmax.readiness_scale),
    )
    return cp_watts, w_prime_joules, pmax_watts


def run_3d_impulse_response(
    daily_rows: list[DailyStrainRow],
    irm_params: Irm3dParams,
    model_params: PowerModelParams,
) -> list[Irm3dStateRow]:
    """Compute 3D fitness/fatigue/readiness and derived signatures."""
    model_params.validate()
    if not daily_rows:
        return []

    cp_fitness = cp_fatigue = 0.0
    w_prime_fitness = w_prime_fatigue = 0.0
    pmax_fitness = pmax_fatigue = 0.0
    state_rows: list[Irm3dStateRow] = []

    for daily_row in sorted(daily_rows, key=lambda row: row.date):
        cp_fitness, cp_fatigue, cp_readiness = _impulse_step(
            load_value=daily_row.ss_cp,
            previous_fitness=cp_fitness,
            previous_fatigue=cp_fatigue,
            dimension_params=irm_params.cp,
        )
        w_prime_fitness, w_prime_fatigue, w_prime_readiness = _impulse_step(
            load_value=daily_row.ss_w_prime,
            previous_fitness=w_prime_fitness,
            previous_fatigue=w_prime_fatigue,
            dimension_params=irm_params.w_prime,
        )
        pmax_fitness, pmax_fatigue, pmax_readiness = _impulse_step(
            load_value=daily_row.ss_pmax,
            previous_fitness=pmax_fitness,
            previous_fatigue=pmax_fatigue,
            dimension_params=irm_params.pmax,
        )

        state_row = Irm3dStateRow(
            date=daily_row.date,
            load_cp=daily_row.ss_cp,
            load_w_prime=daily_row.ss_w_prime,
            load_pmax=daily_row.ss_pmax,
            cp_fitness=cp_fitness,
            cp_fatigue=cp_fatigue,
            cp_readiness=cp_readiness,
            w_prime_fitness=w_prime_fitness,
            w_prime_fatigue=w_prime_fatigue,
            w_prime_readiness=w_prime_readiness,
            pmax_fitness=pmax_fitness,
            pmax_fatigue=pmax_fatigue,
            pmax_readiness=pmax_readiness,
            cp_watts=0.0,
            w_prime_joules=0.0,
            pmax_watts=0.0,
        )

        cp_watts, w_prime_joules, pmax_watts = convert_state_to_cp_wprime_pmax(
            state_row=state_row,
            model_params=model_params,
            irm_params=irm_params,
        )
        state_row.cp_watts = cp_watts
        state_row.w_prime_joules = w_prime_joules
        state_row.pmax_watts = pmax_watts
        state_rows.append(state_row)

    return state_rows
