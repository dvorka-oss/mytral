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
"""Athlete performance metrics estimation and resolution.

Provides formulas for estimating key athlete metrics (max HR, FTP, zones,
VO2max, etc.) and the main resolve() function that populates all e_* fields
on an AthleteMetrics instance given a UserProfile and list of activities.

Convention: metric = 0 means "not set by athlete". e_metric is always
populated with either the athlete-set value or a MyTraL estimate.
All e_* fields are transient and never persisted to disk.
"""

from mytral import settings as app_settings
from mytral.backends import entities
from mytral.metrics import irm3d as irm3d_metrics

# HR zone percentages of LTHR (Coggan/Friel zones).
# Each tuple is (low_pct, high_pct); high of Z5 is always e_max_hr (None).
ZONE_BOUNDARIES: list[tuple[float, float | None]] = [
    (0.00, 0.85),  # Z1: Recovery
    (0.85, 0.90),  # Z2: Aerobic / Endurance
    (0.90, 0.95),  # Z3: Tempo
    (0.95, 1.06),  # Z4: Threshold / Sweetspot
    (1.06, None),  # Z5: Anaerobic / VO2max (upper = e_max_hr)
]

# Power zone percentages of FTP (Coggan cycling zones).
# 7-zone model based on FTP as the threshold.
# Each tuple is (low_pct, high_pct); high of Z7 is None (unlimited).
POWER_ZONE_BOUNDARIES: list[tuple[float, float | None]] = [
    (0.00, 0.61),  # Z1: Recovery
    (0.61, 0.83),  # Z2: Endurance
    (0.83, 1.00),  # Z3: Tempo
    (1.00, 1.17),  # Z4: Threshold
    (1.17, 1.33),  # Z5: VO2Max
    (1.33, 1.67),  # Z6: Anaerobic
    (1.67, None),  # Z7: Neuromuscular (unlimited)
]

# assumed resting HR for active people when not measured
REST_HR_DEFAULT: int = 60

# power-duration anchor table: (duration_minutes, fraction_of_ftp).
# Each entry represents the fraction of FTP an athlete can sustain for that
# duration in a genuine all-out effort. Values are linearly interpolated.
# Basis: activity_types-science literature + "2.5 h ≈ 75–82% FTP" coaching rule.
POWER_DURATION_ANCHORS: list[tuple[float, float]] = [
    (10.0, 1.150),  # 10 min: VO2max territory
    (20.0, 1.053),  # 20 min: standard field-test protocol (avg × 0.95 = FTP)
    (60.0, 1.000),  # 60 min: FTP by definition
    (90.0, 0.900),  # 90 min: empirical coaching rule
    (120.0, 0.850),  # 2h: empirical coaching rule
    (150.0, 0.785),  # 2.5h: midpoint of 75–82% hint
    (240.0, 0.720),  # 4h: ultra-endurance extrapolation
]

MIN_ACTIVITY_DURATION_MIN: float = 10.0  # ignore efforts < 10 min
MAX_ACTIVITY_DURATION_MIN: float = 240.0  # ignore efforts > 4 h


def estimate_max_hr(age: int) -> int:
    """Estimate maximum heart rate using the Tanaka formula.

    Parameters
    ----------
    age : int
        Athlete age in years.

    Returns
    -------
    int
        Estimated maximum heart rate in BPM.

    """
    return round(208 - (0.7 * age))


def estimate_anaerobic_threshold_hr(e_max_hr: int) -> int:
    """Estimate anaerobic threshold heart rate (LTHR).

    Parameters
    ----------
    e_max_hr : int
        Effective maximum heart rate in BPM.

    Returns
    -------
    int
        Estimated LTHR in BPM.

    """
    return round(e_max_hr * 0.85)


def estimate_aerobic_threshold_hr(e_anaerobic_threshold_hr: int, age: int) -> int:
    """Estimate aerobic threshold heart rate (LT1).

    Uses the higher of two estimates:
    - MAF formula: 180 - age
    - LTHR offset: LTHR - 25 BPM

    Parameters
    ----------
    e_anaerobic_threshold_hr : int
        Effective anaerobic threshold HR in BPM.
    age : int
        Athlete age in years.

    Returns
    -------
    int
        Estimated aerobic threshold HR in BPM.

    """
    maf_hr = 180 - age
    lthr_offset_hr = e_anaerobic_threshold_hr - 25
    return max(maf_hr, lthr_offset_hr)


