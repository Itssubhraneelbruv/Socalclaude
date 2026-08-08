-- 번아웃 방지 포털 — 합성 데이터 스키마
--
-- 경계 원칙:
--   portal_*  : 포털이 읽어도 되는 관측 데이터
--   truth_*   : 시뮬레이션 정답. 모델 평가 전용. 운영 포털은 절대 읽지 않는다.
--   v_hr_*    : HR 뷰. 최소 인원(k) 미만 그룹은 뷰 레벨에서 잘라낸다.

PRAGMA foreign_keys = ON;

DROP VIEW  IF EXISTS v_hr_team_week;
DROP VIEW  IF EXISTS v_employee_week;
DROP TABLE IF EXISTS truth_weekly_state;
DROP TABLE IF EXISTS truth_employee;
DROP TABLE IF EXISTS enps_response;
DROP TABLE IF EXISTS pulse_comment;
DROP TABLE IF EXISTS pulse_response;
DROP TABLE IF EXISTS behavior_daily;
DROP TABLE IF EXISTS weekly_signal;
DROP TABLE IF EXISTS org_event;
DROP TABLE IF EXISTS employee;
DROP TABLE IF EXISTS team;

CREATE TABLE team (
    team_key        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    department      TEXT NOT NULL,
    headcount       INTEGER NOT NULL
);

CREATE TABLE employee (
    employee_id     TEXT PRIMARY KEY,
    team_key        TEXT NOT NULL REFERENCES team(team_key),
    department      TEXT NOT NULL,
    level           TEXT NOT NULL,
    tenure_months   INTEGER NOT NULL,
    is_manager      INTEGER NOT NULL,
    hire_week       INTEGER NOT NULL,
    pto_entitlement_days INTEGER NOT NULL
);

CREATE TABLE org_event (
    event_id        INTEGER PRIMARY KEY,
    event_key       TEXT NOT NULL,
    label           TEXT NOT NULL,
    scope           TEXT NOT NULL,          -- org | team
    team_key        TEXT,
    start_week      INTEGER NOT NULL,
    end_week        INTEGER NOT NULL
);

-- 주간 펄스 설문. responded=0 이면 문항이 전부 NULL (정보성 결측)
CREATE TABLE pulse_response (
    employee_id     TEXT NOT NULL REFERENCES employee(employee_id),
    week            INTEGER NOT NULL,
    responded       INTEGER NOT NULL,
    is_anonymous    INTEGER NOT NULL,
    q_workload      INTEGER,
    q_energy        INTEGER,
    q_engagement    INTEGER,
    q_efficacy      INTEGER,
    q_support       INTEGER,
    q_recognition   INTEGER,
    q_mood          INTEGER,
    completion_seconds INTEGER,
    PRIMARY KEY (employee_id, week)
);

CREATE TABLE pulse_comment (
    employee_id     TEXT NOT NULL REFERENCES employee(employee_id),
    week            INTEGER NOT NULL,
    text            TEXT NOT NULL,
    char_len        INTEGER NOT NULL,
    label_sentiment_bucket   TEXT NOT NULL,   -- 정답 라벨 (NLP 평가용)
    label_dominant_dimension TEXT NOT NULL,
    label_mentioned_drivers  TEXT,
    PRIMARY KEY (employee_id, week)
);

CREATE TABLE behavior_daily (
    employee_id     TEXT NOT NULL REFERENCES employee(employee_id),
    week            INTEGER NOT NULL,
    date            TEXT NOT NULL,
    dow             INTEGER NOT NULL,
    is_pto          INTEGER NOT NULL,
    work_hours      REAL NOT NULL,
    after_hours_minutes INTEGER NOT NULL,
    meeting_hours   REAL NOT NULL,
    focus_minutes   INTEGER NOT NULL,
    messages_sent   INTEGER NOT NULL,
    tickets_closed  INTEGER NOT NULL,
    weekend_active  INTEGER NOT NULL,
    PRIMARY KEY (employee_id, date)
);

CREATE TABLE weekly_signal (
    employee_id     TEXT NOT NULL REFERENCES employee(employee_id),
    week            INTEGER NOT NULL,
    one_on_one_scheduled INTEGER NOT NULL,
    one_on_one_attended  INTEGER NOT NULL,
    pto_days_taken  REAL NOT NULL,
    pto_cancelled   INTEGER NOT NULL,
    pto_balance     REAL NOT NULL,
    PRIMARY KEY (employee_id, week)
);

