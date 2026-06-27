# OAuth2 로그인 이상탐지 서비스 — 아키텍처 정리

## 개요

이 프로젝트는 **2단계 이상탐지** 파이프라인입니다.

1. **1단계 (OAuth2 인증)** — 기존 OAuth2 Provider가 처리
2. **2단계 (행동 이상탐지)** — OAuth2 성공 직후, 수집된 클라이언트 신호(IP·WebGL·시간대 등)를 XGBoost 모델에 통과시켜 계정 탈취 여부를 판단

실운용 데이터가 쌓이면 날짜 파라미터를 지정해 모델을 주기적으로 **재학습(fine-tune)** 하며 성능을 지속 향상시킵니다.

---

## 디렉터리 구조

```
PickStranger_AI/
├── main.py                          # 사전학습 파이프라인 (RBA 공개 데이터셋)
├── serve.py                         # gRPC 서버 실행 진입점
├── requirements.txt
├── data/
│   └── events.db                    # 런타임에 자동 생성되는 SQLite 이벤트 DB
├── models/
│   ├── xgboost_v1.json              # 사전학습 완료 모델
│   ├── preprocessor_v1.pkl          # 사전학습 전처리기 (Scaler + Encoder)
│   └── xgboost_ft_YYYYMMDD_HHmmss.json  # fine-tune 후 자동 저장되는 버전
└── src/
    ├── prex/
    │   ├── preprocessor.py          # 기존 RBA 전처리기
    │   └── oauth_preprocessor.py    # OAuth2 + WebGL 신호 → RBA 피처 변환
    ├── store/
    │   └── event_store.py           # 로그인 이벤트 SQLite 저장·조회
    ├── train/
    │   ├── detector.py              # XGBoost 탐지기 (fine_tune 메서드 포함)
    │   └── retrain.py               # 날짜 파라미터 기반 백그라운드 재학습
    └── api/
        ├── rba_service.proto        # gRPC 서비스 명세 (proto3) ← 스키마 정의 파일
        ├── rba_service_pb2.py       # protoc 자동 생성 — 메시지 클래스
        ├── rba_service_pb2_grpc.py  # protoc 자동 생성 — 서비스 스텁
        └── servicer.py              # gRPC Servicer 구현
```

---

## 전체 흐름

```
[클라이언트]
    │  OAuth2 성공 후 WebGL / 타임존 / IP 등 전송
    ▼
[리버스 프록시]  (예: Nginx, Envoy — gRPC 브리지 역할)
    │  gRPC — RBAService.Predict RPC  (HTTP/2)
    ▼
[gRPC 서버 — serve.py, 기본 포트 :50051]
    │
    ├─ OAuthEventMapper        ←── 클라이언트 신호를 RBA 피처 컬럼으로 변환
    ├─ RBAPreprocessor.transform()  ←── Scaler / OrdinalEncoder 적용
    ├─ RBADetector.predict()   ←── XGBoost 추론
    │
    ├─ EventStore.save_event() ←── SQLite에 이벤트 저장 (store_event=true)
    │
    └─ 응답: PredictResponse { is_anomaly, risk_score, event_id }

[운영자 / 보안팀]
    │  공격 확인 후 라벨 부여
    │  RBAService.LabelEvent RPC
    ▼
[EventStore] — is_attack 컬럼 업데이트

[스케줄러 / 운영자]
    │  RBAService.TriggerTrain RPC
    ▼
[RetrainManager]
    ├─ EventStore에서 라벨링된 이벤트 조회 (날짜 범위 or 최근 N일)
    ├─ XGBoost warm-start fine-tune (기존 모델 위에 트리 추가)
    ├─ models/xgboost_ft_{timestamp}.json 저장
    └─ RBAService.ReloadModel RPC → 서버 재시작 없이 모델 교체
```

---

## 수집 피처

| 피처 | 원천 | 설명 |
|------|------|------|
| `country` / `region` / `city` | IP 지오로케이션 | 접속 지역 |
| `asn` | IP 조회 | Autonomous System Number |
| `os_name` / `os_version` | User-Agent | 운영체제 |
| `browser_name` / `browser_version` | User-Agent | 브라우저 |
| `device_type` | User-Agent | Desktop / Mobile / Tablet |
| `timezone` / `timezone_offset` | 클라이언트 JS | 로컬 시간대 (UTC 오프셋 포함) |
| `webgl_renderer` / `webgl_vendor` | 클라이언트 JS | GPU 핑거프린트 → SHA-256 해시 |
| `login_timestamp` | 서버 | 로그인 시각 → `hour`, `day_of_week` 파생 |
| `is_success` | OAuth2 결과 | 로그인 성공 여부 |

> `webgl_hash`는 `renderer|vendor` 문자열의 SHA-256 앞 16자리로 저장됩니다.

---

## gRPC 서비스 명세

서비스 정의 파일: `src/api/rba_service.proto`

### `RBAService.Health`

서버 상태, 현재 활성 모델, 라벨링된 이벤트 수를 반환합니다.

**요청** `HealthRequest` — 필드 없음

