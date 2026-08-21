import os
from datetime import datetime

import grpc
import joblib

from src.api import rba_service_pb2, rba_service_pb2_grpc
from src.prex.oauth_preprocessor import OAuthEventMapper
from src.store.event_store import EventStore
from src.train.detector import RBADetector
from src.train.retrain import RetrainManager

MODEL_PATH = os.getenv("MODEL_PATH", "models/xgboost_v1.json")
PREPROCESSOR_PATH = os.getenv("PREPROCESSOR_PATH", "models/preprocessor_v1.pkl")


class RBAServicer(rba_service_pb2_grpc.RBAServiceServicer):
    def __init__(self):
        self.detector = RBADetector(params={"device": "cpu"})
        self.detector.load_model(MODEL_PATH)
        self.preprocessor = joblib.load(PREPROCESSOR_PATH)
        self.mapper = OAuthEventMapper()
        self.store = EventStore()
        self.retrain = RetrainManager(
            base_model_path=MODEL_PATH,
            preprocessor_path=PREPROCESSOR_PATH,
            event_store=self.store,
        )
        self.active_model = MODEL_PATH
        print(f"[servicer] model loaded: {MODEL_PATH}")

    # ──────────────────────── Health ────────────────────────

    def Health(self, request, context):
        return rba_service_pb2.HealthResponse(
            status="ok",
            active_model=self.active_model,
            model_loaded=self.detector.is_trained if self.detector else False,
            labeled_events=self.store.count_labeled() if self.store else 0,
        )

    # ──────────────────────── Predict ───────────────────────

    def Predict(self, request, context):
        event = {
            "user_id": request.user_id,
            "ip": request.ip,
            "country": request.country or "unknown",
            "region": request.region or "unknown",
            "city": request.city or "unknown",
            "asn": request.asn,
            "os_name": request.os_name or "unknown",
            "os_version": request.os_version,
            "browser_name": request.browser_name or "unknown",
            "browser_version": request.browser_version,
            "device_type": request.device_type or "unknown",
            "timezone": request.timezone or "UTC",
            "timezone_offset": request.timezone_offset,
            "webgl_renderer": request.webgl_renderer,
            "webgl_vendor": request.webgl_vendor,
            "login_timestamp": request.login_timestamp or datetime.utcnow().isoformat(),
            "is_success": request.is_success,
            "store_event": request.store_event,
        }

        rba_df = self.mapper.to_rba_dataframe([event])
        x = self.preprocessor.transform(rba_df)
        result = self.detector.predict(x)[0]

        event_id = 0
        if request.store_event:
            store_dict = self.mapper.build_store_dict(event)
            event_id = self.store.save_event(store_dict) or 0

        return rba_service_pb2.PredictResponse(
            is_anomaly=result["is_anomaly"],
            risk_score=float(result["risk_score"]),
            event_id=event_id,
        )

    # ──────────────────────── Label ─────────────────────────

    def LabelEvent(self, request, context):
        self.store.update_label(
            request.event_id, request.is_attack, request.is_account_takeover
        )
        return rba_service_pb2.LabelResponse(event_id=request.event_id, labeled=True)

    # ──────────────────────── Train ─────────────────────────

    def TriggerTrain(self, request, context):
        start_date = request.start_date or None
        end_date = request.end_date or None
        recent_days = request.recent_days or None
        fine_tune_trees = request.fine_tune_trees or 50

        try:
            job = self.retrain.trigger(
                start_date=start_date,
                end_date=end_date,
                recent_days=recent_days,
                fine_tune_trees=fine_tune_trees,
            )
        except ValueError as e:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
            return

        return rba_service_pb2.TrainResponse(
            job_id=job.job_id,
            status=job.status,
            message="재학습 작업이 백그라운드에서 시작되었습니다.",
        )

    def GetTrainStatus(self, request, context):
        job = self.retrain.get_job(request.job_id)
        if not job:
            context.abort(grpc.StatusCode.NOT_FOUND, "Job not found")
            return

        result = job.result or {}
        return rba_service_pb2.TrainStatusResponse(
            job_id=job.job_id,
            status=job.status,
            started_at=job.started_at or "",
            finished_at=job.finished_at or "",
            error=job.error or "",
            samples=result.get("samples", 0),
            added_trees=result.get("added_trees", 0),
            new_model_path=result.get("new_model_path", ""),
        )

    def ListJobs(self, request, context):
        jobs = self.retrain.list_jobs()
        summaries = [
            rba_service_pb2.JobSummary(
                job_id=j.get("job_id", ""),
                status=j.get("status", ""),
                started_at=j.get("started_at") or "",
                finished_at=j.get("finished_at") or "",
            )
            for j in jobs
        ]
        return rba_service_pb2.ListJobsResponse(jobs=summaries)

    # ──────────────────────── Model Reload ──────────────────

    def ReloadModel(self, request, context):
        if not request.model_path.endswith(".json"):
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "model_path는 .json 파일이어야 합니다.",
            )
            return
        try:
            self.detector.load_model(request.model_path)
            self.active_model = request.model_path
            return rba_service_pb2.ReloadResponse(
                status="reloaded",
                active_model=request.model_path,
            )
        except Exception as e:
            context.abort(grpc.StatusCode.INTERNAL, str(e))