def _power_fraction_of_ftp(duration_min: float) -> float:
    """Interpolate the sustainable power fraction of FTP for a given duration.

    Parameters
    ----------
    duration_min : float
        Activity duration in minutes.

    Returns
    -------
    float
        Expected ratio of average sustainable power to FTP.

    """
    if duration_min <= POWER_DURATION_ANCHORS[0][0]:
        return POWER_DURATION_ANCHORS[0][1]
    if duration_min >= POWER_DURATION_ANCHORS[-1][0]:
        return POWER_DURATION_ANCHORS[-1][1]
    for i in range(len(POWER_DURATION_ANCHORS) - 1):
        t0, f0 = POWER_DURATION_ANCHORS[i]
        t1, f1 = POWER_DURATION_ANCHORS[i + 1]
        if t0 <= duration_min <= t1:
            alpha = (duration_min - t0) / (t1 - t0)
            return f0 + alpha * (f1 - f0)
    return POWER_DURATION_ANCHORS[-1][1]


def estimate_ftp_from_activities(
    activities: list[entities.ActivityEntity],
) -> float:
    """Estimate FTP using a unified power-duration model across all activities.

    For every qualifying activity (has avg_watts > 0, duration 10–240 min), a FTP
    candidate is derived by scaling avg_watts by the inverse of the power-duration
    fraction at that effort length. The best (highest) candidate is returned.

    A 20-min effort at X W produces X / 1.053 ≈ X × 0.95 — identical to the
    classic field-test formula. A 2.5-hour effort at Y W produces Y / 0.785,
    correctly scaling up to a FTP estimate.

    Parameters
    ----------
    activities : list[entities.ActivityEntity]
        All athlete activities. Only activities with avg_watts > 0 and duration
        within [10, 240] minutes are considered.

    Returns
    -------
    float
        Best FTP estimate in Watts, or 0.0 if no qualifying activity exists.

    """
    best_ftp = 0.0
    for activity in activities:
        if activity.avg_watts <= 0:
            continue
        duration_min = (
            activity.hours * 60.0 + activity.minutes + activity.seconds / 60.0
        )
        if duration_min < MIN_ACTIVITY_DURATION_MIN:
            continue
        if duration_min > MAX_ACTIVITY_DURATION_MIN:
            continue
        fraction = _power_fraction_of_ftp(duration_min)
        ftp_candidate = activity.avg_watts / fraction
        if ftp_candidate > best_ftp:
            best_ftp = ftp_candidate
    return round(best_ftp, 1) if best_ftp > 0 else 0.0


def estimate_vo2max(e_max_hr: int, rest_hr: int = REST_HR_DEFAULT) -> float:
    """Estimate VO2 Max using the Uth-Sorensen-Overgaard-Pedersen formula.

    Parameters
    ----------
    e_max_hr : int
        Effective maximum heart rate in BPM.
    rest_hr : int
        Resting heart rate in BPM. Defaults to 60 BPM for active people.

    Returns
    -------
    float
        Estimated VO2 Max in mL/kg/min.

    """
    if rest_hr <= 0:
        rest_hr = REST_HR_DEFAULT
    return round(15.3 * (e_max_hr / rest_hr), 1)


def estimate_hrv_rmssd(age: int) -> float:
    """Estimate overnight HRV RMSSD using age-regression.

    Parameters
    ----------
    age : int
        Athlete age in years.

    Returns
    -------
    float
        Estimated RMSSD in milliseconds (population average baseline).

    """
    return round(max(0.0, 80 - (0.9 * age)), 1)


def estimate_fat_max(weight_kg: float) -> float:
    """Estimate FatMax (peak fat oxidation rate) based on body weight.

    Parameters
    ----------
    weight_kg : float
        Athlete body weight in kilograms.

    Returns
    -------
    float
        Estimated FatMax in grams per hour.

    """
    if weight_kg <= 0:
        return 0.0
    return round(weight_kg * 0.45, 1)


