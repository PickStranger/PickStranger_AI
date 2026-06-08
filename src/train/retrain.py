import threading
import traceback
import uuid
from datetime import datetime
from typing import Optional

import joblib

from src.prex.oauth_preprocessor import OAuthEventMapper
from src.store.event_store import EventStore
from src.train.detector import RBADetector


class JobStatus:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class RetrainJob:
    def __init__(self, job_id: str, params: dict):
        self.job_id = job_id
        self.params = params
        self.status = JobStatus.PENDING
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.result: Optional[dict] = None
        self.error: Optional[str] = None


class RetrainManager:
    MIN_SAMPLES = 10

    def __init__(
        self,
        base_model_path: str = "models/xgboost_v1.json",
        preprocessor_path: str = "models/preprocessor_v1.pkl",
        event_store: Optional[EventStore] = None,
    ):
        self.base_model_path = base_model_path
        self.preprocessor_path = preprocessor_path
        self.store = event_store or EventStore()
        self._jobs: dict[str, RetrainJob] = {}
        self._lock = threading.Lock()

    def trigger(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        recent_days: Optional[int] = None,
        fine_tune_trees: int = 50,
    ) -> RetrainJob:
        if not recent_days and not (start_date and end_date):
            raise ValueError("recent_days 또는 start_date + end_date 중 하나를 지정해야 합니다.")

        job_id = str(uuid.uuid4())
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "recent_days": recent_days,
            "fine_tune_trees": fine_tune_trees,
        }
        job = RetrainJob(job_id, params)

        with self._lock:
            self._jobs[job_id] = job

        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def get_job(self, job_id: str) -> Optional[RetrainJob]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict]:
        with self._lock:
            return [self._job_to_dict(j) for j in self._jobs.values()]

    def _run(self, job: RetrainJob):
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow().isoformat()

        try:
            p = job.params
            if p.get("recent_days"):
                df = self.store.get_recent_events(p["recent_days"])
            else:
                df = self.store.get_events_by_date_range(p["start_date"], p["end_date"])

            if len(df) < self.MIN_SAMPLES:
                raise ValueError(
                    f"라벨링된 이벤트가 부족합니다: {len(df)}건 (최소 {self.MIN_SAMPLES}건 필요)"
                )

            preprocessor = joblib.load(self.preprocessor_path)
            mapper = OAuthEventMapper()

            rba_df = mapper.to_rba_dataframe(df.to_dict("records"))
            x_new = preprocessor.transform(rba_df)

            y_new = df[["is_attack", "is_account_takeover"]].rename(
                columns={
                    "is_attack": "Is Attack IP",
                    "is_account_takeover": "Is Account Takeover",
                }
            )

            detector = RBADetector(params={"n_estimators": p["fine_tune_trees"], "device": "cpu"})
            detector.fine_tune(x_new, y_new, base_model_path=self.base_model_path)

            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            out_path = f"models/xgboost_ft_{ts}.json"
            detector.save_model(out_path)

            job.result = {
                "samples": len(df),
                "added_trees": p["fine_tune_trees"],
                "new_model_path": out_path,
            }
            job.status = JobStatus.DONE
            print(f"[retrain] job {job.job_id} done → {out_path}")

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            traceback.print_exc()

        finally:
            job.finished_at = datetime.utcnow().isoformat()

    @staticmethod
    def _job_to_dict(job: RetrainJob) -> dict:
        return {
            "job_id": job.job_id,
            "status": job.status,
            "params": job.params,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "result": job.result,
            "error": job.error,
        }
