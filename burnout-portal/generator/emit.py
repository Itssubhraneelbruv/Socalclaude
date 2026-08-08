"""출력: SQLite DB + CSV + JSON 덤프."""
from __future__ import annotations

import csv
import json
import os
import sqlite3
from typing import Dict, List, Sequence


def _insert(cur: sqlite3.Cursor, table: str, rows: List[Dict], columns: Sequence[str]) -> None:
    if not rows:
        return
    ph = ",".join("?" for _ in columns)
    cur.executemany(
        f"INSERT OR REPLACE INTO {table} ({','.join(columns)}) VALUES ({ph})",
        [tuple(r.get(c) for c in columns) for r in rows],
    )


TABLES = {
    "team": ["team_key", "name", "department", "headcount"],
    "employee": ["employee_id", "team_key", "department", "level", "tenure_months",
                 "is_manager", "hire_week", "pto_entitlement_days"],
    "org_event": ["event_id", "event_key", "label", "scope", "team_key",
                  "start_week", "end_week"],
    "pulse_response": ["employee_id", "week", "responded", "is_anonymous",
                       "q_workload", "q_energy", "q_engagement", "q_efficacy",
                       "q_support", "q_recognition", "q_mood", "completion_seconds"],
    "pulse_comment": ["employee_id", "week", "text", "char_len",
                      "label_sentiment_bucket", "label_dominant_dimension",
                      "label_mentioned_drivers"],
    "behavior_daily": ["employee_id", "week", "date", "dow", "is_pto", "work_hours",
                       "after_hours_minutes", "meeting_hours", "focus_minutes",
                       "messages_sent", "tickets_closed", "weekend_active"],
    "weekly_signal": ["employee_id", "week", "one_on_one_scheduled", "one_on_one_attended",
                      "pto_days_taken", "pto_cancelled", "pto_balance"],
    "enps_response": ["employee_id", "week", "enps_score"],
    "truth_employee": ["employee_id", "persona_key", "persona_name", "trajectory",
                       "attrition_week", "peak_stage", "weeks_at_risk"],
    "truth_weekly_state": ["employee_id", "week", "demand_index", "resource_index", "strain",
                           "exhaustion", "cynicism", "reduced_efficacy", "composite",
                           "burnout_stage", "valence", "arousal", "scar", "weeks_to_attrition",
                           "top_drivers", "active_events"],
}