def derive_power_to_weight(e_ftp: float, weight_kg: float) -> float:
    """Derive power-to-weight ratio.

    Parameters
    ----------
    e_ftp : float
        Effective FTP in Watts.
    weight_kg : float
        Athlete body weight in kilograms.

    Returns
    -------
    float
        Power-to-weight ratio in W/kg, or 0.0 if inputs are invalid.

    """
    if e_ftp <= 0 or weight_kg <= 0:
        return 0.0
    return round(e_ftp / weight_kg, 2)


def estimate_pmax_from_activities(
    activities: list[entities.ActivityEntity],
    fallback_cp_watts: float,
) -> float:
    """Estimate Pmax from activity max power values.

    Parameters
    ----------
    activities : list[entities.ActivityEntity]
        Activities used to estimate maximal power.
    fallback_cp_watts : float
        Effective CP fallback used to keep Pmax > CP.

    Returns
    -------
    float
        Estimated Pmax in watts.
    """
    max_observed = 0.0
    for activity in activities:
        max_watts = getattr(activity, "max_watts", 0.0)
        if not isinstance(max_watts, (int, float)):
            continue
        if max_watts > max_observed:
            max_observed = float(max_watts)

    if max_observed > 0:
        return max(
            max_observed,
            fallback_cp_watts * 1.1,
            irm3d_metrics.DEFAULT_MIN_PMAX_WATTS,
        )

    return max(
        fallback_cp_watts * irm3d_metrics.DEFAULT_PMAX_MULTIPLIER,
        irm3d_metrics.DEFAULT_MIN_PMAX_WATTS,
    )


def calculate_zones(
    e_anaerobic_threshold_hr: int, e_max_hr: int
) -> list[tuple[int, int]]:
    """Calculate HR zone boundaries from LTHR (estimated path).

    Parameters
    ----------
    e_anaerobic_threshold_hr : int
        Effective LTHR (anaerobic threshold heart rate) in BPM.
    e_max_hr : int
        Effective maximum heart rate in BPM.

    Returns
    -------
    list[tuple[int, int]]
        List of 5 (low, high) BPM tuples for zones Z1–Z5.

    """
    lthr = e_anaerobic_threshold_hr
    zones = []
    for low_pct, high_pct in ZONE_BOUNDARIES:
        low = round(lthr * low_pct) if low_pct > 0 else 0
        high = round(lthr * high_pct) if high_pct is not None else e_max_hr
        zones.append((low, high))
    return zones


def calculate_power_zones(e_ftp: float) -> list[tuple[int, int]]:
    """Calculate power zone boundaries from FTP (Coggan 7-zone model).

    Parameters
    ----------
    e_ftp : float
        Effective FTP (Functional Threshold Power) in watts.

    Returns
    -------
    list[tuple[int, int]]
        List of 7 (low, high) watt tuples for zones PZ1–PZ7.

    """
    zones = []
    for low_pct, high_pct in POWER_ZONE_BOUNDARIES:
        low = round(e_ftp * low_pct) if low_pct > 0 else 0
        high = round(e_ftp * high_pct) if high_pct is not None else 100000
        zones.append((low, high))
    return zones


def resolve_zones(
    athlete_metrics: "app_settings.AthleteMetrics",
) -> None:
    """Resolve e_z* zone boundaries in-place on athlete_metrics.

    Uses athlete-set z{n}_high values when all four are set (> 0);
    falls back to LTHR-based estimation otherwise.

    Parameters
    ----------
    athlete_metrics : app_settings.AthleteMetrics
        The metrics object whose zone fields are populated in-place.
        Requires e_anaerobic_threshold_hr and e_max_hr to be resolved first.

    """
    zones_set = (
        athlete_metrics.z1_high > 0
        and athlete_metrics.z2_high > 0
        and athlete_metrics.z3_high > 0
        and athlete_metrics.z4_high > 0
    )

    if zones_set:
        athlete_metrics.e_z1_low = 0
        athlete_metrics.e_z1_high = athlete_metrics.z1_high
        athlete_metrics.e_z2_low = athlete_metrics.z1_high + 1
        athlete_metrics.e_z2_high = athlete_metrics.z2_high
        athlete_metrics.e_z3_low = athlete_metrics.z2_high + 1
        athlete_metrics.e_z3_high = athlete_metrics.z3_high
        athlete_metrics.e_z4_low = athlete_metrics.z3_high + 1
        athlete_metrics.e_z4_high = athlete_metrics.z4_high
        athlete_metrics.e_z5_low = athlete_metrics.z4_high + 1
        athlete_metrics.e_z5_high = athlete_metrics.e_max_hr
    else:
        zones = calculate_zones(
            athlete_metrics.e_anaerobic_threshold_hr,
            athlete_metrics.e_max_hr,
        )
        athlete_metrics.e_z1_low, athlete_metrics.e_z1_high = zones[0]
        athlete_metrics.e_z2_low, athlete_metrics.e_z2_high = zones[1]
        athlete_metrics.e_z3_low, athlete_metrics.e_z3_high = zones[2]
        athlete_metrics.e_z4_low, athlete_metrics.e_z4_high = zones[3]
        athlete_metrics.e_z5_low, athlete_metrics.e_z5_high = zones[4]


