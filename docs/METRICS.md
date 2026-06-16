# Athlete Metrics

MyTraL tracks a set of athlete-level performance metrics that serve as personal benchmarks for zone calculations, analytics, and progress tracking. Each metric can either be **set** (measured by you) or **estimated** automatically from your age, weight, and activity data.

Access your metrics at **Progress -> Athlete Metrics** or edit them via **Progress -> Athlete Metrics -> Edit**.


## Set vs. Estimated Metrics

Every metric falls into one of three categories:

  * Measured -- Value you entered after a proper field or lab test. Used as-is for all calculations.
  * Estimated -- Automatically computed from your age, weight, or activity data when no measured value is available.
  * Derived -- Always computed at runtime and never stored (e.g., Power-to-Weight).

To override an estimate, enter your measured value in the edit form. Set any field to 0 (or leave blank) to revert to the automatic estimate.

## Automatic Estimation Flow

When you save the edit form without specifying any metric values, MyTraL persists `0`
for all athlete-set fields and resolves all effective `e_*` metrics at runtime.

```text
┌───────────────────────────────────────────────────────────┐
│ Edit Athlete Metrics form                                 │
│ - user leaves all fields blank (or enters 0)              │
└───────────────────────────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────┐
│ On Save (/athlete/metrics/update, POST)                   │
│ - all persisted metric fields become 0                    │
└───────────────────────────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────┐
│ On View (/athlete/metrics, GET)                           │
│ - load user profile + all activities                      │
│ - resolve latest weight from activities (if available)    │
└───────────────────────────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────┐
│ athlete_metrics.resolve(...) computes effective values    │
│                                                           │
│ age = user_profile.age or default age                     │
│ e_max_hr                  = round(208 - 0.7 * age)        │
│ e_anaerobic_threshold_hr  = round(e_max_hr * 0.85)        │
│ e_aerobic_threshold_hr    = max(180 - age, LTHR - 25)     │
│ e_ftp                     = from power activities         │
│                             (10..240 min, max candidate)  │
│ e_vo2max                  = 15.3 * (e_max_hr / 60)        │
│ e_hrv_rmssd               = max(0, 80 - 0.9 * age)        │
│ e_fat_max                 = weight_kg * 0.45 (or 0)       │
│ e_power_to_weight         = e_ftp / weight_kg (or 0)      │
└───────────────────────────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────┐
│ Zone resolution                                           │
│ - HR zones: if any Z1..Z4 boundary missing, estimate      │
│   all HR zones from LTHR percentages                      │
│ - Power zones: if boundaries missing, estimate from FTP   │
│   (when e_ftp > 0)                                        │
└───────────────────────────────────────────────────────────┘
```

## Performance Thresholds

## Max Heart Rate (Max HR)

The highest heart rate you can achieve during maximum effort exercise, measured in BPM. Measured via a maximum-effort field test or treadmill stress test. **Estimation:** Tanaka formula -- `208 - (0.7 × age)`.

### Anaerobic Threshold HR (LTHR)

The heart rate at your lactate threshold (second lactate threshold / LT2), also called LTHR (Lactate Threshold Heart Rate). This is the highest sustainable intensity for prolonged efforts and is the primary anchor for HR zone calculations. Measured as the average heart rate during the final 20 minutes of a 30-minute all-out time trial. **Estimation:** `round(Max HR × 0.85)`.

### Aerobic Threshold HR (LT1)

The heart rate at the first lactate threshold (LT1) -- the upper boundary of easy, fat-burning aerobic work. Training below LT1 builds aerobic base without accumulating fatigue. Measured in a lab via lactate testing, or approximated via a MAF test. **Estimation:** `max(180 - age, LTHR - 25)`.

## Heart Rate Zones

MyTraL uses a 5-zone HR model anchored to LTHR. You can either let MyTraL calculate zones automatically or enter your own zone boundaries. To use custom zones, all four boundary values (Z1-Z4 upper bounds) must be set; any single missing value reverts all zones to the estimated model.

