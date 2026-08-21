# 사용 가이드 — OAuth2 로그인 이상탐지 서비스

## 1. 서버 실행

### 사전 조건

```bash
# 의존성 설치
pip install -r requirements.txt

# 사전학습이 아직 안 됐다면 먼저 실행 (models/ 폴더 생성)
python main.py
```

### 서버 시작

```bash
# 기본 실행
python serve.py

# 또는 직접 uvicorn 사용 (포트·워커 수 조정 가능)
uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --workers 4

# 다른 모델로 시작하고 싶을 때
MODEL_PATH=models/xgboost_ft_20250601_120000.json python serve.py
```

서버가 뜨면 `http://localhost:8000/docs` 에서 Swagger UI로 바로 테스트할 수 있습니다.

---

## 2. 외부 서비스에서 호출하는 방법

### 언제 호출하나?

OAuth2 인증 흐름에서 **access token으로 유저 정보를 받아온 직후** 호출합니다.

```
[클라이언트] → OAuth2 Provider → access token 발급
                                       ↓
                              유저 정보 (user_id 등) 획득
                                       ↓
                        ★ POST /api/v1/predict 호출 ★
                                       ↓
                     is_anomaly=true → 추가 인증 요구 or 차단
                     is_anomaly=false → 로그인 허용
```

### 클라이언트에서 미리 수집해야 할 값

JavaScript로 로그인 페이지에서 아래 값을 수집해 백엔드로 전달합니다.

```javascript
// 클라이언트 사이드에서 수집
const signals = {
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,  // "Asia/Seoul"
  timezone_offset: new Date().getTimezoneOffset() * -1,        // 540
  webgl_renderer: (() => {
    const gl = document.createElement('canvas').getContext('webgl');
    const ext = gl?.getExtension('WEBGL_debug_renderer_info');
    return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : '';
  })(),
  webgl_vendor: (() => {
    const gl = document.createElement('canvas').getContext('webgl');
    const ext = gl?.getExtension('WEBGL_debug_renderer_info');
    return ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : '';
  })(),
};
```

IP·국가·브라우저·OS 정보는 백엔드 서버에서 직접 파싱합니다 (User-Agent, IP 지오로케이션).

---

## 3. API 호출 예시

### 추론 — `POST /api/v1/predict`

**curl**
```bash
curl -X POST http://localhost:8000/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_abc123",
    "ip": "1.2.3.4",
    "country": "KR",
    "region": "Seoul",
    "city": "Seoul",
    "asn": 12345,
    "os_name": "Windows",
    "os_version": "11",
    "browser_name": "Chrome",
    "browser_version": "120.0",
    "device_type": "Desktop",
    "timezone": "Asia/Seoul",
    "timezone_offset": 540,
    "webgl_renderer": "ANGLE (NVIDIA RTX 3080 Direct3D11)",
    "webgl_vendor": "Google Inc. (NVIDIA)",
    "login_timestamp": "2025-06-07T10:30:00",
    "is_success": true,
    "store_event": true
  }'
```

**Python**
```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/predict",
    json={
        "user_id": "user_abc123",
        "ip": "1.2.3.4",
        "country": "KR",
        "region": "Seoul",
        "city": "Seoul",
        "asn": 12345,
        "os_name": "Windows",
        "os_version": "11",
        "browser_name": "Chrome",
        "browser_version": "120.0",
        "device_type": "Desktop",
        "timezone": "Asia/Seoul",
        "timezone_offset": 540,
        "webgl_renderer": "ANGLE (NVIDIA RTX 3080 Direct3D11)",
        "webgl_vendor": "Google Inc. (NVIDIA)",
        "login_timestamp": "2025-06-07T10:30:00",
        "is_success": True,
        "store_event": True,
    }
)

result = response.json()
# {
#   "is_anomaly": false,
#   "risk_score": 12.4,
#   "event_id": 101
# }

if result["is_anomaly"]:
    # 추가 인증 요구 or 로그인 차단
    pass
```

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `is_anomaly` | bool | true면 이상 로그인으로 판단 |
| `risk_score` | float | 0~100, 높을수록 위험 |
| `event_id` | int | DB에 저장된 이벤트 ID (라벨링에 사용) |

> `store_event: false`로 보내면 DB 저장을 건너뜁니다. 테스트 시 활용하세요.

---

### 라벨 부여 — `PATCH /api/v1/events/{event_id}/label`

보안팀이 실제 공격 여부를 확인한 후 라벨을 답니다. **이 라벨이 있어야 재학습에 사용됩니다.**

```bash
curl -X PATCH http://localhost:8000/api/v1/events/101/label \
  -H "Content-Type: application/json" \
  -d '{"is_attack": true, "is_account_takeover": false}'
```

```python
requests.patch(
    "http://localhost:8000/api/v1/events/101/label",
    json={"is_attack": True, "is_account_takeover": False}
)
```

---

### 재학습 트리거 — `POST /api/v1/train`

관리자가 주기적으로 호출합니다. 백그라운드에서 실행되므로 응답은 즉시 반환됩니다.