CREATE TABLE enps_response (
    employee_id     TEXT NOT NULL REFERENCES employee(employee_id),
    week            INTEGER NOT NULL,
    enps_score      INTEGER NOT NULL,
    PRIMARY KEY (employee_id, week)
);

-- ==== 정답 (평가 전용) ======================================================
CREATE TABLE truth_employee (
    employee_id     TEXT PRIMARY KEY REFERENCES employee(employee_id),
    persona_key     TEXT NOT NULL,
    persona_name    TEXT NOT NULL,
    trajectory      TEXT NOT NULL,
    attrition_week  INTEGER,
    peak_stage      INTEGER NOT NULL,   -- 3주 이상 지속된 최고 단계
    weeks_at_risk   INTEGER NOT NULL
);

CREATE TABLE truth_weekly_state (
    employee_id     TEXT NOT NULL REFERENCES employee(employee_id),
    week            INTEGER NOT NULL,
    demand_index    REAL NOT NULL,
    resource_index  REAL NOT NULL,
    strain          REAL NOT NULL,
    exhaustion      REAL NOT NULL,
    cynicism        REAL NOT NULL,
    reduced_efficacy REAL NOT NULL,
    composite       REAL NOT NULL,
    burnout_stage   INTEGER NOT NULL,
    valence         REAL NOT NULL,
    arousal         REAL NOT NULL,
    scar            REAL NOT NULL,        -- 과거 붕괴가 남긴 잔여 취약성
    weeks_to_attrition INTEGER,
    top_drivers     TEXT NOT NULL,        -- 추천 엔진 평가 정답지 (콤마 구분)
    active_events   TEXT,
    PRIMARY KEY (employee_id, week)
);

CREATE INDEX idx_truth_week ON truth_weekly_state(week);
CREATE INDEX idx_behavior_week ON behavior_daily(employee_id, week);

-- ==== 뷰 ====================================================================
-- 개인 뷰: 본인만 조회한다는 전제. 애플리케이션에서 employee_id를 반드시 바인딩.
CREATE VIEW v_employee_week AS
SELECT p.employee_id,
       p.week,
       p.responded,
       p.q_workload, p.q_energy, p.q_engagement,
       p.q_efficacy, p.q_support, p.q_recognition, p.q_mood,
       w.one_on_one_scheduled, w.one_on_one_attended,
       w.pto_days_taken, w.pto_cancelled, w.pto_balance,
       b.work_hours_week, b.after_hours_week, b.meeting_hours_week,
       b.focus_minutes_week, b.weekend_days
FROM pulse_response p
LEFT JOIN weekly_signal w
       ON w.employee_id = p.employee_id AND w.week = p.week
LEFT JOIN (
    SELECT employee_id, week,
           SUM(work_hours)          AS work_hours_week,
           SUM(after_hours_minutes) AS after_hours_week,
           SUM(meeting_hours)       AS meeting_hours_week,
           SUM(focus_minutes)       AS focus_minutes_week,
           SUM(weekend_active)      AS weekend_days
    FROM behavior_daily GROUP BY employee_id, week
) b ON b.employee_id = p.employee_id AND b.week = p.week;

-- HR 뷰: 팀×주 집계. 응답자 5명 미만 그룹은 반환하지 않는다 (k-익명성).
CREATE VIEW v_hr_team_week AS
SELECT e.team_key,
       e.department,
       p.week,
       COUNT(DISTINCT p.employee_id)                       AS respondents,
       ROUND(AVG(p.q_workload), 2)    AS avg_workload,
       ROUND(AVG(p.q_energy), 2)      AS avg_energy,
       ROUND(AVG(p.q_engagement), 2)  AS avg_engagement,
       ROUND(AVG(p.q_efficacy), 2)    AS avg_efficacy,
       ROUND(AVG(p.q_support), 2)     AS avg_support,
       ROUND(AVG(p.q_recognition), 2) AS avg_recognition,
       ROUND(AVG(p.q_mood), 2)        AS avg_mood
FROM pulse_response p
JOIN employee e ON e.employee_id = p.employee_id
WHERE p.responded = 1
GROUP BY e.team_key, e.department, p.week
HAVING COUNT(DISTINCT p.employee_id) >= 5;