def resolve_power_zones(
    athlete_metrics: "app_settings.AthleteMetrics",
) -> None:
    """Resolve e_pz* power zone boundaries in-place on athlete_metrics.

    Uses athlete-set pz{n}_high values when all seven are set (> 0);
    falls back to FTP-based estimation otherwise.

    Parameters
    ----------
    athlete_metrics : app_settings.AthleteMetrics
        The metrics object whose power zone fields are populated in-place.
        Requires e_ftp to be resolved first.

    """
    power_zones_set = (
        athlete_metrics.pz1_high > 0
        and athlete_metrics.pz2_high > 0
        and athlete_metrics.pz3_high > 0
        and athlete_metrics.pz4_high > 0
        and athlete_metrics.pz5_high > 0
        and athlete_metrics.pz6_high > 0
        and athlete_metrics.pz7_high > 0
    )

    if power_zones_set and athlete_metrics.e_ftp > 0:
        athlete_metrics.e_pz1_low = 0
        athlete_metrics.e_pz1_high = athlete_metrics.pz1_high
        athlete_metrics.e_pz2_low = athlete_metrics.pz1_high + 1
        athlete_metrics.e_pz2_high = athlete_metrics.pz2_high
        athlete_metrics.e_pz3_low = athlete_metrics.pz2_high + 1
        athlete_metrics.e_pz3_high = athlete_metrics.pz3_high
        athlete_metrics.e_pz4_low = athlete_metrics.pz3_high + 1
        athlete_metrics.e_pz4_high = athlete_metrics.pz4_high
        athlete_metrics.e_pz5_low = athlete_metrics.pz4_high + 1
        athlete_metrics.e_pz5_high = athlete_metrics.pz5_high
        athlete_metrics.e_pz6_low = athlete_metrics.pz5_high + 1
        athlete_metrics.e_pz6_high = athlete_metrics.pz6_high
        athlete_metrics.e_pz7_low = athlete_metrics.pz6_high + 1
        athlete_metrics.e_pz7_high = athlete_metrics.pz7_high
    elif athlete_metrics.e_ftp > 0:
        zones = calculate_power_zones(athlete_metrics.e_ftp)
        athlete_metrics.e_pz1_low, athlete_metrics.e_pz1_high = zones[0]
        athlete_metrics.e_pz2_low, athlete_metrics.e_pz2_high = zones[1]
        athlete_metrics.e_pz3_low, athlete_metrics.e_pz3_high = zones[2]
        athlete_metrics.e_pz4_low, athlete_metrics.e_pz4_high = zones[3]
        athlete_metrics.e_pz5_low, athlete_metrics.e_pz5_high = zones[4]
        athlete_metrics.e_pz6_low, athlete_metrics.e_pz6_high = zones[5]
        athlete_metrics.e_pz7_low, athlete_metrics.e_pz7_high = zones[6]