**응답** `HealthResponse`
```
status:         "ok"
active_model:   "models/xgboost_v1.json"
model_loaded:   true
labeled_events: 342
```

---

### `RBAService.Predict`

OAuth2 로그인 직후 호출합니다. 이상 여부와 위험 점수를 반환하고, 선택적으로 이벤트를 DB에 저장합니다.

**요청** `PredictRequest`
```
user_id:          "user_abc"
ip:               "1.2.3.4"
country:          "KR"
region:           "Seoul"
city:             "Seoul"
asn:              12345
os_name:          "Windows"
os_version:       "11"
browser_name:     "Chrome"
browser_version:  "120.0"
device_type:      "Desktop"
timezone:         "Asia/Seoul"
timezone_offset:  540
webgl_renderer:   "ANGLE (NVIDIA RTX 3080 Direct3D11)"
webgl_vendor:     "Google Inc. (NVIDIA)"
login_timestamp:  "2025-06-01T10:30:00"
is_success:       true
store_event:      true
```

**응답** `PredictResponse`
```
is_anomaly:  false
risk_score:  12.4
event_id:    101   // 0 = 저장하지 않음
```

---

### `RBAService.LabelEvent`

보안팀이 공격 여부를 확인한 후 라벨을 부여합니다. 이 라벨이 있어야 해당 이벤트가 재학습에 사용됩니다.

**요청** `LabelRequest`
```
event_id:            101
is_attack:           true
is_account_takeover: false
```

**응답** `LabelResponse`
```
event_id: 101
labeled:  true
```

---

### `RBAService.TriggerTrain`

백그라운드에서 재학습을 시작합니다. `recent_days` 또는 `start_date + end_date` 중 하나를 지정해야 합니다.

**요청 예시 — 최근 30일** `TrainRequest`
```
recent_days:     30
fine_tune_trees: 50
```

**요청 예시 — 날짜 범위** `TrainRequest`
```
start_date:      "2025-01-01T00:00:00"
end_date:        "2025-06-01T23:59:59"
fine_tune_trees: 100
```

**응답** `TrainResponse`
```
job_id:  "550e8400-e29b-41d4-a716-446655440000"
status:  "pending"
message: "재학습 작업이 백그라운드에서 시작되었습니다."
```

---

### `RBAService.GetTrainStatus`

재학습 작업의 진행 상태를 확인합니다.

**요청** `TrainStatusRequest`
```
job_id: "550e8400-e29b-41d4-a716-446655440000"
```

**응답 (완료 시)** `TrainStatusResponse`
```
job_id:         "550e8400-..."
status:         "done"
started_at:     "2025-06-01T12:00:00"
finished_at:    "2025-06-01T12:03:42"
samples:        512
added_trees:    50
new_model_path: "models/xgboost_ft_20250601_120342.json"
error:          ""
```

---

### `RBAService.ListJobs`

등록된 모든 재학습 작업 목록을 반환합니다.

**요청** `ListJobsRequest` — 필드 없음

**응답** `ListJobsResponse`
```
jobs: [
  { job_id, status, started_at, finished_at },
  ...
]
```

---

### `RBAService.ReloadModel`

서버 재시작 없이 활성 모델을 교체합니다.

**요청** `ReloadRequest`
```
model_path: "models/xgboost_ft_20250601_120342.json"
```

**응답** `ReloadResponse`
```
status:       "reloaded"
active_model: "models/xgboost_ft_20250601_120342.json"
```

---

## 학습 방식: Fine-tuning (Warm-Start)

재학습은 XGBoost의 **warm-start** 방식을 사용합니다.

```
사전학습 모델 (n_estimators=100 트리, RBA 공개 데이터)
        +
실운용 신규 데이터 (날짜 범위 내 라벨링된 이벤트)
        ↓
fine-tune (n_estimators=50 트리 추가)
        ↓
최종 모델 (총 150트리, 일반화 + 실데이터 반영)
```

- 기존 사전학습 트리는 보존되고, 새 트리가 추가로 누적됩니다.
- `fine_tune_trees`(10~500)로 추가할 트리 수를 조절합니다.
- 최소 10건의 라벨링된 이벤트가 있어야 학습이 시작됩니다.

---

## 서버 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# proto 코드 생성 (최초 1회, proto 변경 시 재실행)
python -m grpc_tools.protoc \
  -I src/api \
  --python_out=src/api \
  --grpc_python_out=src/api \
  src/api/rba_service.proto

# 사전학습 (최초 1회)
python main.py

# gRPC 서버 실행
python serve.py
```

환경 변수로 포트·모델 경로를 오버라이드할 수 있습니다.

```bash
GRPC_PORT=50051 MODEL_PATH=models/xgboost_ft_20250601.json python serve.py
```

---

## 주기적 재학습 권장 절차

1. 운영자가 보안 이벤트를 확인한 뒤 `LabelEvent` RPC로 라벨 부여
2. 월 1회 또는 라벨 이벤트가 일정 수 이상 누적되면 `TriggerTrain` RPC 호출
3. `GetTrainStatus` RPC로 완료 확인
4. `ReloadModel` RPC로 새 모델 즉시 적용
