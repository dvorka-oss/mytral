# Feature Analysis
 Status | Reviewers | Last updated
 --- |  --- |  --- | 
 DONE | @reviewer | YYYY-MM-DD

**Table of contents**

* [Why](#why)
* [Plan](#plan)
* [Functional Requirements](#functional-requirements)
* [Functional Non-requirements](#functional-non-requirements)
* [Technical Requirements](#technical-requirements)
* [Technical Non-requirements](#technical-non-requirements)
* [Design](#design)
* [Appendices](#appendices)
* [References](#references)


# Why
When user installs MyTraL we need to show estimated values
of all functional metrics so that it can be used through
the whole application for various important calculations.

Which metrics are need from athlete to show advanced analytics?

* performance thresholds:
    * max HR
    * ~~rest HR~~
    * anaerobic threshold HR
    * aerobic threshold HR
    * FTP
* zones:
    * Z1: low boundary + high boundary
    * Z2: low boundary + high boundary
    * Z3: low boundary + high boundary
    * Z4: low boundary + high boundary
    * Z5: low boundary + max HR

---

For specific metrics in the athlete profile there are might be two types of values:

1. metric value
2. estimated metric value

For example:

* Max HR and estimated max HR (eMaxHR)
* FTP (based on a test) and estimated FTP (eFTP)
* VO2Max (measured by a lab) and eVO2Max

These metrics are stored in `Account/Athlete` section.

Set (measured) and estimated metric values are resolved as follows:

* `Metric` **set**
    - Set by the athlete 
    - It is authoritative - measured/test-based - value.
* `Metric` **not** set
    - In this case MyTraL attempts to **estimate** the value.
    - View pages: 
        - `Metric` field is hidden
        - `eMetric` label is shown instead
          w/ "Estimated value" explanation behind (i) or star.

How does it work internally? For instance for FTP?

* Activity has the following fields:
    - `FTP`
    - `eFTP`
* `eFTP` is **always** initialized
    - **Never** set by athlete, it cannot be edited in MyTraL,
    - Either it contains `FTP` value copy
      OR it is estimated value
* Calculations:
    - MyTraL calculations always work w/ `eFTP` value 
      (always set to the best available value)
* UI:
    - View pages: 
        - Either `FTP` or `eFTP` (w/ these labels) is shown,
          both values are never shown together.
    - Edit pages:
        - `FTP` metrics is always shown (`eFTP` is never shown).

---

Zone estimates:

* **Zone 1:** $< 85\%$ of LTHR ($0$ to $144\text{ BPM}$)
* **Zone 2:** $85\%$ to $89\%$ of LTHR ($145$ to $152\text{ BPM}$)
* **Zone 3:** $90\%$ to $94\%$ of LTHR ($153$ to $161\text{ BPM}$)
* **Zone 4:** $95\%$ to $105\%$ of LTHR ($162$ to $179\text{ BPM}$)
* **Zone 5:** $> 105\%$ of LTHR ($180\text{ BPM}+$)

---

HR max:

* **estimate**: by Tanaka: $$\text{HR}_{\max} = 208 - (0.7 \times \text{Age})$$

* **estimate**: simple: $220 - \text{Age}$

---

FTP (Functional Threshold Power) estimates:

* $$\text{Estimated FTP} = \text{Average Power over 20 mins} \times 0.95$$

Hints:

* **estimate**: 2.5 hours is typically about $75\%$ to $82\%$ of their 1-hour FTP.

* **estimate**: $\text{Anaerobic Threshold} \approx \text{HR}_{\max} \times 0.85$

GPX trick:

* zoom in on the data and look for your peak, continuous 20-minute window from either of those rides (usually found on a long climb or a fast flat section).
Take the average power of that specific 20-minute block, multiply it by $0.95$, and you will have a highly reliable estimate of your FTP!

---

Aerobic Threshold (LT1)

This is your "redline"—the **maximum effort you can sustain for about 40 to 60** minutes before your muscles fill with acid and you are forced to slow down.

GPX trick:

* Run or cycle completely solo, all-out, for 30 minutes. Your average heart rate over the final 20 minutes of that effort is a highly accurate estimate of your LTHR.


---

**Anaerobic Threshold (LT2 / FTP)**

This is your "all-day pace"—the limit of your purely aerobic system. Below this point, you are burning almost entirely fat, your breathing is easy, and you can comfortably hold a conversation. Above it, your body begins to gradually accumulate lactate and rely more heavily on carbohydrates.

* **estimate**: 180 - age (MAF formula - Maximum Aerobic Function)

* **estimate**: For most moderately-trained athletes, your Aerobic Threshold lies at roughly $75\%$ to $80\%$ of your FTP.

* **estimate**: Your Aerobic Threshold heart rate is usually $20$ to $30\text{ BPM}$ lower than your Anaerobic Threshold (LTHR).



## All metrics to add to MyTraL
To elevate basic zone-tracking to **advanced sports analytics** (the kind used by platforms like TrainingPeaks, WKO5, intervals.icu, and professional coaches), you need metrics that measure **aerobic capacity, metabolic efficiency, fatigue tracking, and structural physical load**.

Here is a table of the crucial missing metrics, grouped by how they supercharge an athlete's data analysis.

| Metric Name | Abbreviation | Category / What it Measures | Short Description |
| --- | --- | --- | --- |
| **VO2 Max** | $VO_2\text{max}$ | Aerobic Capacity | The maximum volume of oxygen your body can consume per minute per kilogram of body weight ($mL/kg/min$). It defines your absolute aerobic ceiling. |
| **Functional Threshold Pace** | **rFTP / sFTP** | Threshold (Sport Specific) | The maximum flat-ground running pace (or swimming pace) you can sustain for ~45–60 minutes. Essential for calculating pacing zones when GPS/power is highly variable. |
| **Maximal Lactate Steady State** | **MLSS** | Metabolic / Lab-grade | The highest exercise intensity where blood lactate concentration remains constant over time. It is the absolute biological gold-standard of your anaerobic threshold. |
| **VLamax** | $VLa_{\max}$ | Metabolic Capacity | The maximum rate of lactate production. Knowing this tells you if an athlete is an "explosive sprinter" or an "efficient diesel engine"—critical for tailoring training plans. |
| **Heart Rate Variability** | **HRV** | Recovery / Autonomic Nervous System | The variation in time between consecutive heartbeats (usually measured in $ms$ via rMSSD). It tracks systemic nervous system fatigue and readiness to train. |
| **FatMax** | **FatMax** | Fuel Utilization | The specific exercise intensity (usually expressed in Watts or Heart Rate) at which your body burns the maximum amount of fat grams per hour. Vital for ultra-endurance fueling strategies. |
| **Power-to-Weight Ratio** | **W/kg** | Performance Efficiency | Your FTP divided by your body weight in kilograms. The ultimate metric for predicting climbing performance in cycling and running efficiency. |
| **Efficiency Factor** | **EF** | Cardiovascular Efficiency | Calculated as Normalized Power (or Pace) divided by Average Heart Rate. Tracks fitness progress over weeks by showing if you can output more power/speed at the same cardiovascular cost. |
| **Aerobic Decoupling** | **Pa:Hr / Pw:Hr** | Aerobic Endurance | The percentage of "drift" where heart rate rises while power/pace stays constant during a long ride/run. A drift under $5\%$ indicates excellent aerobic conditioning. |
| **Chronic Training Load** | **CTL (Fitness)** | Load / Fatigue Modeling | A rolling 42-day average of daily training stress scores. It represents your current level of physical preparation and "fitness." |
| **Acute Training Load** | **ATL (Fatigue)** | Load / Fatigue Modeling | A rolling 7-day average of daily training stress scores. It represents your short-term fatigue. |
| **Training Stress Balance** | **TSB (Form)** | Performance Readiness | Calculated as $\text{CTL} - \text{ATL}$. A negative score means you are tired but building fitness; a positive score ($+5$ to $+15$) means you are "fresh" and ready to race. |

Why these matter for advanced engines?

While **thresholds and zones** tell you *how to execute a single workout today*, metrics like **CTL/ATL/TSB** tell you *if you are overtraining*, **HRV** tells you *if you should rest*, and **VLamax/VO2 Max** tell you *what kind of athlete you biologically are* so you can design the perfect workout in the first place.

---

When analyzing an athlete using only Age, Weight (kg), and Height (cm), we are attempting to estimate complex biological systems using simple physical dimensions.Because of this, some metrics can be approximated using population-wide regression formulas (like $VO_2\text{max}$ or Power-to-Weight), while other metrics are impossible to estimate because they are entirely dependent on active, ongoing training data (like CTL/ATL/TSB) or raw genetic muscle-fiber makeup (like VLamax).The table below breaks down the unit and the exact estimation methodology (or why it cannot be done) for every advanced metric:

![Image](images/Screenshot%20from%202026-05-09%2015-46-35.png)

![Image](images/Screenshot%20from%202026-05-09%2015-46-51.png)


# Functional Requirements
_[... functional requirements (feature scope) and user stories...]_

**As** ... **I want to** ... **so that** ...

* Acceptance criteria:
    * _[... optional acceptance criteria...]_

**As** ... **I want to** ... **so that** ...

* Acceptance criteria:
    * _[... optional acceptance criteria...]_
# Functional Non-requirements
_[... functional non-requirements within the scope of this feature - what we will not deliver...]_
# Technical Requirements
_[... technical requirements (including security and performance) and user stories (feature scope)...]_

**As** ... **I want to** ... **so that** ...

* _[... optional acceptance criteria...]_

**As** ... **I want to** ... **so that** ...

* _[... optional acceptance criteria...]_
# Technical Non-requirements
_[... technical non-requirements within the scope of this feature - what will not be implemented...]_
# Design
_[... here comes a list of associated design(s) - there can be more than one...]_

Implementation design(s) of this feature:

* [Feature Design](FEATURE_DESIGN.md)
# Appendices
_[... appendice sections...]_

# References
_[... relevant resources...]_

* [resource](http://link.io)


