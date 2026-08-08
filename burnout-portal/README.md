# 번아웃 방지 포털 — 합성 데이터 생성기

스트레스·센티먼트를 측정하고 직원/HR에게 추천을 주는 포털을 만들기 위한
**시뮬레이션 기반 데이터셋**. 외부 의존성 없이 표준 라이브러리만 사용한다.

```bash
python3 -m generator
```

세 가지 형식으로 동시에 출력되고, 검증 리포트가 뒤따른다.

| 경로 | 내용 |
|---|---|
| `out/burnout.db` | SQLite. 뷰(`v_employee_week`, `v_hr_team_week`) 포함 |
| `out/csv/*.csv` | 테이블별 CSV |
| `out/json/*.json` | 테이블별 JSON 배열 (compact, `ensure_ascii=False`) |
| `out/json/_sample_employee.json` | **직원 1명의 52주를 전 계층 조인한 읽기용 샘플** (pretty print) |

```bash
python3 -m generator --seed 42 --employees 500 --weeks 104
```

| 옵션 | 설명 |
|---|---|
| `--seed` | 난수 시드. 같은 시드 = 바이트 단위로 동일한 데이터셋 |
| `--employees` / `--weeks` | 인원 / 기간 |
| `--no-anonymous` | 펄스를 기명으로 운영. 축소 보고 편향이 약 2배로 커진다 |
| `--out` | 출력 디렉터리 |

---

## 설계 원칙: 역방향 생성

관측치를 만들고 거기서 스트레스를 추정하는 게 아니라, **잠재 상태를 먼저
시뮬레이션하고 그로부터 관측 신호를 파생**시킨다. 정답을 알고 있어야
나중에 만들 스코어링 모델과 추천 엔진을 평가할 수 있다.

```
조직 컨텍스트 ──▶ 페르소나 파라미터 ──▶ 스트레스 드라이버
                                            │
                                            ▼
   포털이 보는 것 ◀── 관측 신호 ◀── 잠재 상태 (정답)
   (pulse, 텍스트,      (편향·결측       (exhaustion,
    행동 로그)           주입)            cynicism,
                                          reduced_efficacy)
```

| 파일 | 계층 | 역할 |
|---|---|---|
| `generator/config.py` | 0 | 시뮬레이션 설정, 드라이버 정의, 팀 스펙 |
| `generator/org.py` | 0 | 직원 배정, 조직/팀 이벤트 (개편·감원루머·크런치·매니저 교체) |
| `generator/personas.py` | 1 | 7종 아키타입의 파라미터 벡터 |
| `generator/dynamics.py` | 2–3 | 드라이버 시계열 + 잠재 상태 동역학 → **정답** |
| `generator/signals.py` | 4 | 관측 신호 + 편향·결측 주입 |
| `generator/text_ko.py` | 4 | 자유 서술 코멘트 (템플릿 + 어휘 변주) |
| `generator/validate.py` | — | 4종 검증 리포트 |
| `schema.sql` | — | 테이블·뷰. 접근 경계가 스키마에 박혀 있다 |

---

## 스트레스 결정 요인 (JD-R 모델)

**요구(Demands)** — 부담을 만드는 것
`workload` · `time_pressure` · `role_ambiguity` · `emotional_labor` ·
`context_switching` · `unpredictability`

**자원(Resources)** — 완충하는 것
`autonomy` · `support_manager` · `support_peer` · `reward_fairness` ·
`growth_meaning` · `recovery_opportunity`

자율성은 단순 자원이 아니라 **부하–긴장 관계의 조절 변수**로 들어간다 (Karasek):

```
strain = (demand_index − resource_index) × (1 − 0.35 × autonomy)
```

## 잠재 상태 (Maslach 3차원)

단일 "번아웃 점수" 하나로 뭉치지 않는다. 처방이 다르기 때문이다.

| 차원 | 의미 | 대응 처방 |
|---|---|---|
| `exhaustion` | 소진 | 부하 재조정, 회복 시간 |
| `cynicism` | 냉소·심리적 이탈 | 의미·인정 회복, 공정성 |
| `reduced_efficacy` | 효능감 저하 | 코칭, 역할 명확화 |

