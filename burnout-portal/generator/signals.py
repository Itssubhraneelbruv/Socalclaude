"""Layer 4: 관측 신호 — 포털이 실제로 볼 수 있는 데이터.

여기서 의도적으로 '지저분함'을 주입한다. 깨끗한 합성 데이터는 쓸모가 없다.
  - 정보성 결측: 번아웃이 심할수록 설문에 답하지 않는다
  - 사회적 바람직성 편향: 축소 보고
  - 응답 스타일: 중앙 몰림 / 극단 선호
  - 대리지표의 배신: 야근 많은 건강한 사람, 정시 퇴근하는 번아웃
"""
from __future__ import annotations

import datetime as dt
import random
from typing import Dict, List, Optional, Tuple

from .config import SimConfig
from .dynamics import WeekState, clamp
from .org import Employee
from .personas import Persona
from . import text_en, text_ko

_TEXT_MODULES = {"en": text_en, "ko": text_ko}

# 펄스 문항: 모두 '높을수록 좋음' 방향으로 통일 (역문항 혼란 제거)
PULSE_ITEMS = [
    ("q_workload", "지난 한 주 업무량은 감당 가능한 수준이었다"),
    ("q_energy", "일과 후에도 쓸 에너지가 남아 있었다"),
    ("q_engagement", "내 일에 마음이 가 있었다"),
    ("q_efficacy", "의미 있는 성과를 냈다고 느낀다"),
    ("q_support", "필요할 때 도움을 받을 수 있었다"),
    ("q_recognition", "내 기여가 정당하게 인정받았다"),
    ("q_mood", "지난 한 주 전반적인 기분은 좋았다"),
]


def _to_likert(rng: random.Random, x_good: float, bias: float, style: str) -> int:
    """잠재 '좋음' 값(0..1) -> 1..5 리커트. 편향과 응답 스타일이 여기서 들어간다."""
    m = 1.0 + 4.0 * clamp(x_good)
    m += bias * 0.9
    if style == "central":
        m = 3.0 + (m - 3.0) * 0.60
    elif style == "extreme":
        m = 3.0 + (m - 3.0) * 1.35
    m += rng.gauss(0, 0.45)
    return int(max(1, min(5, round(m))))


def pulse_row(rng: random.Random, emp: Employee, p: Persona, st: WeekState,
              cfg: SimConfig) -> Dict:
    """응답 여부까지 포함한 한 행. responded=0이면 문항은 None (정보성 결측)."""
    # 응답 확률: 소진·냉소가 높을수록 침묵한다
    prob = (0.90 - 0.50 * st.exhaustion - 0.32 * st.cynicism
            + p.survey_diligence + emp.jitter["diligence"] - 0.0015 * st.week)
    responded = rng.random() < clamp(prob, 0.10, 0.97)

    row: Dict[str, Optional[float]] = {
        "employee_id": emp.employee_id, "week": st.week,
        "responded": 1 if responded else 0,
        "is_anonymous": 1 if cfg.anonymous_pulse else 0,
    }
    for key, _ in PULSE_ITEMS:
        row[key] = None
    if not responded:
        row["completion_seconds"] = None
        return row

    bias = p.disclosure_bias + emp.jitter["disclosure"]
    if cfg.anonymous_pulse:
        bias *= 0.55  # 익명이면 축소 보고가 줄어든다

    d, r = st.demands, st.resources
    vals = {
        "q_workload": 1.0 - (0.6 * d["workload"] + 0.4 * d["time_pressure"]),
        "q_energy": 1.0 - st.exhaustion,
        "q_engagement": 1.0 - st.cynicism,
        "q_efficacy": 1.0 - st.reduced_efficacy,
        "q_support": 0.6 * r["support_manager"] + 0.4 * r["support_peer"],
        "q_recognition": r["reward_fairness"],
        "q_mood": (st.valence + 1.0) / 2.0,
    }
    for key, _ in PULSE_ITEMS:
        row[key] = _to_likert(rng, vals[key], bias, p.response_style)

    # 성의 없는 응답일수록 빨리 끝낸다 (straightlining 탐지용 신호)
    base_sec = 55 - 22 * st.cynicism + rng.gauss(0, 8)
    row["completion_seconds"] = int(max(6, base_sec))
    return row


