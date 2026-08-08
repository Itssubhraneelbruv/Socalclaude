# `jimmy_week.json` — schema reference

Single-file dataset: one office worker ("Jimmy"), one week, wearable + room environment
+ self-report. **Synthetic.** 6.1 MB, 10,080 minute records, **zero missing values** —
every field in every record is populated, so no null handling is required.

---

## 1. Read this first

**Load only what you need.** The file is layered by resolution:

| Key | Size | Use when |
|---|---|---|
| `metadata` | <1 KB | Always |
| `ieq_targets` | <1 KB | Recommending environmental changes |
| `week_summary` | 1.7 KB | Answering "how was the week" |
| `daily` | 6.9 KB | Day-level reasoning, trends, EMA text |
| `minutes` | 6.0 MB | Charts, recomputation, within-day patterns |

`metadata` + `ieq_targets` + `week_summary` + `daily` total **under 10 KB** and fit in
any context window. **Do not load `minutes` into a prompt** — subset or aggregate it in
code first.

```python
import json
d = json.load(open("jimmy_week.json"))
context = {k: d[k] for k in ("metadata", "ieq_targets", "week_summary", "daily")}
```

**Everything in `daily` and `week_summary` is already derived from `minutes`.** Don't
recompute means that are sitting there; do use `minutes` for anything not precomputed.

---

## 2. `metadata`

```json
{"participant_full_id": "1109-1-1-JIMMY01", "display_name": "Jimmy",
 "period_start": "2026-08-03", "period_end": "2026-08-09",
 "sampling_interval": "1 minute", "core_shift": "09:00-17:00, Mon-Fri",
 "records": {"days": 7, "minutes": 10080, "ema_responses": 10, "missing_values": 0},
 "data_type": "synthetic"}
```

Period is Mon 2026-08-03 → Sun 2026-08-09. Timestamps are **local wall-clock strings**,
format `YYYY-MM-DD HH:MM`. No timezone offset, no UTC conversion needed. Sort
lexicographically or parse with `%Y-%m-%d %H:%M`.

---

## 3. `minutes` — array of 10,080 records

One record per minute, chronological, wearable and room merged onto the same row.
No joins needed. Index `i` corresponds to day `i // 1440`, minute-of-day `i % 1440`.

### Wearable fields

| Field | Unit | Observed range | Meaning |
|---|---|---|---|
| `pulse_rate_bpm` | bpm | 56 – 125 | Heart rate from PPG |
| `prv_rmssd_ms` | ms | 5.0 – 42.3 | Pulse rate variability (RMSSD). **Higher = more recovered.** Primary stress marker |
| `eda_scl_usiemens` | µS | 0.07 – 5.71 | Skin conductance level. Sympathetic arousal |
| `respiratory_rate_brpm` | breaths/min | 11.1 – 24.7 | Respiration rate |
| `temperature_celsius` | °C | 32.98 – 34.65 | **Wrist skin** temperature, not ambient |
| `met` | ratio | 0.9 – 4.99 | Metabolic equivalent. 1.0 ≈ rest, >3.0 moderate |
| `step_counts` | steps/min | 0 – 158 | Steps in that minute |
| `activity_counts` | count | 0 – 3689 | Aggregate movement magnitude |
| `accelerometers_std_g` | g | 0.004 – 0.497 | SD of acceleration; movement variability |
| `activity_class` | enum | `still`, `walking`, `generic` | Movement label |
| `activity_intensity` | enum | `sedentary`, `LPA`, `MPA` | Light / moderate physical activity |
| `sleep_detection_stage` | enum | `0`, `101`, `102` | **`0` = awake. `101` and `102` are both sleep** |
| `wearing_detection_percentage` | % | 94.8 – 100.0 | Wear confidence |

### Environment fields (same row)

| Field | Unit | Observed range | Meaning |
|---|---|---|---|
| `co2_ppm` | ppm | 302 – 2323 | CO₂. Ventilation proxy; >1000 impairs cognition |
| `sound_level_dba` | dBA | 28.0 – 87.1 | A-weighted sound pressure level |
| `illuminance_lux` | lux | 4 – 881 | Light at the workplane |
| `color_temp_kelvin` | K | 4034 – 5547 | Light colour temperature. Higher = cooler/bluer/more alerting |
| `air_temperature_celsius` | °C | 21.12 – 28.55 | **Room air** temperature |
| `relative_humidity_pct` | % | 15.8 – 42.3 | Relative humidity |

### Two traps

1. **`temperature_celsius` (skin, ~33 °C) vs `air_temperature_celsius` (room, ~25 °C)**
   are different sensors. Never plot on one axis or compare directly.
2. **Sleep is `stage != 0`**, not `stage == 1`. Counts: 7,825 awake / 1,322 stage-101 /
   933 stage-102.

Outside 07:00–20:00 the room is empty, so environment values drop to empty-room levels
(CO₂ ~450, ~34 dBA, ~4 lux). These are **real readings of an unoccupied room, not
sentinels** — filter to core hours before averaging environment.

---

## 4. `daily` — array of 7 records

