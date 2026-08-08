"""python -m generator [--seed N] [--employees N] [--weeks N] [--out DIR]

전체 파이프라인: 조직 -> 페르소나 -> 드라이버 -> 잠재 상태(정답) -> 관측 신호 -> DB.
"""
from __future__ import annotations

import argparse
import os
import random
from typing import Dict, List

from .config import SimConfig, TEAMS
from .dynamics import simulate_employee
from .emit import write_all
from .org import build_employees, build_events
from .personas import PERSONA_BY_KEY
from .signals import behavior_rows, comment_row, enps_row, pulse_row, weekly_extras
from .validate import report

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 번아웃은 '나쁜 한 주'가 아니라 지속 상태다. 최댓값 통계는 노이즈를 과대평가하므로
# 연속 MIN_SUSTAIN 주 이상 유지된 단계만 그 사람의 도달 단계로 인정한다.
MIN_SUSTAIN = 3


def sustained_peak_stage(stages, min_run: int = MIN_SUSTAIN) -> int:
    for level in (3, 2, 1):
        run = 0
        for s in stages:
            run = run + 1 if s >= level else 0
            if run >= min_run:
                return level
    return 0


def build(cfg: SimConfig) -> Dict[str, List[Dict]]:
    rng = random.Random(cfg.seed)
    employees = build_employees(cfg, rng)
    events = build_events(cfg, random.Random(cfg.seed + 1))

    data: Dict[str, List[Dict]] = {k: [] for k in
                                   ("team", "employee", "org_event", "pulse_response",
                                    "pulse_comment", "behavior_daily", "weekly_signal",
                                    "enps_response", "truth_employee", "truth_weekly_state")}

    headcount: Dict[str, int] = {}
    for e in employees:
        headcount[e.team] = headcount.get(e.team, 0) + 1
    for t in TEAMS:
        data["team"].append({"team_key": t.key, "name": t.name, "department": t.department,
                             "headcount": headcount.get(t.key, 0)})

    for i, e in enumerate(events):
        data["org_event"].append({
            "event_id": i, "event_key": e.key, "label": e.label, "scope": e.scope,
            "team_key": e.team, "start_week": e.start_week, "end_week": e.end_week})

    for idx, emp in enumerate(employees):
        p = PERSONA_BY_KEY[emp.persona]
        erng = random.Random(cfg.seed * 7919 + idx)
        states, attrition_week = simulate_employee(emp, cfg, events, erng)
        if not states:
            continue

        data["employee"].append({
            "employee_id": emp.employee_id, "team_key": emp.team, "department": emp.department,
            "level": emp.level, "tenure_months": emp.tenure_months,
            "is_manager": 1 if emp.is_manager else 0, "hire_week": emp.hire_week,
            "pto_entitlement_days": emp.pto_entitlement_days})

        peak = sustained_peak_stage([s.burnout_stage for s in states])
        weeks_at_risk = sum(1 for s in states if s.burnout_stage >= 2)
        data["truth_employee"].append({
            "employee_id": emp.employee_id, "persona_key": p.key, "persona_name": p.name_en,
            "trajectory": p.trajectory, "attrition_week": attrition_week,
            "peak_stage": peak, "weeks_at_risk": weeks_at_risk})

        for st in states:
            data["truth_weekly_state"].append({
                "employee_id": emp.employee_id, "week": st.week,
                "demand_index": round(st.demand_index, 4),
                "resource_index": round(st.resource_index, 4),
                "strain": round(st.strain, 4),
                "exhaustion": round(st.exhaustion, 4),
                "cynicism": round(st.cynicism, 4),
                "reduced_efficacy": round(st.reduced_efficacy, 4),
                "composite": round(st.composite, 4),
                "burnout_stage": st.burnout_stage,
                "valence": round(st.valence, 4), "arousal": round(st.arousal, 4),
                "scar": round(st.scar, 4),
                "weeks_to_attrition": (attrition_week - st.week) if attrition_week is not None else None,
                "top_drivers": ",".join(st.top_drivers),
                "active_events": ",".join(sorted(set(st.active_events))),
            })

            if st.week % cfg.pulse_every_weeks == 0:
                data["pulse_response"].append(pulse_row(erng, emp, p, st, cfg))
            if st.week % cfg.comment_every_weeks == 0:
                c = comment_row(erng, emp, p, st, cfg)
                if c:
                    data["pulse_comment"].append(c)
            if (st.week + 1) in cfg.enps_weeks:
                data["enps_response"].append(enps_row(erng, emp, p, st))
            data["behavior_daily"].extend(behavior_rows(erng, emp, p, st, cfg))
            data["weekly_signal"].append(weekly_extras(erng, emp, p, st))

    return data


def main() -> None:
    ap = argparse.ArgumentParser(prog="generator")
    ap.add_argument("--seed", type=int, default=SimConfig.seed)
    ap.add_argument("--employees", type=int, default=SimConfig.n_employees)
    ap.add_argument("--weeks", type=int, default=SimConfig.n_weeks)
    ap.add_argument("--out", type=str, default=os.path.join(HERE, "out"))
    ap.add_argument("--lang", choices=("en", "ko"), default=SimConfig.lang,
                    help="코멘트 텍스트 언어 (기본 en)")
    ap.add_argument("--no-anonymous", action="store_true",
                    help="펄스를 기명으로 운영 (축소 보고 편향이 커진다)")
    args = ap.parse_args()

    cfg = SimConfig(seed=args.seed, n_employees=args.employees, n_weeks=args.weeks,
                    out_dir=args.out, anonymous_pulse=not args.no_anonymous, lang=args.lang)

    print(f"[1/3] 시뮬레이션: {cfg.n_employees}명 x {cfg.n_weeks}주 "
          f"(seed={cfg.seed}, lang={cfg.lang})")
    data = build(cfg)
    print(f"[2/3] 저장 중...")
    db = write_all(cfg.out_dir, os.path.join(HERE, "schema.sql"), data)
    counts = {k: len(v) for k, v in data.items()}
    print(f"      -> {db}")
    print(f"      -> {os.path.join(cfg.out_dir, 'csv')}/  ,  "
          f"{os.path.join(cfg.out_dir, 'json')}/")
    for k in ("employee", "truth_weekly_state", "pulse_response", "pulse_comment",
              "behavior_daily", "weekly_signal", "enps_response"):
        print(f"      {k:22s} {counts[k]:>7,d} rows")
    print(f"[3/3] 검증 리포트\n")
    report(data, cfg, db_path=db)


if __name__ == "__main__":
    main()
