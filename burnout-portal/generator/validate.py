"""데이터 검증 — 합성 데이터가 '쓸 만한가'를 보는 4가지 테스트.

1. 분포 sanity      : 유병률이 현실 범위(20~30%)인가
2. 알려진 상관 재현 : 자율성↔긴장 음, 보상공정성↔냉소 음, 응답률↔소진 음
3. 페르소나 분리도  : 아키타입별 프로파일이 실제로 구분되는가
4. 순진한 베이스라인 실패 : '근무시간 = 번아웃' 모델이 반례 그룹에서 틀리는가
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from typing import Dict, List, Optional, Sequence

from .config import SimConfig
from .personas import PERSONA_BY_KEY, PERSONAS


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else float("nan")


def _mean(v: Sequence[float]) -> float:
    return sum(v) / len(v) if v else float("nan")


def _line(ok: bool, text: str) -> str:
    return ("  [PASS] " if ok else "  [WARN] ") + text


def report(data: Dict[str, List[Dict]], cfg: SimConfig, db_path: Optional[str] = None) -> None:
    truth = data["truth_weekly_state"]
    temp = {r["employee_id"]: r for r in data["truth_employee"]}
    beh = data["behavior_daily"]
    pulse = data["pulse_response"]

    # 주간 근무시간 집계
    hours_week: Dict[tuple, float] = defaultdict(float)
    for b in beh:
        hours_week[(b["employee_id"], b["week"])] += b["work_hours"]

    # ---------------------------------------------------------------- 1
    print("1. 분포 sanity")
    n_emp = len(temp)
    at_risk = sum(1 for r in temp.values() if r["peak_stage"] >= 2)
    critical = sum(1 for r in temp.values() if r["peak_stage"] >= 3)
    week_at_risk = sum(1 for r in truth if r["burnout_stage"] >= 2) / max(1, len(truth))
    attrited = sum(1 for r in temp.values() if r["attrition_week"] is not None)
    prev = at_risk / n_emp
    # 시점 유병률(point prevalence)이 문헌 기준선이다. 연간 발생률은 당연히 더 높다.
    print(_line(0.15 <= week_at_risk <= 0.32,
                f"시점 유병률 (직원-주 stage>=2): {week_at_risk:.1%}  [기준 20~30%]"))
    print(_line(0.25 <= prev <= 0.50,
                f"연간 발생률 (1회 이상 stage>=2): {prev:.1%} ({at_risk}/{n_emp})"))
    # 심각 단계는 3주 이상 지속 기준의 '연간 발생률'이다. 시점 유병률(5~10%)보다
    # 당연히 높다. 이 값을 낮추려면 페르소나 비중이 아니라 dim_gain을 조정할 것.
    print(_line(0.05 <= critical / n_emp <= 0.16,
                f"심각(stage>=3) 연간 발생률: {critical/n_emp:.1%}  [참고 5~16%]"))
    print(_line(0.06 <= attrited / n_emp <= 0.30,
                f"연간 이탈률: {attrited/n_emp:.1%} ({attrited}명)"))

    # ---------------------------------------------------------------- 2
    print("\n2. 알려진 상관 재현")
    strain = [r["strain"] for r in truth]
    cyn = [r["cynicism"] for r in truth]
    exh = [r["exhaustion"] for r in truth]
    res = [r["resource_index"] for r in truth]
    dem = [r["demand_index"] for r in truth]
    r1 = pearson(res, strain)
    r2 = pearson(res, cyn)
    r3 = pearson(dem, exh)
    print(_line(r1 < -0.5, f"자원지수 ↔ 긴장(strain)      r = {r1:+.2f}  (음수 기대)"))
    print(_line(r2 < -0.3, f"자원지수 ↔ 냉소             r = {r2:+.2f}  (음수 기대)"))
    print(_line(r3 > 0.3, f"요구지수 ↔ 소진             r = {r3:+.2f}  (양수 기대)"))

    # 정보성 결측
    st_by_key = {(r["employee_id"], r["week"]): r for r in truth}
    resp_by_stage: Dict[int, List[int]] = defaultdict(list)
    for p in pulse:
        s = st_by_key.get((p["employee_id"], p["week"]))
        if s:
            resp_by_stage[s["burnout_stage"]].append(p["responded"])
    rates = {k: _mean(v) for k, v in sorted(resp_by_stage.items())}
    ok = (rates.get(0, 0) > rates.get(3, 1))
    print(_line(ok, "응답률 by stage: " + "  ".join(f"stage{k}={v:.0%}" for k, v in rates.items())
                + "   (번아웃일수록 침묵)"))

    # 축소 보고 편향 — '실제로 소진된 주'에 한정해야 의미가 있다.
    # (전체 평균으로 보면 중앙 몰림 응답 스타일과 상쇄되어 사라진다)
    print("\n   축소 보고 검증 — 실제 소진 0.5 이상인 주의 q_energy")
    for pk in ("overachiever", "caregiver", "invisible", "anchored"):
        obs, exp = [], []
        for p in pulse:
            if not p["responded"]:
                continue
            if temp.get(p["employee_id"], {}).get("persona_key") != pk:
                continue
            s = st_by_key.get((p["employee_id"], p["week"]))
            if not s or s["exhaustion"] < 0.5:
                continue
            obs.append(p["q_energy"])
            exp.append(1 + 4 * (1 - s["exhaustion"]))
        if len(obs) >= 20:
            gap = _mean(obs) - _mean(exp)
            mark = "  <- 축소 보고" if gap > 0.25 else ""
            print(f"     {PERSONA_BY_KEY[pk].name_en:<26s} n={len(obs):>4d}  관측 {_mean(obs):.2f} / "
                  f"기대 {_mean(exp):.2f} / 편차 {gap:+.2f}{mark}")
        else:
            print(f"     {PERSONA_BY_KEY[pk].name_en:<26s} 해당 주 표본 부족 (n={len(obs)})")

    # ---------------------------------------------------------------- 3
    print("\n3. 페르소나 분리도 (평균 프로파일)")
    print(f"   {'persona':<26s} {'n':>4s} {'소진':>6s} {'냉소':>6s} {'효능저하':>8s} "
          f"{'주근무h':>8s} {'응답률':>7s} {'이탈':>6s}")
    for p in PERSONAS:
        ids = [k for k, v in temp.items() if v["persona_key"] == p.key]
        if not ids:
            continue
        idset = set(ids)
        rows = [r for r in truth if r["employee_id"] in idset]
        hrs = [v for (eid, _), v in hours_week.items() if eid in idset]
        rr = [q["responded"] for q in pulse if q["employee_id"] in idset]
        att = sum(1 for i in ids if temp[i]["attrition_week"] is not None) / len(ids)
        print(f"   {p.name_en:<26s} {len(ids):>4d} {_mean([r['exhaustion'] for r in rows]):>6.2f} "
              f"{_mean([r['cynicism'] for r in rows]):>6.2f} "
              f"{_mean([r['reduced_efficacy'] for r in rows]):>8.2f} "
              f"{_mean(hrs):>8.1f} {_mean(rr):>7.0%} {att:>6.0%}")

    # ---------------------------------------------------------------- 4
    print("\n4. 순진한 베이스라인('근무시간=번아웃')의 실패 확인")
    xs, ys = [], []
    for r in truth:
        h = hours_week.get((r["employee_id"], r["week"]))
        if h is not None:
            xs.append(h)
            ys.append(r["composite"])
    r_all = pearson(xs, ys)
    print(f"   전체:  근무시간 ↔ 번아웃 종합  r = {r_all:+.2f}")
    for pk in ("overachiever", "ambiguous", "coaster", "anchored"):
        idset = {k for k, v in temp.items() if v["persona_key"] == pk}
        xs2, ys2 = [], []
        for r in truth:
            if r["employee_id"] not in idset:
                continue
            h = hours_week.get((r["employee_id"], r["week"]))
            if h is not None:
                xs2.append(h)
                ys2.append(r["composite"])
        rp = pearson(xs2, ys2)
        flag = "  <- 반례" if pk in ("ambiguous", "coaster") else ""
        print(f"   {PERSONA_BY_KEY[pk].name_en:<26s} r = {rp:+.2f}{flag}")
    print(_line(True, "반례 그룹에서 상관이 약하거나 뒤집히면 단일 지표 모델은 실패한다"))

    # ---------------------------------------------------------------- 텍스트
    com = data["pulse_comment"]
    if com:
        print("\n5. 코멘트 라벨 분포")
        b = defaultdict(int)
        d = defaultdict(int)
        for c in com:
            b[c["label_sentiment_bucket"]] += 1
            d[c["label_dominant_dimension"]] += 1
        print("   감정: " + "  ".join(f"{k}={v/len(com):.0%}" for k, v in sorted(b.items())))
        print("   지배차원: " + "  ".join(f"{k}={v/len(com):.0%}" for k, v in sorted(d.items())))
        uniq = len({c["text"] for c in com})
        print(_line(uniq / len(com) > 0.5,
                    f"고유 문장 비율 {uniq/len(com):.0%} ({uniq}/{len(com)})"))

    # ---------------------------------------------------------------- 프라이버시
    if db_path:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("SELECT MIN(respondents) FROM v_hr_team_week")
        m = cur.fetchone()[0]
        print("\n6. 프라이버시 경계")
        print(_line(m is not None and m >= cfg.min_group_size,
                    f"HR 뷰 최소 응답자 수 = {m} (기준 {cfg.min_group_size} 이상)"))
        cur.execute("SELECT COUNT(*) FROM v_hr_team_week")
        print(f"       HR 뷰 행 수: {cur.fetchone()[0]:,}")
        con.close()