```
date, weekday, is_workday,
physiology:            sleep_duration_h, night_rmssd_ms, sleeping_pulse_rate_bpm,
                       work_eda_usiemens, work_pulse_rate_bpm,
                       work_respiratory_rate_brpm, daily_steps
behaviour:             micro_breaks_core_hours, sedentary_minutes_core_hours,
                       after_hours_work_minutes
environment_core_hours: co2_ppm_mean, co2_ppm_peak, sound_level_dba_mean,
                       illuminance_lux_mean, color_temp_kelvin_mean,
                       air_temperature_celsius_mean, relative_humidity_pct_mean
coupling:              co2_vs_eda_r_core_hours, sound_vs_pulse_r_core_hours
ema:                   {pre_shift, post_shift}  — null on Sat/Sun
```

Derivation rules:
- `night_*` = mean over minutes where `sleep_detection_stage != 0`
- `work_*` and `*_core_hours` = 09:00–17:00 only
- `micro_breaks_core_hours` = count of **contiguous walking bouts** in core hours, not
  walking minutes
- `after_hours_work_minutes` = sedentary awake work-pattern minutes after 20:00
- `coupling` = Pearson *r* across the 480 core-hour minutes of that day

### `ema` — self-report, Mon–Fri only

`ema` is **`null` on Saturday and Sunday.** Guard for it.

**`pre_shift`** (~09:00): `energy_1_7` (1 = depleted, 7 = energised) ·
`sleep_quality_1_5` (1 = terrible, 5 = excellent) · `workload_expected_1_7` (7 = highest
demand) · `appraisal` (`challenge` | `threat` | `neutral`)

**`post_shift`** (~17:00): `fatigue_1_7` (7 = most exhausted) · `stress_1_7` (7 = most
stressed) · `detachment_difficulty_1_7` (7 = cannot switch off; Need-for-Recovery core
item) · `free_text` (open response, 1–2 sentences)

**Scale directions are not uniform.** `energy` and `sleep_quality` are *higher = better*;
`fatigue`, `stress`, `detachment_difficulty`, `workload_expected` are *higher = worse*.
`sleep_quality` is 1–5; everything else is 1–7.

---

## 5. `week_summary` and `ieq_targets`

`week_summary` holds precomputed headline comparisons: `night_rmssd_ms` (Mon/Fri/Sun +
`pct_change_mon_to_fri`), `sleeping_pulse_rate_bpm`, `sleep_duration_h`, `micro_breaks`,
`after_hours_work_minutes_total`, plus two composite objects:

- **`recovery_return`** — `{monday_baseline_ms, sunday_ms, returned: bool}`. Whether
  Monday's overnight RMSSD baseline is restored after the weekend. This is the single
  most important field in the file.
- **`self_report_ceiling`** — flags that `fatigue` and `detachment` both hit 7/7 while
  physiology continues to decline.

`ieq_targets` gives each environment parameter as `{target, measured_week_mean}`:

| Parameter | Target | Measured |
|---|---|---|
| `co2_ppm` | <800 | 1540 |
| `sound_level_dba` | ~45 steady | 65.2 |
| `illuminance_lux` | ~100 task-level | 749 |
| `color_temp_kelvin` | ~3000 | 5199 |
| `air_temperature_celsius` | 21–23 | ~26.9 |
| `relative_humidity_pct` | 40–60 | ~23.3 |

Every parameter is outside its band, and each maps to a lever: ventilation, acoustic
masking, dimming, warmer colour temperature, setpoint, humidification.

---

## 6. What the data shows

Core shift is 09:00–17:00 all week — the contracted 8 hours never change. Strain arrives
as **encroachment**: after-hours work grows across the week, and Sunday is worked
outright. Total 1,106 after-hours minutes.

- Overnight RMSSD 30.7 → 15.7 ms, **−48.7%** Mon→Fri
- Sleeping pulse rate 62.2 → 75.9 bpm, never returning to Monday's level
- Sleep 6.3h → 4.0h; weekend total 12.08h across two nights
- Micro-breaks 4 → 1, while sedentary core-hour minutes rise
- `recovery_return.returned` is **`false`** — Sunday's 15.7 ms matches Friday's
- Self-report saturates at 7/7 by Friday while physiology keeps falling

Friday `free_text`: *"Running on empty. Have to work Sunday to make the deadline so no
real break, but next week should ease up."* — a prediction of recovery the data does not
support.

---

## 7. Constraints on interpretation

**Synthetic data.** `data_type` is `"synthetic"`. Never present findings as evidence
about a real person or as a validated result.

**One participant, one week.** No population baseline exists here. Every comparison must
be within-person (day vs day, weekday vs weekend), never against norms. Seven days is far
too short to establish a personal baseline in reality — 2–3 weeks is the working minimum.

**Correlation is not causation.** `coupling` values are within-day correlations between
co-occurring signals. `co2_vs_eda_r_core_hours` reaches 0.98 on Friday, which is cleaner
than any real deployment would produce and is an artifact of the generator. The
sound↔pulse correlation (~0.5) is the more plausible figure. Do not describe either as
proof the environment caused the arousal.

**Not a clinical instrument.** These signals index *strain and recovery*, not diagnosis.
Do not output diagnoses, clinical labels, or statements about depression, anxiety, or
burnout as a condition. "Recovery deficit," "elevated strain," and "insufficient
overnight recovery" are the correct register. Burnout is a months-long construct and
cannot be established from one week.

**Participant-facing framing.** Write for Jimmy, not about him for a manager. Avoid
outputs that would function as employer-facing surveillance or performance evidence.

**Actionable output.** When recommending, prefer the environmental levers in
`ieq_targets` and the workload-encroachment pattern in `after_hours_work_minutes` — these
are changeable. Restating physiological numbers back to the user is not a recommendation.
