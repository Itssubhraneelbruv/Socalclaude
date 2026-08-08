"""Layer 0: 조직 컨텍스트 — 직원 배정과 조직/팀 레벨 이벤트.

이벤트를 조직·팀 레벨에서 주입하면 개인 간 상관이 '자연스럽게' 생긴다.
개인별로 독립 노이즈만 주면 팀 효과가 없는 비현실적 데이터가 된다.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import LEVELS, LEVEL_WEIGHTS, SimConfig, TEAMS, TeamSpec
from .personas import PERSONAS, PERSONA_TEAM_AFFINITY, Persona, PERSONA_BY_KEY


@dataclass
class Employee:
    employee_id: str
    team: str
    department: str
    level: str
    persona: str
    tenure_months: int
    is_manager: bool
    pto_entitlement_days: int
    hire_week: int          # 0이면 시작 시점부터 재직
    # 개인 고유 변동 (같은 페르소나여도 사람마다 다르게)
    jitter: Dict[str, float] = field(default_factory=dict)


@dataclass
class Event:
    key: str
    label: str
    scope: str              # "org" | "team"
    team: Optional[str]
    start_week: int
    end_week: int
    demand_delta: Dict[str, float] = field(default_factory=dict)
    resource_delta: Dict[str, float] = field(default_factory=dict)
    sentiment_shock: float = 0.0   # 즉각적인 감정 충격 (감쇠)


def build_employees(cfg: SimConfig, rng: random.Random) -> List[Employee]:
    team_capacity = {t.key: t.size for t in TEAMS}
    total_cap = sum(team_capacity.values())
    scale = cfg.n_employees / total_cap
    for k in team_capacity:
        team_capacity[k] = max(cfg.min_group_size, round(team_capacity[k] * scale))

    team_by_key = {t.key: t for t in TEAMS}
    slots: List[str] = []
    for k, n in team_capacity.items():
        slots.extend([k] * n)
    # 목표 인원에 맞게 조정
    while len(slots) > cfg.n_employees:
        slots.pop(rng.randrange(len(slots)))
    while len(slots) < cfg.n_employees:
        slots.append(rng.choice(list(team_capacity.keys())))
    rng.shuffle(slots)

    persona_pool: List[Persona] = []
    for p in PERSONAS:
        persona_pool.extend([p] * max(1, round(p.share * cfg.n_employees)))
    while len(persona_pool) < cfg.n_employees:
        persona_pool.append(PERSONA_BY_KEY["anchored"])
    persona_pool = persona_pool[: cfg.n_employees]
    rng.shuffle(persona_pool)

    # 팀 친화도를 반영해 페르소나를 재배치 (그리디 스왑)
    def affinity(p_key: str, t_key: str) -> float:
        return PERSONA_TEAM_AFFINITY.get(p_key, {}).get(t_key, 1.0)

    for _ in range(cfg.n_employees * 4):
        i, j = rng.randrange(cfg.n_employees), rng.randrange(cfg.n_employees)
        if i == j:
            continue
        cur = affinity(persona_pool[i].key, slots[i]) * affinity(persona_pool[j].key, slots[j])
        swp = affinity(persona_pool[i].key, slots[j]) * affinity(persona_pool[j].key, slots[i])
        if swp > cur:
            persona_pool[i], persona_pool[j] = persona_pool[j], persona_pool[i]

    employees: List[Employee] = []
    for idx in range(cfg.n_employees):
        t: TeamSpec = team_by_key[slots[idx]]
        p = persona_pool[idx]
        level = rng.choices(LEVELS, weights=LEVEL_WEIGHTS, k=1)[0]
        is_mgr = level in ("Manager",)
        tenure = int(max(2, rng.lognormvariate(3.2, 0.75)))
        hire_week = 0
        if tenure < 6 and rng.random() < 0.5:
            hire_week = rng.randrange(0, min(cfg.n_weeks, 20))
        employees.append(
            Employee(
                employee_id=f"E{1000 + idx}",
                team=t.key,
                department=t.department,
                level=level,
                persona=p.key,
                tenure_months=tenure,
                is_manager=is_mgr,
                pto_entitlement_days=15 + (5 if tenure > 36 else 0),
                hire_week=hire_week,
                # 같은 페르소나여도 사람마다 다르게 무너진다.
                # 이 분산이 좁으면 아키타입 전원이 똑같이 번아웃되는
                # 비현실적 데이터가 나온다.
                jitter={
                    "demand": rng.gauss(0, 0.10),
                    "resource": rng.gauss(0, 0.10),
                    "sensitivity": rng.gauss(1.0, 0.24),
                    "recovery": rng.gauss(1.0, 0.24),
                    "disclosure": rng.gauss(0, 0.10),
                    "hours": rng.gauss(0, 0.55),
                    "diligence": rng.gauss(0, 0.08),
                    "gain_exhaustion": rng.gauss(1.0, 0.18),
                    "gain_cynicism": rng.gauss(1.0, 0.18),
                    "gain_reduced_efficacy": rng.gauss(1.0, 0.18),
                },
            )
        )
    return employees


def build_events(cfg: SimConfig, rng: random.Random) -> List[Event]:
    """조직 전체 + 팀 단위 충격. 주차는 고정 시드 기반으로 흔들린다."""
    W = cfg.n_weeks
    events: List[Event] = []

    # 조직 개편 — 역할 모호성과 예측 불가능성이 튄다
    reorg = int(W * 0.45) + rng.randint(-2, 2)
    events.append(Event(
        "reorg", "Reorg announced", "org", None, reorg, reorg + 7,
        demand_delta={"role_ambiguity": 0.28, "unpredictability": 0.34, "context_switching": 0.12},
        resource_delta={"autonomy": -0.12, "growth_meaning": -0.10, "support_manager": -0.10},
        sentiment_shock=-0.35,
    ))

    # 감원 루머 — 심리적 안전감 붕괴. 요구는 안 늘어나는데 냉소가 오른다.
    layoff = int(W * 0.74) + rng.randint(-2, 2)
    events.append(Event(
        "layoff_rumor", "Layoff rumors spreading", "org", None, layoff, layoff + 5,
        demand_delta={"unpredictability": 0.42, "workload": 0.10},
        resource_delta={"reward_fairness": -0.20, "support_manager": -0.12, "growth_meaning": -0.16},
        sentiment_shock=-0.45,
    ))

    # 성과 리뷰 사이클 — 보상 공정성 인식이 갈린다
    for wk in (int(W * 0.22), int(W * 0.96)):
        events.append(Event(
            "perf_review", "Performance review cycle", "org", None, wk, wk + 3,
            demand_delta={"time_pressure": 0.14, "emotional_labor": 0.10},
            resource_delta={"reward_fairness": -0.10},
            sentiment_shock=-0.12,
        ))

    # 팀별 릴리즈 크런치 (엔지니어링/프로덕트에 집중)
    for t in TEAMS:
        n_crunch = 3 if t.department in ("Engineering", "Product") else 1
        for _ in range(n_crunch):
            s = rng.randrange(2, max(3, W - 5))
            events.append(Event(
                "release_crunch", f"{t.name} release crunch", "team", t.key, s, s + 2,
                demand_delta={"workload": 0.30, "time_pressure": 0.34, "context_switching": 0.14},
                resource_delta={"recovery_opportunity": -0.26},
                sentiment_shock=-0.10,
            ))

    # 매니저 교체 — 지지 자원이 무너졌다가 서서히 회복
    for t in rng.sample(TEAMS, 3):
        s = rng.randrange(4, max(5, W - 12))
        events.append(Event(
            "manager_change", f"{t.name} manager change", "team", t.key, s, s + 10,
            demand_delta={"role_ambiguity": 0.20, "unpredictability": 0.18},
            resource_delta={"support_manager": -0.34, "reward_fairness": -0.12},
            sentiment_shock=-0.22,
        ))

    # 동료 퇴사 — 남은 사람에게 업무가 넘어온다
    for t in TEAMS:
        for _ in range(rng.randint(1, 3)):
            s = rng.randrange(3, max(4, W - 8))
            events.append(Event(
                "peer_exit", f"{t.name} teammate departure", "team", t.key, s, s + 7,
                demand_delta={"workload": 0.22, "context_switching": 0.10},
                resource_delta={"support_peer": -0.16},
                sentiment_shock=-0.14,
            ))
    return events


def event_deltas(events: List[Event], team: str, week: int):
    """해당 (팀, 주차)에 활성화된 이벤트의 델타 합산 + 감정 충격."""
    d: Dict[str, float] = {}
    r: Dict[str, float] = {}
    shock = 0.0
    active: List[str] = []
    for e in events:
        if e.scope == "team" and e.team != team:
            continue
        if not (e.start_week <= week <= e.end_week):
            continue
        span = max(1, e.end_week - e.start_week)
        # 시작 시 최대, 이후 선형 감쇠 (조직은 적응한다)
        decay = 1.0 - 0.55 * ((week - e.start_week) / span)
        for k, v in e.demand_delta.items():
            d[k] = d.get(k, 0.0) + v * decay
        for k, v in e.resource_delta.items():
            r[k] = r.get(k, 0.0) + v * decay
        if week == e.start_week:
            shock += e.sentiment_shock
        active.append(e.key)
    return d, r, shock, active