def resolve(
    athlete_metrics: "app_settings.AthleteMetrics",
    user_profile: "app_settings.UserProfile",
    activities: list[entities.ActivityEntity],
    weight_kg: float = 0.0,
    rest_hr: int = 0,
) -> None:
    """Resolve all e_* fields on AthleteMetrics in-place.

    Populates every effective (e_*) field and HR zone boundary using
    athlete-set values where available, falling back to estimates otherwise.

    Parameters
    ----------
    athlete_metrics : app_settings.AthleteMetrics
        The metrics object to populate in-place.
    user_profile : app_settings.UserProfile
        User profile providing age.
    activities : list[entities.ActivityEntity]
        All athlete activities for FTP estimation.
    weight_kg : float
        Current athlete body weight in kg (from last activity or profile).
    rest_hr : int
        Resting heart rate in BPM (0 if unknown).  Passed through to
        :func:`estimate_vo2max` for the Uth-Sorensen-Overgaard-Pedersen
        formula; falls back to :data:`REST_HR_DEFAULT` when 0.

    """
    age = user_profile.age or app_settings.UserProfile.DEFAULT_AGE

    # --- max HR ---
    athlete_metrics.e_max_hr = (
        athlete_metrics.max_hr if athlete_metrics.max_hr > 0 else estimate_max_hr(age)
    )

    # --- anaerobic threshold HR (LTHR) ---
    athlete_metrics.e_anaerobic_threshold_hr = (
        athlete_metrics.anaerobic_threshold_hr
        if athlete_metrics.anaerobic_threshold_hr > 0
        else estimate_anaerobic_threshold_hr(athlete_metrics.e_max_hr)
    )

    # --- aerobic threshold HR (LT1) ---
    athlete_metrics.e_aerobic_threshold_hr = (
        athlete_metrics.aerobic_threshold_hr
        if athlete_metrics.aerobic_threshold_hr > 0
        else estimate_aerobic_threshold_hr(
            athlete_metrics.e_anaerobic_threshold_hr, age
        )
    )

    # --- FTP ---
    if athlete_metrics.ftp > 0:
        athlete_metrics.e_ftp = athlete_metrics.ftp
    elif athlete_metrics.e_ftp > 0:
        # already estimated in a prior request — skip expensive scan
        pass
    else:
        athlete_metrics.e_ftp = estimate_ftp_from_activities(activities)

    # --- 3D IRM parameters ---
    athlete_metrics.e_critical_power = (
        athlete_metrics.critical_power
        if athlete_metrics.critical_power > 0
        else athlete_metrics.e_ftp
    )
    athlete_metrics.e_w_prime_joules = (
        athlete_metrics.w_prime_joules
        if athlete_metrics.w_prime_joules > 0
        else irm3d_metrics.DEFAULT_W_PRIME_JOULES
    )
    if athlete_metrics.p_max_watts > 0:
        athlete_metrics.e_p_max_watts = athlete_metrics.p_max_watts
    elif athlete_metrics.e_p_max_watts > 0:
        # already estimated — skip expensive scan
        pass
    else:
        athlete_metrics.e_p_max_watts = estimate_pmax_from_activities(
            activities=activities,
            fallback_cp_watts=athlete_metrics.e_critical_power,
        )
    if athlete_metrics.e_critical_power > 0:
        athlete_metrics.e_p_max_watts = max(
            athlete_metrics.e_p_max_watts,
            athlete_metrics.e_critical_power * 1.1,
        )

    # --- VO2 Max ---
    athlete_metrics.e_vo2max = (
        athlete_metrics.vo2max
        if athlete_metrics.vo2max > 0
        else estimate_vo2max(athlete_metrics.e_max_hr, rest_hr)
    )

    # --- HRV RMSSD ---
    athlete_metrics.e_hrv_rmssd = (
        athlete_metrics.hrv_rmssd
        if athlete_metrics.hrv_rmssd > 0
        else estimate_hrv_rmssd(age)
    )

    # --- FatMax ---
    athlete_metrics.e_fat_max = (
        athlete_metrics.fat_max
        if athlete_metrics.fat_max > 0
        else estimate_fat_max(weight_kg)
    )

    # --- Power-to-Weight (always derived) ---
    athlete_metrics.e_power_to_weight = derive_power_to_weight(
        athlete_metrics.e_ftp, weight_kg
    )

    # --- HR Zones (athlete-set or derived from e_anaerobic_threshold_hr) ---
    resolve_zones(athlete_metrics)

    # --- Power Zones (athlete-set or derived from e_ftp) ---
    resolve_power_zones(athlete_metrics)
