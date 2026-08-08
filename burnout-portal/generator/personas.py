"""페르소나 = 시뮬레이션 파라미터 벡터.

'성격 묘사'가 아니라 동역학 계수의 묶음이다. 각 아키타입은
  (1) 드라이버 베이스라인을 어떻게 밀어내는가
  (2) 같은 부하에 얼마나 민감한가 / 얼마나 회복하는가
  (3) 잠재 상태 3차원 중 무엇이 먼저 오르는가
  (4) 관측 신호에 어떤 편향을 넣는가
로 정의된다.

주의: 4번(Ambiguous Role)과 5번(Disengaged Coaster)은 의도적인 반례다.
'야근 시간 = 번아웃'이라는 순진한 모델을 반드시 실패하게 만든다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Persona:
    key: str
    name_ko: str
    name_en: str
    share: float                      # 인구 비중

    # (1) 드라이버 이동량 (팀/직급 베이스라인에 가산, -0.3..0.3 범위 권장)
    demand_shift: Dict[str, float] = field(default_factory=dict)
    resource_shift: Dict[str, float] = field(default_factory=dict)

    # (2) 동역학
    sensitivity: float = 1.0          # 부하 -> 소진 축적 배율
    recovery_rate: float = 1.0        # 회복 배율
    detachment: float = 0.5           # 심리적 분리 능력 0..1

    # (3) 차원별 이득 (어느 축이 먼저 오르는가)
    dim_gain: Dict[str, float] = field(default_factory=dict)
    init_state: Dict[str, float] = field(default_factory=dict)

    # (4) 관측 편향
    disclosure_bias: float = 0.0      # +면 실제보다 긍정적으로 응답 (축소 보고)
    response_style: str = "normal"    # normal | central | extreme
    survey_diligence: float = 0.0     # 응답률 개인 성향 보정
    overwork_tendency: float = 0.0    # 요구와 무관한 자발적 초과근무 (-1..1)
    presence_decay: float = 0.0       # 냉소 시 근무시간이 오히려 줄어드는 정도

    trajectory: str = "stable"        # stable|acute|chronic|volatile|recovery|flat_disengaged
    attrition_gain: float = 1.0
    voice: str = "neutral"            # 텍스트 템플릿 보이스 키
    note: str = ""


PERSONAS: List[Persona] = [
    Persona(
        key="overachiever",
        name_ko="자발적 과부하형",
        name_en="The Overachiever",
        share=0.12,
        demand_shift={"workload": 0.18, "time_pressure": 0.15, "context_switching": 0.08},
        resource_shift={"recovery_opportunity": -0.22, "autonomy": 0.08, "growth_meaning": 0.10},
        sensitivity=1.15, recovery_rate=0.62, detachment=0.22,
        dim_gain={"exhaustion": 1.14, "cynicism": 0.75, "reduced_efficacy": 0.85},
        init_state={"exhaustion": 0.30, "cynicism": 0.12, "reduced_efficacy": 0.10},
        disclosure_bias=0.50,          # "괜찮다"고 답한다 — 가장 위험한 편향
        response_style="central", survey_diligence=0.10,
        overwork_tendency=0.75, trajectory="acute", attrition_gain=0.9,
        voice="stoic",
        note="요구가 아니라 자기 기준이 원인. 급성 붕괴형. 설문으로는 늦게 잡힌다.",
    ),
    Persona(
        key="invisible",
        name_ko="인정받지 못하는 기여자",
        name_en="The Invisible Contributor",
        share=0.13,
        demand_shift={"workload": 0.05, "role_ambiguity": 0.06},
        resource_shift={"reward_fairness": -0.30, "growth_meaning": -0.20, "support_manager": -0.14},
        sensitivity=0.90, recovery_rate=0.95, detachment=0.58,
        dim_gain={"exhaustion": 0.80, "cynicism": 1.32, "reduced_efficacy": 1.05},
        init_state={"exhaustion": 0.20, "cynicism": 0.26, "reduced_efficacy": 0.18},
        disclosure_bias=-0.12,
        response_style="normal", survey_diligence=0.05,
        overwork_tendency=0.05, trajectory="chronic", attrition_gain=1.6,
        voice="resentful",
        note="ERI 불균형. 부하는 보통인데 냉소가 먼저 오른다. 이탈 위험 최고.",
    ),
    Persona(
        key="caregiver",
        name_ko="감정노동 돌봄형",
        name_en="The Caregiver",
        share=0.12,
        demand_shift={"emotional_labor": 0.26, "workload": 0.10, "context_switching": 0.10},
        resource_shift={"recovery_opportunity": -0.15, "growth_meaning": 0.12, "support_peer": 0.10},
        sensitivity=0.95, recovery_rate=0.95, detachment=0.32,
        dim_gain={"exhaustion": 0.95, "cynicism": 0.95, "reduced_efficacy": 0.70},
        init_state={"exhaustion": 0.26, "cynicism": 0.14, "reduced_efficacy": 0.10},
        disclosure_bias=0.20,
        response_style="normal", survey_diligence=0.12,
        overwork_tendency=0.20, trajectory="chronic", attrition_gain=1.2,
        voice="depleted",
        note="효능감은 유지되나 소진이 누적. CS/매니저 직군에 몰린다.",
    ),
    Persona(
        key="ambiguous",
        name_ko="역할 모호형",
        name_en="The Ambiguous Role",
        share=0.11,
        demand_shift={"role_ambiguity": 0.32, "unpredictability": 0.26, "workload": -0.10},
        resource_shift={"autonomy": -0.22, "growth_meaning": -0.12},
        sensitivity=1.05, recovery_rate=0.88, detachment=0.45,
        dim_gain={"exhaustion": 0.95, "cynicism": 1.15, "reduced_efficacy": 1.50},
        init_state={"exhaustion": 0.18, "cynicism": 0.18, "reduced_efficacy": 0.28},
        disclosure_bias=-0.05,
        response_style="extreme", survey_diligence=-0.05,
        overwork_tendency=-0.15, trajectory="volatile", attrition_gain=1.3,
        voice="confused",
        note="반례 A: 업무량은 오히려 낮은데 스트레스는 높다. 근무시간 기반 모델이 놓친다.",
    ),
    Persona(
        key="coaster",
        name_ko="심리적 이탈형",
        name_en="The Disengaged Coaster",
        share=0.07,
        demand_shift={"workload": -0.14, "time_pressure": -0.12},
        resource_shift={"growth_meaning": -0.34, "reward_fairness": -0.20, "support_manager": -0.18},
        sensitivity=0.55, recovery_rate=1.10, detachment=0.85,
        dim_gain={"exhaustion": 0.52, "cynicism": 1.12, "reduced_efficacy": 1.35},
        init_state={"exhaustion": 0.26, "cynicism": 0.52, "reduced_efficacy": 0.48},
        disclosure_bias=-0.10,
        response_style="central", survey_diligence=-0.35,
        overwork_tendency=-0.55, presence_decay=0.6,
        trajectory="flat_disengaged", attrition_gain=1.6,
        voice="flat",
        note="반례 B: 스트레스 지표는 낮은데 냉소·효능감은 바닥. 정시 퇴근하는 번아웃.",
    ),
    Persona(
        key="recovering",
        name_ko="회복 궤적형",
        name_en="The Recovering",
        share=0.07,
        demand_shift={"workload": 0.12, "time_pressure": 0.10},
        resource_shift={"support_manager": 0.16, "recovery_opportunity": 0.10},
        sensitivity=1.00, recovery_rate=1.25, detachment=0.55,
        dim_gain={"exhaustion": 1.10, "cynicism": 0.90, "reduced_efficacy": 0.90},
        init_state={"exhaustion": 0.72, "cynicism": 0.55, "reduced_efficacy": 0.45},
        disclosure_bias=0.05,
        response_style="normal", survey_diligence=0.15,
        overwork_tendency=0.10, trajectory="recovery", attrition_gain=0.7,
        voice="cautious",
        note="개입 이후 회복. 추천 엔진의 효과를 검증할 수 있는 유일한 그룹.",
    ),
    Persona(
        key="anchored",
        name_ko="안정형",
        name_en="The Anchored",
        share=0.38,
        demand_shift={},
        resource_shift={"autonomy": 0.14, "support_peer": 0.12, "recovery_opportunity": 0.18,
                        "growth_meaning": 0.10},
        sensitivity=0.70, recovery_rate=1.30, detachment=0.78,
        dim_gain={"exhaustion": 0.70, "cynicism": 0.65, "reduced_efficacy": 0.65},
        init_state={"exhaustion": 0.16, "cynicism": 0.10, "reduced_efficacy": 0.10},
        disclosure_bias=0.0,
        response_style="normal", survey_diligence=0.05,
        overwork_tendency=0.0, trajectory="stable", attrition_gain=0.5,
        voice="steady",
        note="건강한 다수. 유병률을 현실 범위로 맞추고, 조직 쇼크에도 견디는 대조군.",
    ),
]

PERSONA_BY_KEY = {p.key: p for p in PERSONAS}

# 페르소나별로 잘 맞는 팀 (배정 시 가중치로 사용)
PERSONA_TEAM_AFFINITY = {
    "caregiver": {"cs": 3.0, "sales": 1.6, "ops": 1.4},
    "ambiguous": {"pm": 2.4, "des": 1.6, "ops": 1.3},
    "overachiever": {"prod": 2.0, "plat": 1.5, "sales": 1.4},
    "invisible": {"plat": 1.5, "data": 1.4, "ops": 1.4},
    "coaster": {"ops": 1.4, "cs": 1.3},
    "recovering": {},
    "anchored": {},
}
