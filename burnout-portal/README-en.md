# Burnout Prevention Portal — Synthetic Data Generator

A **simulation-based dataset** for building a portal that measures stress and sentiment
and provides recommendations to employees and HR. Uses only the standard library — no external dependencies.

```bash
python3 -m generator
```

Outputs three formats simultaneously, followed by a validation report.

| Path | Contents |
|---|---|
| `out/burnout.db` | SQLite, includes views (`v_employee_week`, `v_hr_team_week`) |
| `out/csv/*.csv` | Per-table CSV |
| `out/json/*.json` | Per-table JSON arrays (compact, `ensure_ascii=False`) |
| `out/json/_sample_employee.json` | **52-week full-hierarchy join for a single employee** (pretty print) |

```bash
python3 -m generator --seed 42 --employees 500 --weeks 104
```

| Option | Description |
|---|---|
| `--seed` | Random seed. Same seed = byte-identical dataset |
| `--employees` / `--weeks` | Headcount / duration |
| `--no-anonymous` | Run pulse surveys non-anonymously. Under-reporting bias roughly doubles |
| `--out` | Output directory |

---

## Design Principle: Reverse Generation

Rather than producing observations and inferring stress from them, we **simulate latent
state first and derive observable signals from it**. Knowing the ground truth is essential
for evaluating the scoring models and recommendation engine built on top.

```
Org context ──▶ Persona parameters ──▶ Stress drivers
                                            │
                                            ▼
  What the portal sees ◀── Observable signals ◀── Latent state (ground truth)
  (pulse, text,              (bias & missingness      (exhaustion,
   behavior logs)             injected)                cynicism,
                                                        reduced_efficacy)
```

| File | Layer | Role |
|---|---|---|
| `generator/config.py` | 0 | Simulation config, driver definitions, team specs |
| `generator/org.py` | 0 | Employee assignment, org/team events (reorgs, layoff rumors, crunch, manager changes) |
| `generator/personas.py` | 1 | Parameter vectors for 7 archetypes |
| `generator/dynamics.py` | 2–3 | Driver time-series + latent state dynamics → **ground truth** |
| `generator/signals.py` | 4 | Observable signals + bias & missingness injection |
| `generator/text_en.py` | 4 | Free-text comments (templates + vocabulary variation) |
| `generator/validate.py` | — | Four validation reports |
| `schema.sql` | — | Tables & views. Access boundaries are encoded in the schema |

---

## Stress Determinants (JD-R Model)

**Demands** — what creates burden  
`workload` · `time_pressure` · `role_ambiguity` · `emotional_labor` ·
`context_switching` · `unpredictability`

**Resources** — what buffers against it  
`autonomy` · `support_manager` · `support_peer` · `reward_fairness` ·
`growth_meaning` · `recovery_opportunity`

Autonomy is not a simple resource — it acts as a **moderator of the demand–strain
relationship** (Karasek):

```
strain = (demand_index − resource_index) × (1 − 0.35 × autonomy)
```

## Latent State (Maslach 3 Dimensions)

We do not collapse everything into a single "burnout score". The interventions differ.

| Dimension | Meaning | Intervention |
|---|---|---|
| `exhaustion` | Depletion | Workload rebalancing, recovery time |
| `cynicism` | Detachment / psychological withdrawal | Restore meaning & recognition, fairness |
| `reduced_efficacy` | Loss of confidence | Coaching, role clarification |

Sentiment is a separate axis (`valence` × `arousal`). In late-stage burnout, arousal
actually drops, producing a **low-arousal negative affect (helplessness)** pattern.

## Four Core Dynamics

- **Hysteresis** — Once `exhaustion > 0.70`, the recovery coefficient drops to 45%.
  Once collapsed, recovery does not happen under the same conditions.
- **Scarring (`scar`)** — People who have crashed do not fully return to baseline.
  The floor of exhaustion rises and sensitivity to future load increases. This is a key
  variable for relapse prediction, so it is preserved in `truth_weekly_state.scar`.
- **Event shocks** — Injected at the org/team level to naturally produce team-level correlation.
- **Seasonality** — End-of-quarter pressure, summer vacation season (higher load for those remaining), year-end.

---

## 7 Personas

| Key | Name | Share | Characteristics |
|---|---|---|---|
| `overachiever` | Voluntary overloader | 12% | Self-imposed standards are the cause. **Under-reporting** means surveys catch them late. Acute collapse. |
| `invisible` | Unrecognized contributor | 13% | ERI imbalance. Cynicism comes first. **Highest attrition risk.** |
| `caregiver` | Emotional labor caregiver | 12% | Cumulative emotional labor. Efficacy is maintained. |
| `ambiguous` | Role-ambiguous | 11% | **Counter-example A** — low workload, high stress. |
| `coaster` | Psychologically detached | 7% | **Counter-example B** — burnout with regular hours. 21% response rate. |
| `recovering` | Recovery trajectory | 7% | Starts in a high-risk state, recovers after intervention. Used to validate recommendation effects. |
| `anchored` | Stable | 38% | Healthy majority. Control group that weathers org shocks. |

Personas 4 and 5 are the heart of this dataset. Without them, a naïve model concludes
"overtime hours = burnout" and fails silently in production.

---

## Intentionally Injected 'Messiness'

Clean synthetic data is useless. All of the following are deliberate.

