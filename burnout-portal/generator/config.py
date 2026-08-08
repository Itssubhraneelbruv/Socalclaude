"""시뮬레이션 전역 설정.

모든 무작위성은 SEED 하나로 결정된다. 같은 SEED = 같은 데이터셋.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SimConfig:
    seed: int = 20260808
    n_employees: int = 250
    n_weeks: int = 52
    start_date: dt.date = dt.date(2025, 1, 6)  # 월요일

    # 설문 운영 정책
    pulse_every_weeks: int = 1
    comment_every_weeks: int = 2
    enps_weeks: tuple = (13, 26, 39, 52)
    anonymous_pulse: bool = True  # 익명이면 사회적 바람직성 편향이 줄어든다

    # HR 뷰 최소 집계 인원 (k-익명성). 스키마·뷰에 박아둔다.
    min_group_size: int = 5

    lang: str = "en"          # 코멘트 텍스트 언어: en | ko

    out_dir: str = "out"


# --- 스트레스 드라이버 정의 (JD-R 모델) -------------------------------------
# demand: 높을수록 부담. resource: 높을수록 완충.
DEMANDS: List[str] = [
    "workload",           # 업무량
    "time_pressure",      # 시간 압박
    "role_ambiguity",     # 역할 모호성
    "emotional_labor",    # 감정 노동
    "context_switching",  # 컨텍스트 스위칭 / 회의 파편화
    "unpredictability",   # 예측 불가능성
]

RESOURCES: List[str] = [
    "autonomy",             # 자율성 / 통제감
    "support_manager",      # 매니저 지지
    "support_peer",         # 동료 지지
    "reward_fairness",      # 보상·인정의 공정성 (ERI)
    "growth_meaning",       # 성장·의미감
    "recovery_opportunity", # 회복 기회 (심리적 분리)
]

# 종합 지수를 만들 때의 가중치 (합 = 1)
DEMAND_WEIGHTS: Dict[str, float] = {
    "workload": 0.26,
    "time_pressure": 0.24,
    "role_ambiguity": 0.15,
    "emotional_labor": 0.13,
    "context_switching": 0.12,
    "unpredictability": 0.10,
}

RESOURCE_WEIGHTS: Dict[str, float] = {
    "autonomy": 0.22,
    "support_manager": 0.20,
    "support_peer": 0.14,
    "reward_fairness": 0.18,
    "growth_meaning": 0.14,
    "recovery_opportunity": 0.12,
}

# --- 잠재 상태 (Maslach 3차원) ----------------------------------------------
DIMENSIONS = ("exhaustion", "cynicism", "reduced_efficacy")

# burnout_stage 컷오프 (composite 기준)
STAGE_CUTOFFS = (0.35, 0.58, 0.80)

# composite = 가중합. 소진에 가장 큰 가중.
COMPOSITE_WEIGHTS = {"exhaustion": 0.45, "cynicism": 0.35, "reduced_efficacy": 0.20}


@dataclass
class TeamSpec:
    key: str
    name: str
    department: str
    size: int
    manager_quality: float      # 0..1 -> support_manager 베이스
    workload_baseline: float    # 0..1
    meeting_density: float      # 0..1 -> context_switching
    emotional_labor_base: float # 0..1 (CS/영업 높음)
    autonomy_base: float        # 0..1
    reward_fairness_base: float # 0..1


TEAMS: List[TeamSpec] = [
    TeamSpec("plat",  "Platform Engineering", "Engineering", 34, 0.72, 0.62, 0.38, 0.10, 0.74, 0.62),
    TeamSpec("prod",  "Product Engineering",  "Engineering", 42, 0.55, 0.74, 0.55, 0.15, 0.58, 0.48),
    TeamSpec("data",  "Data & ML",            "Engineering", 22, 0.68, 0.58, 0.42, 0.12, 0.70, 0.58),
    TeamSpec("des",   "Design",               "Product",     18, 0.63, 0.55, 0.60, 0.22, 0.62, 0.44),
    TeamSpec("pm",    "Product Management",   "Product",     20, 0.48, 0.70, 0.78, 0.35, 0.52, 0.50),
    TeamSpec("cs",    "Customer Support",     "GTM",         46, 0.44, 0.72, 0.35, 0.82, 0.30, 0.36),
    TeamSpec("sales", "Sales",                "GTM",         38, 0.58, 0.68, 0.62, 0.66, 0.55, 0.66),
    TeamSpec("ops",   "People & Ops",         "G&A",         30, 0.66, 0.52, 0.58, 0.48, 0.58, 0.52),
]

LEVELS = ["IC1", "IC2", "IC3", "IC4", "Lead", "Manager"]
LEVEL_WEIGHTS = [0.16, 0.26, 0.22, 0.14, 0.12, 0.10]