센티먼트는 별도 축(`valence` × `arousal`)이다. 번아웃 말기에는 각성이
오히려 떨어져 **저각성 부정 감정(무기력)** 패턴이 나타난다.

## 동역학의 핵심 4가지

- **히스테리시스** — `exhaustion > 0.70`을 넘으면 회복 계수가 45%로 떨어진다.
  한 번 무너지면 같은 조건에서도 안 돌아온다.
- **흉터(`scar`)** — 붕괴를 겪은 사람은 완전히 원래대로 돌아가지 않는다.
  소진의 바닥값이 올라가고 이후 부하에 더 민감해진다. 재발 예측의 핵심 변수라
  `truth_weekly_state.scar`로 정답에도 남긴다.
- **이벤트 쇼크** — 조직·팀 레벨에서 주입해 팀 단위 상관을 자연 발생시킨다.
- **주기성** — 분기말 압박, 여름 휴가철(남은 사람 부하 증가), 연말.

---

## 페르소나 7종

| 키 | 이름 | 비중 | 특징 |
|---|---|---|---|
| `overachiever` | 자발적 과부하형 | 12% | 자기 기준이 원인. **축소 보고**로 설문에 늦게 잡힘. 급성 붕괴 |
| `invisible` | 인정받지 못하는 기여자 | 13% | ERI 불균형. 냉소가 먼저. **이탈 위험 최고** |
| `caregiver` | 감정노동 돌봄형 | 12% | 감정 노동 누적. 효능감은 유지 |
| `ambiguous` | 역할 모호형 | 11% | **반례 A** — 업무량은 낮은데 스트레스는 높다 |
| `coaster` | 심리적 이탈형 | 7% | **반례 B** — 정시 퇴근하는 번아웃. 응답률 21% |
| `recovering` | 회복 궤적형 | 7% | 위험 상태에서 시작해 개입 후 회복. 추천 효과 검증용 |
| `anchored` | 안정형 | 38% | 건강한 다수. 조직 쇼크에도 견디는 대조군 |

4번·5번이 이 데이터셋의 핵심이다. 이들이 없으면 "야근 시간 = 번아웃"이라는
순진한 모델이 만들어지고, 실제 배포 시 조용히 무너진다.

---

## 의도적으로 주입한 '지저분함'

깨끗한 합성 데이터는 쓸모가 없다. 다음은 전부 의도된 것이다.

| 현상 | 구현 | 효과 |
|---|---|---|
| **정보성 결측** | 응답 확률 = `0.90 − 0.50·E − 0.32·C` | stage0 78% → stage3 20% 응답률. 침묵 자체가 가장 강한 신호 |
| **사회적 바람직성 편향** | `disclosure_bias`, 익명이면 0.55배 | 과부하형은 실제로 소진된 주에도 `q_energy`를 +0.5점 높게 답한다 |
| **응답 스타일** | `central`(중앙 몰림) / `extreme` | 리커트 척도 보정 없이는 개인 비교가 불가능 |
| **대리지표의 배신** | `presence_decay`, `overwork_tendency` | 근무시간↔번아웃 전체 상관 r = +0.02 |
| **휴가 미사용·취소** | 잔여일수를 남은 기간에 배분하되 상한을 둠. 크런치 중 55% 확률로 취소 | 안정형은 15일 중 15.0일 사용, 과부하형은 0.8일 사용에 15.3일 미사용 — **미사용 잔여 자체가 회복 실패 신호** |

---

## 검증 (`python3 -m generator` 실행 시 자동 출력)

```
1. 분포 sanity
  [PASS] 시점 유병률 (직원-주 stage>=2): 20.8%  [기준 20~30%]
  [PASS] 연간 발생률 (1회 이상 stage>=2): 42.8%
  [PASS] 심각(stage>=3) 연간 발생률: 14.4%  [참고 5~16%]
  [PASS] 연간 이탈률: 12.0%

2. 알려진 상관 재현
  [PASS] 자원지수 ↔ 긴장   r = -0.76
  [PASS] 자원지수 ↔ 냉소   r = -0.71
  [PASS] 요구지수 ↔ 소진   r = +0.43
  [PASS] 응답률: stage0=78% stage1=50% stage2=35% stage3=18%
  축소 보고: 자발적 과부하형 관측 2.70 / 기대 2.19 / 편차 +0.51

4. 순진한 베이스라인의 실패 확인
   전체:  근무시간 ↔ 번아웃  r = +0.02
   역할 모호형   r = -0.02  <- 반례
   심리적 이탈형  r = -0.04  <- 반례
```

