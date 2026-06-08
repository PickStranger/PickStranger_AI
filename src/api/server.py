import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import joblib
from fastapi import FastAPI, HTTPException

from src.api.schemas import (
    HealthResponse,
    LabelRequest,
    PredictRequest,
    PredictResponse,
    TrainRequest,
    TrainResponse,
    TrainStatusResponse,
)
from src.prex.oauth_preprocessor import OAuthEventMapper
from src.store.event_store import EventStore
from src.train.detector import RBADetector
from src.train.retrain import RetrainManager

MODEL_PATH = os.getenv("MODEL_PATH", "models/xgboost_v1.json")
PREPROCESSOR_PATH = os.getenv("PREPROCESSOR_PATH", "models/preprocessor_v1.pkl")


class _State:
    detector: Optional[RBADetector] = None
    preprocessor = None
    mapper: Optional[OAuthEventMapper] = None
    store: Optional[EventStore] = None
    retrain: Optional[RetrainManager] = None
    active_model: str = MODEL_PATH


_s = _State()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _s.detector = RBADetector(params={"device": "cpu"})
    _s.detector.load_model(MODEL_PATH)
    _s.preprocessor = joblib.load(PREPROCESSOR_PATH)
    _s.mapper = OAuthEventMapper()
    _s.store = EventStore()
    _s.retrain = RetrainManager(
        base_model_path=MODEL_PATH,
        preprocessor_path=PREPROCESSOR_PATH,
        event_store=_s.store,
    )
    _s.active_model = MODEL_PATH
    print(f"[server] model loaded: {MODEL_PATH}")
    yield


app = FastAPI(title="RBA Anomaly Detection", version="1.0.0", lifespan=lifespan)


# ──────────────────────────── health ────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        active_model=_s.active_model,
        model_loaded=_s.detector.is_trained if _s.detector else False,
        labeled_events=_s.store.count_labeled() if _s.store else 0,
    )


# ──────────────────────────── predict ───────────────────────────

@app.post("/api/v1/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    event = req.model_dump()
    event.setdefault("login_timestamp", datetime.utcnow().isoformat())

    rba_df = _s.mapper.to_rba_dataframe([event])
    x = _s.preprocessor.transform(rba_df)
    result = _s.detector.predict(x)[0]

    event_id = None
    if req.store_event:
        store_dict = _s.mapper.build_store_dict(event)
        event_id = _s.store.save_event(store_dict)

    return PredictResponse(
        is_anomaly=result["is_anomaly"],
        risk_score=result["risk_score"],
        event_id=event_id,
    )


# ──────────────────────────── label ─────────────────────────────

@app.patch("/api/v1/events/{event_id}/label")
def label_event(event_id: int, req: LabelRequest):
    """수집된 이벤트에 공격 여부 라벨을 달아 재학습에 활용합니다."""
    _s.store.update_label(event_id, req.is_attack, req.is_account_takeover)
    return {"event_id": event_id, "labeled": True}


# ──────────────────────────── train ─────────────────────────────

@app.post("/api/v1/train", response_model=TrainResponse)
def trigger_train(req: TrainRequest):
    """
    날짜 범위 또는 최근 N일의 라벨링된 이벤트로 모델을 fine-tune합니다.

    - recent_days: 최근 N일 (예: 30)
    - start_date + end_date: ISO 형식 날짜 범위 (예: 2025-01-01T00:00:00)
    """
    try:
        job = _s.retrain.trigger(
            start_date=req.start_date,
            end_date=req.end_date,
            recent_days=req.recent_days,
            fine_tune_trees=req.fine_tune_trees,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return TrainResponse(
        job_id=job.job_id,
        status=job.status,
        message="재학습 작업이 백그라운드에서 시작되었습니다.",
    )


@app.get("/api/v1/train/{job_id}", response_model=TrainStatusResponse)
def train_status(job_id: str):
    job = _s.retrain.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return TrainStatusResponse(
        job_id=job.job_id,
        status=job.status,
        params=job.params,
        started_at=job.started_at,
        finished_at=job.finished_at,
        result=job.result,
        error=job.error,
    )


@app.get("/api/v1/train")
def list_jobs():
    return _s.retrain.list_jobs()


# ──────────────────────────── model reload ──────────────────────

@app.post("/api/v1/model/reload")
def reload_model(model_path: str = MODEL_PATH):
    """fine-tune 완료 후 서버가 사용할 모델을 교체합니다."""
    if not model_path.endswith(".json"):
        raise HTTPException(status_code=400, detail="model_path는 .json 파일이어야 합니다.")
    try:
        _s.detector.load_model(model_path)
        _s.active_model = model_path
        return {"status": "reloaded", "active_model": model_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