def behavior_rows(rng: random.Random, emp: Employee, p: Persona, st: WeekState,
                  cfg: SimConfig) -> List[Dict]:
    """일별 행동 로그 7건. 근무시간은 스트레스의 대리지표일 뿐 정답이 아니다."""
    d, r = st.demands, st.resources
    monday = cfg.start_date + dt.timedelta(weeks=st.week)

    # 휴가 일수를 평일에 배분
    pto_left = int(st.pto_days)
    pto_days_set = set()
    if pto_left > 0:
        start = rng.randrange(0, max(1, 5 - min(pto_left, 5) + 1))
        for i in range(min(pto_left, 5)):
            pto_days_set.add(start + i)

    # 심리적 이탈은 근무시간을 '줄인다' — 순진한 모델이 여기서 틀린다
    disengage = p.presence_decay * st.cynicism * 2.4

    rows: List[Dict] = []
    for dow in range(7):
        day = monday + dt.timedelta(days=dow)
        is_weekend = dow >= 5
        on_pto = dow in pto_days_set

        if on_pto:
            hours = 0.0
            # 회복 실패형은 휴가 중에도 알림을 본다
            after_hours = int(max(0, rng.gauss(35 * (1 - p.detachment), 12))) if rng.random() < 0.45 else 0
            meetings = 0.0
        elif is_weekend:
            work_p = clamp(0.05 + 0.42 * d["time_pressure"] * (1 - p.detachment)
                           + 0.30 * max(0.0, p.overwork_tendency) - 0.45 * disengage)
            if rng.random() < work_p:
                hours = max(0.5, rng.gauss(3.0 + 2.0 * d["workload"], 1.0))
            else:
                hours = 0.0
            after_hours = int(hours * 60 * 0.4)
            meetings = 0.0
        else:
            hours = (7.4 + 3.4 * d["workload"] + 1.7 * d["time_pressure"]
                     + 1.7 * p.overwork_tendency + emp.jitter["hours"] - disengage
                     + rng.gauss(0, 0.55))
            hours = max(2.0, hours)
            over = max(0.0, hours - 9.0)
            after_hours = int(over * 60 * (1.1 - 0.6 * p.detachment) + max(0, rng.gauss(8, 10)))
            meetings = clamp(0.6 + 4.2 * d["context_switching"]
                             + (1.2 if emp.is_manager else 0.0) + rng.gauss(0, 0.4), 0, 7.5)

        focus_min = max(0.0, hours * 60 - meetings * 60 - 45 * d["context_switching"] * 8)
        msgs = int(max(0, rng.gauss(38 + 55 * d["context_switching"] - 25 * st.cynicism, 12))) if hours > 0 else 0
        # 산출물은 효능감·소진에 따라 떨어진다 (presenteeism)
        tickets = 0
        if hours > 0 and not is_weekend:
            base = 2.4 * (hours / 8.0)
            tickets = int(max(0, round(base * (1 - 0.45 * st.reduced_efficacy)
                                       * (1 - 0.30 * st.exhaustion) + rng.gauss(0, 0.6))))

        rows.append({
            "employee_id": emp.employee_id, "week": st.week,
            "date": day.isoformat(), "dow": dow,
            "is_pto": 1 if on_pto else 0,
            "work_hours": round(hours, 2),
            "after_hours_minutes": int(after_hours),
            "meeting_hours": round(meetings, 2),
            "focus_minutes": int(focus_min),
            "messages_sent": msgs,
            "tickets_closed": tickets,
            "weekend_active": 1 if (is_weekend and hours > 0) else 0,
        })
    return rows


def weekly_extras(rng: random.Random, emp: Employee, p: Persona, st: WeekState) -> Dict:
    """1:1 참석, 휴가 취소 등 주 단위 이벤트 신호."""
    scheduled = 1 if (st.week % 2 == 0 or emp.is_manager) else 0
    attended = 0
    if scheduled:
        att_p = clamp(0.95 - 0.50 * st.cynicism - 0.18 * st.exhaustion)
        attended = 1 if rng.random() < att_p else 0
    return {
        "employee_id": emp.employee_id, "week": st.week,
        "one_on_one_scheduled": scheduled,
        "one_on_one_attended": attended,
        "pto_days_taken": st.pto_days,
        "pto_cancelled": st.pto_cancelled,
        "pto_balance": round(st.pto_balance, 1),
    }


def comment_row(rng: random.Random, emp: Employee, p: Persona, st: WeekState,
                cfg: SimConfig) -> Optional[Dict]:
    """자유 서술. 펄스보다 응답률이 더 낮고, 편향은 텍스트 톤으로 나타난다."""
    prob = clamp(0.55 - 0.35 * st.exhaustion - 0.25 * st.cynicism + p.survey_diligence, 0.05, 0.85)
    if rng.random() > prob:
        return None
    dims = {"exhaustion": st.exhaustion, "cynicism": st.cynicism,
            "reduced_efficacy": st.reduced_efficacy}
    # 축소 보고형은 텍스트에서도 톤을 눌러 쓴다
    shown_valence = st.valence + p.disclosure_bias * 0.35
    # 텍스트 조립은 별도 난수 스트림에서. 언어마다 난수 소비량이 다르므로
    # 같은 스트림을 쓰면 --lang 을 바꿨을 때 시뮬레이션 전체가 흔들린다.
    crng = random.Random(f"{cfg.seed}:{emp.employee_id}:{st.week}")
    mod = _TEXT_MODULES[cfg.lang]
    text, label = mod.generate_comment(crng, p.voice, shown_valence, st.composite,
                                       dims, st.top_drivers)
    return {
        "employee_id": emp.employee_id, "week": st.week, "text": text,
        "char_len": len(text),
        "label_sentiment_bucket": label["sentiment_bucket"],
        "label_dominant_dimension": label["dominant_dimension"],
        "label_mentioned_drivers": label["mentioned_drivers"],
    }


def enps_row(rng: random.Random, emp: Employee, p: Persona, st: WeekState) -> Dict:
    base = 10.0 * (0.55 * ((st.valence + 1) / 2) + 0.45 * (1 - st.cynicism))
    base += p.disclosure_bias * 0.8 + rng.gauss(0, 0.9)
    return {
        "employee_id": emp.employee_id, "week": st.week,
        "enps_score": int(max(0, min(10, round(base)))),
    }