Zone | Name | Intensity | Estimated boundary (LTHR-based)
---|---|---|---
Z1| Recovery| Very easy | < LTHR × 0.85
Z2| Aerobic| Easy-moderate | LTHR × 0.85 - 0.90
Z3| Tempo| Moderate | LTHR × 0.90 - 0.95
Z4| Threshold| Hard | LTHR × 0.95 - 1.06
Z5| Anaerobic| Maximum | ≥ LTHR × 1.06

## FTP & Power

### Functional Threshold Power (FTP)

The highest average power you can sustain for one hour, measured in Watts. Measured as 95% of your average power in a 20-minute all-out effort, or directly from a 60-minute field test. **Estimation:** Derived from activity power data using a duration-scaled model (see FTP Model below).

### Power Zones

MyTraL uses the Coggan 7-zone model for power, anchored to your FTP.

Zone | Name | Intensity | Estimated boundary (FTP-based)
---|---|---|---
PZ1| Recovery| Active recovery | < FTP × 0.61
PZ2| Endurance| Aerobic base | FTP × 0.61 - 0.83
PZ3| Tempo| Intensive aerobic | FTP × 0.83 - 1.00
PZ4| Threshold| Lactate threshold | FTP × 1.00 - 1.17
PZ5| VO2Max| Aerobic capacity | FTP × 1.17 - 1.33
PZ6| Anaerobic| Anaerobic capacity | FTP × 1.33 - 1.67
PZ7| Neuromuscular| Sprints / Maximum | ≥ FTP × 1.67

### Power-to-Weight Ratio (W/kg)

Always derived: `eFTP / body weight (kg)`. Never stored; always recalculated from your current FTP and body weight.

## FTP Estimation Model

When no FTP is set, MyTraL estimates it from activities with recorded power (avg_watts > 0) and duration between 10 and 240 minutes. For each qualifying activity the algorithm computes:
[code]
    ftp_candidate = avg_watts / power_fraction(duration_minutes)
[/code]

The _power fraction_ is interpolated from the following anchors (fraction = proportion of FTP an athlete can hold for that duration):

Duration (min)| Fraction of FTP
---|---
10| 1.150
20| 1.053
60| 1.000
90| 0.900
120| 0.850
150| 0.785
240| 0.720

The highest FTP candidate across all qualifying activities is used. Activities shorter than 10 min or longer than 240 min are excluded.

## Banister Fitness-Fatigue-Performance Model

MyTraL implements the Banister systems model for predicting performance from
training load. See the dedicated [Banister Model documentation](METRICS.banister.md)
for the full mathematical model, performance zones, and per-activity analysis.

## Advanced Metrics

### VO2 Max

Maximal oxygen uptake in mL/kg/min -- the gold standard for aerobic fitness. Measured in a laboratory via a graded exercise test with gas analysis. **Estimation:** Uth-Sørensen formula: `15.3 × (Max HR / Rest HR)` (rest HR defaults to 60 BPM if not available from activities).

### HRV RMSSD

Heart Rate Variability -- Root Mean Square of Successive Differences, in ms. Higher values generally indicate better recovery and parasympathetic activity. Measured each morning before rising using an HRV app and a chest strap or compatible wrist sensor. **Estimation:** Population average baseline: `80 - (0.9 × age)`.

### FatMax

Maximum fat oxidation rate in g/hr -- the highest rate at which your body burns fat for fuel. Measured via metabolic cart testing (indirect calorimetry). **Estimation:** Body weight × 0.45 g/hr. Requires body weight data from at least one activity.

## How to Set Your Metrics

  1. Go to **Profile -> Athlete Metrics**.
  2. Click **Edit**.
  3. Enter only the values you have measured. Leave unused fields blank or at 0 to let MyTraL estimate them automatically.
  4. Click **Save Metrics**.

Metrics are re-resolved every time you view the Athlete Metrics page, so estimates update automatically as you log more activities.
