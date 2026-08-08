"""자유 서술 코멘트 생성 — 템플릿 + 어휘 변주.

구조: [도입] + [드라이버 언급] + [상태 서술] + [마무리]
각 조각은 페르소나 보이스와 잠재 상태에 따라 풀이 달라진다.
생성과 동시에 정답 라벨(감정 극성, 지배 차원, 언급 드라이버)을 함께 뱉는다.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

# --- 도입 -------------------------------------------------------------------
OPENERS = {
    "pos": ["이번 주는", "요즘은", "최근 몇 주는", "지난주부터"],
    "neu": ["이번 주는", "특별한 건 없는데", "요즘", "그냥"],
    "neg": ["솔직히 말하면", "이번 주는", "요즘 계속", "말하기 조심스럽지만"],
    "sev": ["더 이상 못 버티겠습니다.", "솔직히 한계입니다.", "이제는 정말", "쓰기도 지치지만"],
}

# --- 드라이버 언급 ----------------------------------------------------------
DRIVER_CLAUSES: Dict[str, List[str]] = {
    "workload": [
        "쳐내야 할 일이 계속 쌓입니다",
        "일이 줄어들 기미가 안 보입니다",
        "처리량 자체가 감당 범위를 넘었습니다",
        "받은 일 중 절반도 못 끝냈습니다",
    ],
    "time_pressure": [
        "마감이 겹쳐서 숨 돌릴 틈이 없습니다",
        "일정이 너무 촉박하게 잡힙니다",
        "항상 쫓기면서 일하는 느낌입니다",
        "제대로 검토할 시간 없이 넘기고 있습니다",
    ],
    "role_ambiguity": [
        "제가 뭘 책임지는 사람인지 모르겠습니다",
        "기대치가 명확하지 않습니다",
        "누가 결정하는지가 매번 다릅니다",
        "제 역할 범위가 계속 바뀝니다",
    ],
    "emotional_labor": [
        "고객 응대에서 감정이 많이 소모됩니다",
        "화난 사람을 계속 상대하는 게 힘듭니다",
        "괜찮은 척하는 데 에너지를 다 씁니다",
        "감정을 눌러가며 응대하고 있습니다",
    ],
    "context_switching": [
        "회의가 하루를 조각내서 집중할 시간이 없습니다",
        "컨텍스트 전환이 너무 잦습니다",
        "한 가지를 끝내기 전에 다른 게 들어옵니다",
        "몰입할 블록이 아예 안 남습니다",
    ],
    "unpredictability": [
        "우선순위가 주마다 뒤집힙니다",
        "다음 달에 뭐가 어떻게 될지 모르겠습니다",
        "계획을 세워도 소용이 없습니다",
        "공지가 갑자기 내려옵니다",
    ],
    "lack_of_autonomy": [
        "제가 결정할 수 있는 게 거의 없습니다",
        "방식까지 정해져서 내려옵니다",
        "실행만 하는 역할로 느껴집니다",
    ],
    "lack_of_support_manager": [
        "매니저와 이야기할 기회가 거의 없습니다",
        "막혔을 때 도와줄 사람이 없습니다",
        "1:1이 계속 취소됩니다",
    ],
    "lack_of_support_peer": [
        "팀에서 혼자 떠안는 느낌입니다",
        "물어볼 사람이 마땅치 않습니다",
        "다들 각자 바빠서 도움 요청을 못 하겠습니다",
    ],
    "lack_of_reward_fairness": [
        "한 만큼 인정받는다는 느낌이 없습니다",
        "성과가 다른 사람 이름으로 올라갑니다",
        "평가 기준이 납득이 안 됩니다",
        "누가 봐도 제 몫이었는데 언급이 없었습니다",
    ],
    "lack_of_growth_meaning": [
        "이 일이 어디로 가는지 모르겠습니다",
        "배우는 게 없다는 생각이 듭니다",
        "제가 여기 있는 이유를 모르겠습니다",
    ],
    "lack_of_recovery_opportunity": [
        "주말에도 알림을 확인하게 됩니다",
        "휴가를 잡았다가 결국 취소했습니다",
        "퇴근하고도 일 생각이 안 끊깁니다",
    ],
}

# --- 상태 서술 (지배 차원 × 강도) -------------------------------------------
STATE_CLAUSES: Dict[str, Dict[str, List[str]]] = {
    "exhaustion": {
        "mid": ["피로가 잘 안 풀립니다", "주말에도 회복이 덜 됩니다", "체력이 예전 같지 않습니다"],
        "high": ["아침에 일어나는 것부터 버겁습니다", "번아웃이라는 단어가 계속 떠오릅니다",
                 "잠을 자도 개운하지 않습니다", "몸이 먼저 신호를 보내는 것 같습니다"],
    },
    "cynicism": {
        "mid": ["예전만큼 마음이 안 갑니다", "회의에서 말을 아끼게 됩니다",
                "기대를 접는 게 편하다는 걸 배웠습니다"],
        "high": ["솔직히 이제 관심이 없습니다", "잘 되든 안 되든 상관없어졌습니다",
                 "다른 곳을 보고 있습니다", "기대하지 않는 편이 낫다고 생각합니다"],
    },
    "reduced_efficacy": {
        "mid": ["제가 잘하고 있는 건지 모르겠습니다", "성과가 눈에 안 보입니다",
                "판단에 자신이 없어집니다"],
        "high": ["제가 여기서 쓸모가 있는지 의문입니다", "뭘 해도 나아지지 않는 느낌입니다",
                 "실수가 늘고 있습니다"],
    },
}

POSITIVE_STATE = [
    "이번 스프린트는 흐름이 좋았습니다",
    "팀에서 도움을 많이 받았습니다",
    "오랜만에 제대로 집중할 수 있었습니다",
    "일정이 여유로워서 숨을 돌렸습니다",
    "피드백을 받고 방향이 명확해졌습니다",
    "맡은 일이 손에 잘 붙었습니다",
    "협업이 매끄러웠습니다",
    "쉬는 시간을 제대로 챙길 수 있었습니다",
]

NEUTRAL_STATE = [
    "특별히 좋지도 나쁘지도 않았습니다",
    "평소와 비슷하게 흘러갔습니다",
    "그럭저럭 굴러가고 있습니다",
    "무난하게 지나갔습니다",
    "크게 달라진 건 없습니다",
]

# 강도 부사 — 같은 문장을 재사용해도 표면형이 갈라진다
INTENSIFIERS = {
    "mid": ["", "", "조금 ", "약간 ", "요즘 "],
    "high": ["", "정말 ", "계속 ", "요즘 들어 ", "솔직히 "],
}

# --- 보이스별 마무리 --------------------------------------------------------
CLOSERS = {
    "stoic": ["그래도 이번 주만 넘기면 됩니다.", "일단은 할 만합니다.", "제가 더 챙기면 되는 부분입니다.",
              "크게 문제될 정도는 아닙니다."],
    "resentful": ["이런 얘기를 몇 번째 쓰는지 모르겠습니다.", "바뀔 거라 기대하진 않습니다.",
                  "적어봐야 달라지는 게 없더군요.", "누군가는 알고 있어야 할 것 같아 남깁니다."],
    "depleted": ["조금만 쉴 수 있으면 좋겠습니다.", "다음 주엔 나아지길 바랍니다.",
                 "지금은 채울 곳이 없습니다."],
    "confused": ["어디에 물어봐야 할지도 모르겠습니다.", "정리가 한 번 필요할 것 같습니다.",
                 "이게 정상인지 확인받고 싶습니다."],
    "flat": ["특별히 할 말은 없습니다.", "그렇습니다.", "이상입니다."],
    "cautious": ["조심스럽지만 나아지고 있는 것 같습니다.", "지난달보다는 낫습니다.",
                 "이 흐름이 유지되면 좋겠습니다."],
    "steady": ["전반적으로 괜찮습니다.", "지금 페이스면 문제없습니다.", "특별한 요청은 없습니다."],
    "neutral": ["이상입니다.", "참고 부탁드립니다."],
}

DRIVER_CONNECT = ["", "그리고 ", "여기에 ", "무엇보다 "]

# 낙관적 보이스(cautious/steady)의 마무리는 '심각' 코멘트와 모순된다.
# 그럴 땐 이 풀로 대체한다.
SEV_FALLBACK_CLOSERS = ["이대로는 어렵습니다.", "도움이 필요합니다.",
                        "한 번 상의하고 싶습니다.", "혼자 감당이 안 됩니다."]

# 이미 부사로 시작하는 문장에는 강도 부사를 겹쳐 붙이지 않는다
_ADV_PREFIXES = ("솔직히", "정말", "계속", "요즘")


def _intensify(rng: random.Random, clause: str, level: str) -> str:
    if clause.startswith(_ADV_PREFIXES):
        return clause
    return rng.choice(INTENSIFIERS[level]) + clause


def _closer(rng: random.Random, voice: str, bucket: str) -> str:
    if bucket == "sev" and voice in ("cautious", "steady"):
        return rng.choice(SEV_FALLBACK_CLOSERS)
    return rng.choice(CLOSERS.get(voice, CLOSERS["neutral"]))


def _valence_bucket(valence: float, composite: float) -> str:
    if composite >= 0.72 or valence <= -0.60:
        return "sev"
    if valence <= -0.15:
        return "neg"
    if valence >= 0.45:
        return "pos"
    return "neu"


def generate_comment(rng: random.Random, voice: str, valence: float, composite: float,
                     dims: Dict[str, float], top_drivers: List[str]) -> Tuple[str, Dict]:
    """코멘트 1건과 그 정답 라벨을 만든다."""
    bucket = _valence_bucket(valence, composite)
    dominant = max(dims.items(), key=lambda kv: kv[1])[0]
    dom_val = dims[dominant]

    parts: List[str] = []
    mentioned: List[str] = []

    if bucket == "pos":
        parts.append(rng.choice(OPENERS["pos"]) + " " + rng.choice(POSITIVE_STATE) + ".")
        if rng.random() < 0.3 and top_drivers:
            k = top_drivers[0]
            if k in DRIVER_CLAUSES:
                parts.append("다만 " + rng.choice(DRIVER_CLAUSES[k]) + ".")
                mentioned.append(k)
        parts.append(_closer(rng, voice, bucket))
    elif bucket == "neu":
        parts.append(rng.choice(OPENERS["neu"]) + " " + rng.choice(NEUTRAL_STATE) + ".")
        if top_drivers and rng.random() < 0.55:
            k = top_drivers[0]
            if k in DRIVER_CLAUSES:
                parts.append(rng.choice(DRIVER_CLAUSES[k]) + ".")
                mentioned.append(k)
        if rng.random() < 0.6:
            parts.append(_closer(rng, voice, bucket))
    else:
        opener = rng.choice(OPENERS[bucket])
        n_drivers = 1 if bucket == "neg" else rng.choice([1, 2, 2])
        picked = [k for k in top_drivers if k in DRIVER_CLAUSES][:n_drivers]
        if picked:
            head = rng.choice(DRIVER_CLAUSES[picked[0]])
            parts.append(f"{opener} {head}." if not opener.endswith(".") else f"{opener} {head}.")
            mentioned.append(picked[0])
            for k in picked[1:]:
                parts.append(rng.choice(DRIVER_CONNECT[1:]) + rng.choice(DRIVER_CLAUSES[k]) + ".")
                mentioned.append(k)
        else:
            parts.append(opener if opener.endswith(".") else opener + " 힘듭니다.")

        level = "high" if dom_val >= 0.6 else "mid"
        parts.append(_intensify(rng, rng.choice(STATE_CLAUSES[dominant][level]), level) + ".")
        # 2순위 차원이 함께 높으면 한 문장 더 붙는다
        second = sorted(dims.items(), key=lambda kv: kv[1], reverse=True)[1]
        if second[1] >= 0.45 and rng.random() < 0.4:
            lv2 = "high" if second[1] >= 0.6 else "mid"
            parts.append(rng.choice(STATE_CLAUSES[second[0]][lv2]) + ".")
        # 축소 보고형(stoic)은 부정 서술 뒤에 방어적 마무리를 붙인다
        parts.append(_closer(rng, voice, bucket))

    text = " ".join(p.strip() for p in parts if p.strip())
    label = {
        "sentiment_bucket": bucket,
        "dominant_dimension": dominant,
        "mentioned_drivers": ",".join(mentioned),
        "voice": voice,
    }
    return text, label