심각(stage>=3) 연간 발생률 14.4%는 참고 범위의 상단이다. 낮추려면
`personas.py`의 `dim_gain["exhaustion"]`을 내리면 된다 —
페르소나 비중을 건드리면 시점 유병률이 같이 무너진다.

`peak_stage`는 **3주 이상 지속된** 최고 단계로 정의한다. 번아웃은 '나쁜 한 주'가
아니라 지속 상태이고, 최댓값 통계는 노이즈를 과대평가하기 때문이다.

---

## 프라이버시 경계 (스키마에 내장)

이 포털은 감시 도구로 변질되기 가장 쉬운 종류다. 접근 경계를 애플리케이션이
아니라 **스키마에** 박아뒀다.

| 대상 | 접근 |
|---|---|
| `truth_*` 테이블 | **모델 평가 전용.** 운영 포털은 절대 읽지 않는다 |
| `v_employee_week` | 개인 뷰. 애플리케이션에서 본인 `employee_id`를 반드시 바인딩 |
| `v_hr_team_week` | 팀×주 집계만. **응답자 5명 미만 그룹은 뷰가 행을 반환하지 않는다** |

HR에게 개인 단위 번아웃 점수를 노출하는 순간 직원은 설문에 솔직하게 답하지
않고, 데이터 자체가 죽는다. `disclosure_bias` 파라미터가 시뮬레이션하는 게
정확히 그 현상이다.

---

## 데이터 규모 (기본 설정)

| 테이블 | 행 수 | 주기 |
|---|---|---|
| `employee` | 250 | — |
| `truth_weekly_state` | ~12,400 | 주간 (정답) |
| `pulse_response` | ~12,400 | 주간 (약 65%가 실제 응답) |
| `pulse_comment` | ~2,500 | 격주, 응답률 낮음 |
| `behavior_daily` | ~86,600 | 일간 |
| `weekly_signal` | ~12,400 | 주간 |
| `enps_response` | ~940 | 분기 |

---

## 쿼리 예시

```sql
-- 페르소나별 프로파일 (정답 기준)
SELECT t.persona_name_ko, COUNT(DISTINCT t.employee_id) n,
       ROUND(AVG(s.exhaustion),2) 소진, ROUND(AVG(s.cynicism),2) 냉소,
       ROUND(AVG(s.reduced_efficacy),2) 효능저하
FROM truth_employee t JOIN truth_weekly_state s USING(employee_id)
GROUP BY t.persona_key ORDER BY 소진 DESC;
```

```sql
-- 이탈 8주 전에 어떤 신호가 먼저 움직였나
SELECT s.weeks_to_attrition,
       ROUND(AVG(s.cynicism),2) 냉소, ROUND(AVG(p.responded),2) 응답률,
       ROUND(AVG(w.one_on_one_attended),2) 원온원참석
FROM truth_weekly_state s
JOIN pulse_response p USING(employee_id, week)
JOIN weekly_signal  w USING(employee_id, week)
WHERE s.weeks_to_attrition BETWEEN 0 AND 12
GROUP BY s.weeks_to_attrition ORDER BY s.weeks_to_attrition DESC;
```

```sql
-- 추천 엔진 평가 정답지: 지금 이 사람에게 작동 중인 드라이버
SELECT employee_id, week, burnout_stage, top_drivers
FROM truth_weekly_state WHERE burnout_stage >= 2 LIMIT 20;
```

---

## 다음 단계

1. **스코어링 모델** — 관측 신호만으로 3차원 잠재 상태를 복원. `truth_weekly_state`로 채점.
2. **추천 엔진** — 추정된 드라이버에 처방을 매핑. `top_drivers`가 정답지.
3. **포털 UI** — 개인 뷰 / HR 집계 뷰. 접근 경계는 이미 스키마에 있다.

모델을 만들 때 반드시 지킬 것: **학습·평가 모두 `truth_*`를 피처로 쓰지 말 것.**
정답지를 피처로 넣으면 검증이 통째로 무의미해진다.