**최근 N일 기준**
```bash
curl -X POST http://localhost:8000/api/v1/train \
  -H "Content-Type: application/json" \
  -d '{"recent_days": 30, "fine_tune_trees": 50}'
```

**날짜 범위 기준**
```bash
curl -X POST http://localhost:8000/api/v1/train \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-01-01T00:00:00",
    "end_date": "2025-06-01T23:59:59",
    "fine_tune_trees": 100
  }'
```

응답으로 `job_id`를 받습니다.
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "재학습 작업이 백그라운드에서 시작되었습니다."
}
```

---

### 재학습 상태 확인 — `GET /api/v1/train/{job_id}`

```bash
curl http://localhost:8000/api/v1/train/550e8400-e29b-41d4-a716-446655440000
```

**진행 중**
```json
{"job_id": "550e...", "status": "running", "started_at": "2025-06-07T12:00:00"}
```

**완료**
```json
{
  "job_id": "550e...",
  "status": "done",
  "started_at": "2025-06-07T12:00:00",
  "finished_at": "2025-06-07T12:03:42",
  "result": {
    "samples": 512,
    "added_trees": 50,
    "new_model_path": "models/xgboost_ft_20250607_120342.json"
  }
}
```

**실패**
```json
{"job_id": "550e...", "status": "failed", "error": "라벨링된 이벤트가 부족합니다: 3건"}
```

---

### 모델 교체 — `POST /api/v1/model/reload`

재학습 완료 후 서버 재시작 없이 새 모델을 적용합니다.

```bash
curl -X POST \
  "http://localhost:8000/api/v1/model/reload?model_path=models/xgboost_ft_20250607_120342.json"
```

---

### 서버 상태 확인 — `GET /health`

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "active_model": "models/xgboost_v1.json",
  "model_loaded": true,
  "labeled_events": 342
}
```

---

## 4. 주기적 재학습 운영 절차

```
매월 1일 (예시)
  │
  ├─ 1. 라벨링 현황 확인
  │      GET /health → labeled_events 수 확인
  │      (10건 미만이면 이번 달은 건너뜀)
  │
  ├─ 2. 재학습 트리거
  │      POST /api/v1/train { "recent_days": 30 }
  │      → job_id 저장
  │
  ├─ 3. 완료 대기
  │      GET /api/v1/train/{job_id} 폴링
  │      status == "done" 확인
  │
  ├─ 4. 새 모델 적용
  │      POST /api/v1/model/reload?model_path={new_model_path}
  │
  └─ 5. 정상 동작 확인
         GET /health → active_model이 새 경로인지 확인
```

---

## 5. 리버스 프록시 연동 (Nginx 예시)

```nginx
upstream rba_service {
    server 127.0.0.1:8000;
}

server {
    listen 443 ssl;
    server_name your-domain.com;

    # 추론 엔드포인트만 외부 노출
    location /api/v1/predict {
        proxy_pass http://rba_service;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 10s;
    }

    # 관리 엔드포인트는 내부망에서만 허용
    location /api/v1/train {
        allow 10.0.0.0/8;
        deny all;
        proxy_pass http://rba_service;
    }

    location /api/v1/model {
        allow 10.0.0.0/8;
        deny all;
        proxy_pass http://rba_service;
    }
}
```

> `/predict`는 외부 공개, `/train`과 `/model/reload`는 내부망에서만 접근하도록 분리하는 것을 권장합니다.

---

## 6. 요청 파라미터 전체 목록

### `POST /api/v1/predict`

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `user_id` | string | ✅ | — | OAuth2 유저 ID |
| `ip` | string | ✅ | — | 클라이언트 IP |
| `country` | string | | `"unknown"` | 국가 코드 (예: KR) |
| `region` | string | | `"unknown"` | 지역 |
| `city` | string | | `"unknown"` | 도시 |
| `asn` | int | | `0` | Autonomous System Number |
| `os_name` | string | | `"unknown"` | 운영체제 이름 |
| `os_version` | string | | `""` | 운영체제 버전 |
| `browser_name` | string | | `"unknown"` | 브라우저 이름 |
| `browser_version` | string | | `""` | 브라우저 버전 |
| `device_type` | string | | `"unknown"` | Desktop / Mobile / Tablet |
| `timezone` | string | | `"UTC"` | IANA 타임존 (예: Asia/Seoul) |
| `timezone_offset` | int | | `0` | UTC 오프셋 (분 단위, 예: 540) |
| `webgl_renderer` | string | | `""` | WebGL 렌더러 문자열 |
| `webgl_vendor` | string | | `""` | WebGL 벤더 문자열 |
| `login_timestamp` | string | | 현재 시각 | ISO 8601 형식 |
| `is_success` | bool | | `true` | 로그인 성공 여부 |
| `store_event` | bool | | `true` | DB 저장 여부 |

### `POST /api/v1/train`

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `recent_days` | int | 최근 N일 (예: 30) |
| `start_date` | string | 시작 날짜 ISO 8601 |
| `end_date` | string | 종료 날짜 ISO 8601 |
| `fine_tune_trees` | int | 추가할 트리 수 (10~500, 기본 50) |

> `recent_days` 또는 `start_date + end_date` 중 하나는 반드시 지정해야 합니다.
