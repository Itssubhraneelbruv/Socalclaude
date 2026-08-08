"""Layer 2-3: 드라이버 시계열 + 잠재 상태 동역학.

여기서 나오는 값이 '정답(ground truth)'이다. 포털은 이걸 절대 못 본다.
포털은 signals.py가 만드는 관측치만 본다.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .config import (COMPOSITE_WEIGHTS, DEMAND_WEIGHTS, DEMANDS, RESOURCE_WEIGHTS,
                     RESOURCES, STAGE_CUTOFFS, SimConfig, TEAMS)
from .org import Employee, Event, event_deltas
from .personas import Persona, PERSONA_BY_KEY

TEAM_BY_KEY = {t.key: t for t in TEAMS}

# 건강한 기준선 — 활성 드라이버 판정에 쓴다
HEALTHY_DEMAND = 0.45
HEALTHY_RESOURCE = 0.55


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def smoothstep(t: float) -> float:
    t = clamp(t)
    return t * t * (3 - 2 * t)


@dataclass
class WeekState:
    employee_id: str
    week: int
    demands: Dict[str, float]
    resources: Dict[str, float]
    demand_index: float
    resource_index: float
    strain: float
    exhaustion: float
    cynicism: float
    reduced_efficacy: float
    composite: float
    burnout_stage: int
    valence: float
    arousal: float
    scar: float
    pto_days: float
    pto_balance: float
    pto_cancelled: int
    active_events: List[str]
    top_drivers: List[str]
    active: bool = True


# --- 직급/직무 베이스라인 ----------------------------------------------------
LEVEL_DEMAND = {"IC1": -0.06, "IC2": -0.02, "IC3": 0.03, "IC4": 0.07, "Lead": 0.10, "Manager": 0.14}
LEVEL_RESOURCE = {"IC1": -0.08, "IC2": -0.03, "IC3": 0.02, "IC4": 0.06, "Lead": 0.08, "Manager": 0.05}


def _base_drivers(emp: Employee, p: Persona) -> Tuple[Dict[str, float], Dict[str, float]]:
    t = TEAM_BY_KEY[emp.team]
    d = {
        "workload": t.workload_baseline,
        "time_pressure": t.workload_baseline * 0.85 + 0.08,
        "role_ambiguity": 0.32,
        "emotional_labor": t.emotional_labor_base,
        "context_switching": t.meeting_density,
        "unpredictability": 0.28,
    }
    r = {
        "autonomy": t.autonomy_base,
        "support_manager": t.manager_quality,
        "support_peer": 0.58,
        "reward_fairness": t.reward_fairness_base,
        "growth_meaning": 0.55,
        "recovery_opportunity": 0.58,
    }
    ld, lr = LEVEL_DEMAND[emp.level], LEVEL_RESOURCE[emp.level]
    for k in d:
        d[k] = clamp(d[k] + ld + p.demand_shift.get(k, 0.0) + emp.jitter["demand"])
    for k in r:
        r[k] = clamp(r[k] + lr + p.resource_shift.get(k, 0.0) + emp.jitter["resource"])
    # 신입은 역할 모호성이 높고 동료 지지가 낮다
    if emp.tenure_months < 6:
        d["role_ambiguity"] = clamp(d["role_ambiguity"] + 0.18)
        r["support_peer"] = clamp(r["support_peer"] - 0.12)
    return d, r


def _trajectory(p: Persona, week: int, n_weeks: int) -> Tuple[Dict[str, float], Dict[str, float], float]:
    """페르소나 궤적이 만드는 시간에 따른 드라이버 표류. 세 번째 값은 노이즈 증폭."""
    prog = week / max(1, n_weeks - 1)
    d: Dict[str, float] = {}
    r: Dict[str, float] = {}
    noise_amp = 1.0

    if p.trajectory == "acute":
        ramp = smoothstep((prog - 0.40) / 0.35)
        d["workload"] = 0.24 * ramp
        d["time_pressure"] = 0.20 * ramp
        r["recovery_opportunity"] = -0.26 * ramp
    elif p.trajectory == "chronic":
        r["reward_fairness"] = -0.20 * prog
        r["growth_meaning"] = -0.16 * prog
        d["role_ambiguity"] = 0.10 * prog
    elif p.trajectory == "volatile":
        noise_amp = 2.3
        d["unpredictability"] = 0.10 * math.sin(week / 3.1)
        d["role_ambiguity"] = 0.10 * math.sin(week / 4.7 + 1.2)
    elif p.trajectory == "recovery":
        iv = 0.34  # 개입 시점
        if prog < iv:
            # 개입 전에는 조건이 그대로다. 여기서 미리 좋아지면
            # '개입 효과'를 검증할 수 없다.
            d["workload"] = 0.14
            d["time_pressure"] = 0.10
            r["recovery_opportunity"] = -0.18
            r["support_manager"] = -0.14
        else:
            g = smoothstep((prog - iv) / 0.40)
            r["recovery_opportunity"] = 0.30 * g
            r["support_manager"] = 0.22 * g
            r["growth_meaning"] = 0.18 * g
            d["workload"] = -0.18 * g
            d["time_pressure"] = -0.14 * g
    return d, r, noise_amp


def _seasonal(week: int, n_weeks: int) -> Dict[str, float]:
    d: Dict[str, float] = {}
    wk_in_q = week % 13
    if wk_in_q >= 11:  # 분기말
        d["time_pressure"] = 0.16
        d["workload"] = 0.10
    if 28 <= week <= 33:  # 여름 휴가철 — 남은 사람 부하는 오히려 오른다
        d["workload"] = d.get("workload", 0.0) + 0.08
    return d


class EmployeeSim:
    """직원 1명의 52주 시뮬레이션."""

    def __init__(self, emp: Employee, cfg: SimConfig, events: List[Event], rng: random.Random):
        self.emp = emp
        self.p: Persona = PERSONA_BY_KEY[emp.persona]
        self.cfg = cfg
        self.events = events
        self.rng = rng
        self.base_d, self.base_r = _base_drivers(emp, self.p)
        self.ar = {k: 0.0 for k in DEMANDS + RESOURCES}
        self.E = clamp(self.p.init_state.get("exhaustion", 0.2) + rng.gauss(0, 0.05))
        self.C = clamp(self.p.init_state.get("cynicism", 0.15) + rng.gauss(0, 0.05))
        self.RE = clamp(self.p.init_state.get("reduced_efficacy", 0.15) + rng.gauss(0, 0.05))
        self.shock = 0.0
        # 흉터: 한 번 무너진 사람은 완전히 원래대로 돌아가지 않는다.
        # 재발 예측에서 가장 강한 예측자이므로 정답에도 남긴다.
        self.scar = 0.0
        self.pto_balance = float(emp.pto_entitlement_days)
        self.sens = self.p.sensitivity * clamp(emp.jitter["sensitivity"], 0.5, 1.6)
        self.rho = self.p.recovery_rate * clamp(emp.jitter["recovery"], 0.5, 1.6)
        self.gain_j = {d: clamp(emp.jitter["gain_" + d], 0.55, 1.5)
                       for d in ("exhaustion", "cynicism", "reduced_efficacy")}
        self.attrition_week: Optional[int] = None

    # --- 드라이버 --------------------------------------------------------
    def _drivers(self, week: int):
        traj_d, traj_r, noise_amp = _trajectory(self.p, week, self.cfg.n_weeks)
        ev_d, ev_r, shock, active = event_deltas(self.events, self.emp.team, week)
        seas = _seasonal(week, self.cfg.n_weeks)

        d, r = {}, {}
        for k in DEMANDS:
            self.ar[k] = 0.62 * self.ar[k] + self.rng.gauss(0, 0.055 * noise_amp)
            d[k] = clamp(self.base_d[k] + traj_d.get(k, 0.0) + ev_d.get(k, 0.0)
                         + seas.get(k, 0.0) + self.ar[k])
        for k in RESOURCES:
            self.ar[k] = 0.62 * self.ar[k] + self.rng.gauss(0, 0.045)
            r[k] = clamp(self.base_r[k] + traj_r.get(k, 0.0) + ev_r.get(k, 0.0) + self.ar[k])
        return d, r, shock, active

    # --- 휴가: 회복의 주요 경로이자 '회복 실패'의 관측 신호 ----------------
    def _pto(self, week: int, d: Dict[str, float], r: Dict[str, float]) -> Tuple[float, int]:
        if self.pto_balance <= 0:
            return 0.0, 0
        # 사람은 잔여 일수를 남은 기간에 맞춰 배분한다. 잔여가 많은데 기간이
        # 얼마 안 남으면 사용 압력이 올라간다(연말 소진성 사용).
        # 다만 상한을 둬서, 쓰지 못하는 사람은 끝까지 못 쓰고 잔여를 남긴다 —
        # 미사용 잔여 자체가 회복 실패의 관측 신호다.
        weeks_left = max(1, self.cfg.n_weeks - week)
        pace = min(self.pto_balance / weeks_left, 0.8)
        want = 0.06 + 0.45 * pace
        if 28 <= week <= 33:
            want += 0.18  # 여름 휴가철
        want += 0.15 * r["recovery_opportunity"]
        want -= 0.20 * d["workload"] + 0.16 * d["time_pressure"]
        want -= 0.22 * self.p.overwork_tendency
        want += 0.10 * self.p.detachment
        if self.rng.random() > clamp(want, 0.01, 0.80):
            return 0.0, 0
        days = min(self.pto_balance, self.rng.choice([1, 1, 2, 3, 5]))
        # 크런치 중이면 취소
        if d["time_pressure"] > 0.78 and self.rng.random() < 0.55:
            return 0.0, 1
        self.pto_balance -= days
        return float(days), 0

    # --- 잠재 상태 --------------------------------------------------------
    def step(self, week: int) -> WeekState:
        d, r, shock, active = self._drivers(week)
        di = sum(DEMAND_WEIGHTS[k] * d[k] for k in DEMANDS)
        ri = sum(RESOURCE_WEIGHTS[k] * r[k] for k in RESOURCES)
        # 자율성은 부하-긴장 관계를 완충한다 (Karasek)
        strain = (di - ri) * (1 - 0.35 * r["autonomy"])

        pto_days, pto_cancelled = self._pto(week, d, r)
        rec = clamp(0.30 + 0.45 * r["recovery_opportunity"] + 0.35 * self.p.detachment
                    + 0.09 * pto_days - 0.25 * max(0.0, d["time_pressure"] - 0.7), 0.0, 1.4)

        # 히스테리시스: 임계치를 넘으면 회복 자체가 느려진다
        rho_eff = self.rho * rec * (0.45 if self.E > 0.70 else 1.0)

        gE = self.p.dim_gain.get("exhaustion", 1.0) * self.gain_j["exhaustion"]
        gC = self.p.dim_gain.get("cynicism", 1.0) * self.gain_j["cynicism"]
        gF = self.p.dim_gain.get("reduced_efficacy", 1.0) * self.gain_j["reduced_efficacy"]

        aE = 0.11 * self.sens * (1.0 + 0.6 * self.scar) * gE
        self.E = clamp(self.E + aE * max(0.0, strain + 0.05)
                       - 0.09 * rho_eff * self.E + self.rng.gauss(0, 0.018))
        if self.E > 0.70:
            self.scar = min(0.35, self.scar + 0.012)
        self.E = max(self.E, 0.55 * self.scar)   # 완전 회복은 없다

        cyn_p = (0.42 * (1 - r["reward_fairness"]) + 0.26 * (1 - r["support_manager"])
                 + 0.16 * (1 - r["growth_meaning"]) + 0.16 * d["unpredictability"])
        self.C = clamp(self.C + 0.13 * gC * (cyn_p - 0.40)
                       + 0.040 * max(0.0, self.E - 0.55)
                       - 0.050 * self.C * ri + self.rng.gauss(0, 0.016))
        self.C = max(self.C, 0.35 * self.scar)

        eff_p = (0.34 * (1 - r["growth_meaning"]) + 0.30 * d["role_ambiguity"]
                 + 0.18 * (1 - r["autonomy"]) + 0.18 * max(0.0, self.E - 0.40))
        self.RE = clamp(self.RE + 0.12 * gF * (eff_p - 0.38)
                        - 0.050 * self.RE * ri + self.rng.gauss(0, 0.016))

        composite = sum(COMPOSITE_WEIGHTS[k] * v for k, v in
                        (("exhaustion", self.E), ("cynicism", self.C), ("reduced_efficacy", self.RE)))

        stage = 0
        for i, cut in enumerate(STAGE_CUTOFFS):
            if composite >= cut:
                stage = i + 1
        # 단일 축이 극단이면 종합이 낮아도 위험하다 (심리적 이탈형이 여기서 잡힌다)
        if self.C >= 0.78:
            stage = max(stage, 2)
        if self.E >= 0.90:
            stage = max(stage, 3)

        self.shock = 0.55 * self.shock + shock
        # 중립점을 composite≈0.30에 맞춘다. 그래야 '보통 정도로 지친 주'가
        # 긍정 코멘트로 새어나가지 않는다.
        valence = clamp(0.85 - 2.6 * composite + 0.40 * (ri - 0.5) + self.shock
                        + self.rng.gauss(0, 0.10), -1.0, 1.0)
        # 번아웃 말기에는 각성이 오히려 떨어진다 (불안 -> 무기력)
        arousal = clamp(0.45 + 0.55 * max(0.0, strain) + 0.30 * d["unpredictability"]
                        - 0.80 * max(0.0, self.E - 0.62) + self.rng.gauss(0, 0.07))

        top = self._top_drivers(d, r)

        return WeekState(
            employee_id=self.emp.employee_id, week=week,
            demands=d, resources=r, demand_index=di, resource_index=ri, strain=strain,
            exhaustion=self.E, cynicism=self.C, reduced_efficacy=self.RE,
            composite=composite, burnout_stage=stage,
            valence=valence, arousal=arousal, scar=self.scar,
            pto_days=pto_days, pto_balance=self.pto_balance, pto_cancelled=pto_cancelled,
            active_events=active, top_drivers=top,
        )

    def _top_drivers(self, d: Dict[str, float], r: Dict[str, float]) -> List[str]:
        """추천 엔진 평가용 정답지: 지금 이 사람에게 실제로 작동 중인 드라이버."""
        contrib = []
        for k in DEMANDS:
            c = DEMAND_WEIGHTS[k] * (d[k] - HEALTHY_DEMAND)
            if c > 0.012:
                contrib.append((c, k))
        for k in RESOURCES:
            c = RESOURCE_WEIGHTS[k] * (HEALTHY_RESOURCE - r[k])
            if c > 0.012:
                contrib.append((c, "lack_of_" + k))
        contrib.sort(reverse=True)
        return [k for _, k in contrib[:3]]

    def attrition_hazard(self, st: WeekState) -> float:
        z = (3.0 * st.cynicism + 1.0 * st.exhaustion + 1.2 * st.reduced_efficacy
             - 2.2 * st.resource_index - 1.6)
        h = 0.0011 * self.p.attrition_gain * math.exp(z)
        return min(h, 0.05)


def simulate_employee(emp: Employee, cfg: SimConfig, events: List[Event],
                      rng: random.Random) -> Tuple[List[WeekState], Optional[int]]:
    sim = EmployeeSim(emp, cfg, events, rng)
    states: List[WeekState] = []
    attrition_week: Optional[int] = None
    for w in range(cfg.n_weeks):
        if w < emp.hire_week:
            continue
        st = sim.step(w)
        states.append(st)
        if attrition_week is None and w >= 6 and rng.random() < sim.attrition_hazard(st):
            attrition_week = w
            break
    return states, attrition_week