def write_all(out_dir: str, schema_path: str, data: Dict[str, List[Dict]]) -> str:
    os.makedirs(out_dir, exist_ok=True)
    db_path = os.path.join(out_dir, "burnout.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    with open(schema_path, encoding="utf-8") as f:
        schema = f.read()

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executescript(schema)
    for table, cols in TABLES.items():
        _insert(cur, table, data.get(table, []), cols)
    con.commit()

    csv_dir = os.path.join(out_dir, "csv")
    os.makedirs(csv_dir, exist_ok=True)
    for table, cols in TABLES.items():
        rows = data.get(table, [])
        with open(os.path.join(csv_dir, f"{table}.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c) for c in cols})

    json_dir = os.path.join(out_dir, "json")
    os.makedirs(json_dir, exist_ok=True)
    for table, cols in TABLES.items():
        rows = [{c: r.get(c) for c in cols} for r in data.get(table, [])]
        with open(os.path.join(json_dir, f"{table}.json"), "w", encoding="utf-8") as f:
            # 대용량 테이블이라 compact. 한글은 그대로 (ensure_ascii=False)
            json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))

    _write_sample(json_dir, data)
    con.close()
    return db_path


def _write_sample(json_dir: str, data: Dict[str, List[Dict]]) -> str:
    """읽을 수 있는 샘플: 위험 단계까지 간 직원 1명을 전 계층 조인해서 pretty print.

    전체 덤프는 사람이 읽을 물건이 아니라서, 데이터 구조를 눈으로 확인할
    용도의 파일을 따로 만든다.
    """
    truth_emp = {r["employee_id"]: r for r in data["truth_employee"]}

    # 위험 단계까지 갔으면서 설문에도 절반 이상 응답한 사람을 고른다.
    # 응답률이 0인 사람을 뽑으면 pulse가 전부 null이라 구조가 안 보인다.
    resp: Dict[str, List[int]] = {}
    for p in data["pulse_response"]:
        resp.setdefault(p["employee_id"], []).append(p["responded"])
    rate = {k: sum(v) / len(v) for k, v in resp.items() if v}

    target = next((eid for eid, r in truth_emp.items()
                   if r["peak_stage"] >= 3 and rate.get(eid, 0) >= 0.5), None)
    if target is None:
        target = max(truth_emp, key=lambda e: (truth_emp[e]["peak_stage"], rate.get(e, 0)))

    def rows_of(table: str):
        return [r for r in data[table] if r.get("employee_id") == target]

    emp = next(r for r in data["employee"] if r["employee_id"] == target)
    team = next(t for t in data["team"] if t["team_key"] == emp["team_key"])
    truth_weeks = {r["week"]: r for r in rows_of("truth_weekly_state")}
    pulse = {r["week"]: r for r in rows_of("pulse_response")}
    weekly = {r["week"]: r for r in rows_of("weekly_signal")}
    comments = {r["week"]: r for r in rows_of("pulse_comment")}

    beh: Dict[int, Dict] = {}
    for b in rows_of("behavior_daily"):
        w = beh.setdefault(b["week"], {"work_hours": 0.0, "after_hours_minutes": 0,
                                       "meeting_hours": 0.0, "focus_minutes": 0,
                                       "pto_days": 0, "weekend_days": 0})
        w["work_hours"] = round(w["work_hours"] + b["work_hours"], 2)
        w["after_hours_minutes"] += b["after_hours_minutes"]
        w["meeting_hours"] = round(w["meeting_hours"] + b["meeting_hours"], 2)
        w["focus_minutes"] += b["focus_minutes"]
        w["pto_days"] += b["is_pto"]
        w["weekend_days"] += b["weekend_active"]

    weeks = []
    for wk in sorted(truth_weeks):
        t = truth_weeks[wk]
        p = pulse.get(wk, {})
        weeks.append({
            "week": wk,
            "observed": {   # 포털이 볼 수 있는 것
                "pulse": {k: p.get(k) for k in
                          ("responded", "q_workload", "q_energy", "q_engagement",
                           "q_efficacy", "q_support", "q_recognition", "q_mood")},
                "comment": comments.get(wk, {}).get("text"),
                "behavior_week": beh.get(wk),
                "weekly_signal": {k: weekly.get(wk, {}).get(k) for k in
                                  ("one_on_one_scheduled", "one_on_one_attended",
                                   "pto_days_taken", "pto_cancelled", "pto_balance")},
            },
            "truth": {      # 포털은 절대 못 보는 정답
                "exhaustion": t["exhaustion"], "cynicism": t["cynicism"],
                "reduced_efficacy": t["reduced_efficacy"], "composite": t["composite"],
                "burnout_stage": t["burnout_stage"], "scar": t["scar"],
                "valence": t["valence"], "arousal": t["arousal"],
                "demand_index": t["demand_index"], "resource_index": t["resource_index"],
                "top_drivers": [d for d in t["top_drivers"].split(",") if d],
                "active_events": [e for e in (t["active_events"] or "").split(",") if e],
                "weeks_to_attrition": t["weeks_to_attrition"],
            },
        })

    sample = {
        "_note": "observed = what the portal can see. truth = evaluation-only ground truth; never feed it to a model as a feature.",
        "employee": emp,
        "team": {"name": team["name"], "department": team["department"]},
        "truth_employee": truth_emp[target],
        "weeks": weeks,
    }
    path = os.path.join(json_dir, "_sample_employee.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    return path
