# Banister Fitness-Fatigue-Performance Model

MyTraL implements the **Banister systems model of training for athletic performance**
(Banister et al., 1975; Busso 1997, 2002) to quantify how your training load
translates into fitness, fatigue, and predicted performance.

Access the model at **Progress -> HR-based progress analytics** and per-activity
at **Activity -> HR-based Analysis**.

## The Model

The Banister model treats your body's response to training as a system of two
first-order low-pass filters with different time constants:

```
fitness(t)  = fitness(t-1) · e^(-1/τ1)  +  w(t) · (1 - e^(-1/τ1))
fatigue(t)  = fatigue(t-1) · e^(-1/τ2)  +  w(t) · (1 - e^(-1/τ2))
performance(t) = k1 · fitness(t) - k2 · fatigue(t)
```

Where:
- **τ1 ≈ 42 days** — fitness time constant (gains accumulate and decay slowly)
- **τ2 ≈ 7 days** — fatigue time constant (accumulates and dissipates quickly)
- **k1 = 1.0** — fitness gain coefficient
- **k2 = 2.0** — fatigue penalty coefficient (fatigue hurts performance ~2× more than fitness helps it)
- **w(t)** — daily TRIMP (Training Impulse) score

## Negative Training Impulse (Busso 2002)

The model credits recovery days: when your daily TRIMP is below the recovery
threshold (25), the model applies a **negative training impulse** that actively
reduces fatigue:

```
w+(t) = max(0, w(t) - 25)     # positive impulse
w-(t) = max(0, 25 - w(t))     # negative impulse (recovery credit)
```

Recovery has faster time constants (τ1' ≈ 14d, τ2' ≈ 3d) and a damped gain
(γ ≈ 0.5), reflecting that rest days help you recover faster than hard days
fatigue you.

## Performance Zones

Your predicted performance p(t) falls into one of four zones:

| Zone         | Performance | Meaning                                           |
|-------------|-------------|---------------------------------------------------|
| Fresh       | > +20       | Ready for a quality session or race               |
| Optimal     | 0 to +20    | Balanced — training is working                    |
| Tired       | -20 to 0    | Fatigued — a deload day would help                |
| Overreached | < -20       | Significantly fatigued — consider a recovery week |

## Programmatic Insights

The model generates six insight cards automatically:

1. **Current State** — your performance zone and what it means
2. **Best Race Form Ever** — the date and conditions of your peak performance
3. **Overreaching Episodes** — detected periods of sustained fatigue
4. **Personal Bests** — fitness PB, race form PB, most tired
5. **Projection** — 56-day forward projection assuming current load pattern
6. **Optimal Race Window** — when performance is projected to cross into positive

## Per-Activity Analysis

Each activity with heart-rate data has an **HR-based Analysis** page showing:

- Pre- and post-activity fitness/fatigue/performance values
- Delta (change) in each metric caused by the activity
- Recovery ETA — days until performance returns to fresh (TSB > 0)
- Benefits, risks, context, and recommendation

## Legacy Metrics

The classic ATRIMP (7d EMA), CTRIMP (42d EMA), and TRIMPB (balance) metrics
are preserved as co-equal KPI cards. They are a special case of the Banister
model with k1 = k2 = 1 and no negative impulse.

## References

- Banister, E.W., Calvert, T.W., Savage, N.V., & Bach, T. (1975). *A systems
  model of training for athletic performance.* Australian Journal of Sports
  Medicine.
- Busso, T., Denis, C., Bonnefoy, R., Geyssant, A., & Lacour, J. R. (1997).
  *Modeling of adaptations to physical training by using a recursive least
  squares algorithm.* Journal of Applied Physiology, 82(5), 1685–1693.
- Busso, T. (2002). *Effects of training frequency on the dynamics of
  performance response to a single training bout.* Journal of Applied
  Physiology, 92(2), 572–580.