| Phenomenon | Implementation | Effect |
|---|---|---|
| **Informative missingness** | Response probability = `0.90 − 0.50·E − 0.32·C` | Stage 0: 78% response → Stage 3: 20% response. Silence is the strongest signal. |
| **Social desirability bias** | `disclosure_bias`, ×0.55 if anonymous | Overachievers rate `q_energy` +0.5 pts higher even in weeks when they are genuinely exhausted. |
| **Response style** | `central` (midpoint clustering) / `extreme` | Individual comparison is impossible without Likert scale correction. |
| **Proxy betrayal** | `presence_decay`, `overwork_tendency` | Overall correlation of work hours ↔ burnout: r = +0.02. |
| **Unused / cancelled leave** | Remaining days spread over remaining weeks with a cap; 55% cancellation probability during crunch | Stable types use all 15 days; overachievers use 0.8 days and leave 15.3 unused — **unused balance is itself a recovery-failure signal**. |

---

## Validation (printed automatically when running `python3 -m generator`)

```
1. Distribution sanity
  [PASS] Point prevalence (employee-week stage>=2): 20.8%  [target 20–30%]
  [PASS] Annual incidence (stage>=2 at least once): 42.8%
  [PASS] Severe (stage>=3) annual incidence: 14.4%  [reference 5–16%]
  [PASS] Annual attrition rate: 12.0%

2. Known correlations reproduced
  [PASS] Resource index ↔ strain   r = -0.76
  [PASS] Resource index ↔ cynicism r = -0.71
  [PASS] Demand index  ↔ exhaustion r = +0.43
  [PASS] Response rate: stage0=78% stage1=50% stage2=35% stage3=18%
  Under-reporting: overachiever observed 2.70 / expected 2.19 / delta +0.51

4. Naïve baseline failure confirmed
   Overall:          work hours ↔ burnout  r = +0.02
   Role-ambiguous    r = -0.02  ← counter-example
   Psychologically detached  r = -0.04  ← counter-example
```

The severe (stage≥3) annual incidence of 14.4% sits at the top of the reference range.
To lower it, reduce `dim_gain["exhaustion"]` in `personas.py` —
adjusting persona weights will simultaneously break point prevalence.

`peak_stage` is defined as the highest stage sustained for **3 or more consecutive weeks**.
Burnout is a persistent state, not a bad week, and peak statistics over-weight noise.

---

## Privacy Boundaries (built into the schema)

This portal is exactly the kind of tool most easily turned into a surveillance instrument.
Access boundaries are encoded in the **schema**, not in the application layer.

| Target | Access |
|---|---|
| `truth_*` tables | **Model evaluation only.** The operational portal never reads these. |
| `v_employee_week` | Personal view. The application must bind the user's own `employee_id`. |
| `v_hr_team_week` | Team × week aggregates only. **Groups with fewer than 5 respondents return no rows.** |

The moment individual-level burnout scores are exposed to HR, employees stop answering
honestly and the data dies. The `disclosure_bias` parameter simulates exactly that.

---

## Data Volume (default settings)

| Table | Rows | Cadence |
|---|---|---|
| `employee` | 250 | — |
| `truth_weekly_state` | ~12,400 | Weekly (ground truth) |
| `pulse_response` | ~12,400 | Weekly (~65% actually respond) |
| `pulse_comment` | ~2,500 | Biweekly, low response rate |
| `behavior_daily` | ~86,600 | Daily |
| `weekly_signal` | ~12,400 | Weekly |
| `enps_response` | ~940 | Quarterly |

---

## Example Queries

```sql
-- Persona profiles (ground truth)
SELECT t.persona_name_ko, COUNT(DISTINCT t.employee_id) n,
       ROUND(AVG(s.exhaustion),2) exhaustion, ROUND(AVG(s.cynicism),2) cynicism,
       ROUND(AVG(s.reduced_efficacy),2) reduced_efficacy
FROM truth_employee t JOIN truth_weekly_state s USING(employee_id)
GROUP BY t.persona_key ORDER BY exhaustion DESC;
```

```sql
-- Which signals move first in the 8 weeks before attrition?
SELECT s.weeks_to_attrition,
       ROUND(AVG(s.cynicism),2) cynicism, ROUND(AVG(p.responded),2) response_rate,
       ROUND(AVG(w.one_on_one_attended),2) one_on_one_attended
FROM truth_weekly_state s
JOIN pulse_response p USING(employee_id, week)
JOIN weekly_signal  w USING(employee_id, week)
WHERE s.weeks_to_attrition BETWEEN 0 AND 12
GROUP BY s.weeks_to_attrition ORDER BY s.weeks_to_attrition DESC;
```

```sql
-- Recommendation engine ground truth: active drivers for a given person right now
SELECT employee_id, week, burnout_stage, top_drivers
FROM truth_weekly_state WHERE burnout_stage >= 2 LIMIT 20;
```

---

## Next Steps

1. **Scoring model** — Recover the 3-dimensional latent state from observable signals only. Score against `truth_weekly_state`.
2. **Recommendation engine** — Map estimated drivers to interventions. `top_drivers` is the answer key.
3. **Portal UI** — Personal view / HR aggregate view. Access boundaries are already in the schema.

One rule when building models: **never use `truth_*` columns as features in training or evaluation.**
Using the answer key as a feature makes the entire validation meaningless.
