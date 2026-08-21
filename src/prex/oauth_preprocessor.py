import hashlib
import pandas as pd
from datetime import datetime


class OAuthEventMapper:
    """OAuth2 로그인 이벤트 딕셔너리를 RBAPreprocessor가 기대하는 컬럼 형식으로 변환."""

    @staticmethod
    def hash_webgl(renderer: str, vendor: str) -> str:
        raw = f"{vendor}|{renderer}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _parse_datetime(ts: str):
        try:
            return pd.to_datetime(ts, errors="coerce")
        except Exception:
            return pd.NaT

    def to_rba_row(self, event: dict) -> dict:
        """단일 이벤트 dict → RBA 피처 row dict."""
        ts = event.get("login_timestamp") or datetime.utcnow().isoformat()

        os_str = f"{event.get('os_name', 'unknown')} {event.get('os_version', '')}".strip()
        browser_str = f"{event.get('browser_name', 'unknown')} {event.get('browser_version', '')}".strip()

        return {
            "Country": event.get("country") or "unknown",
            "Region": event.get("region") or "unknown",
            "City": event.get("city") or "unknown",
            "OS Name and Version": os_str or "unknown",
            "Browser Name and Version": browser_str or "unknown",
            "Device Type": event.get("device_type") or "unknown",
            "ASN": event.get("asn") or 0,
            "Login Timestamp": ts,
            "Login Successful": int(event.get("is_success", 1)),
        }

    def to_rba_dataframe(self, events: list[dict]) -> pd.DataFrame:
        return pd.DataFrame([self.to_rba_row(e) for e in events])

    def build_store_dict(self, event: dict) -> dict:
        """API 요청 dict → EventStore에 저장할 형식으로 변환."""
        ts = event.get("login_timestamp") or datetime.utcnow().isoformat()
        dt = self._parse_datetime(ts)

        webgl_hash = self.hash_webgl(
            event.get("webgl_renderer", ""),
            event.get("webgl_vendor", ""),
        )

        return {
            "user_id": event.get("user_id"),
            "ip": event.get("ip"),
            "country": event.get("country") or "unknown",
            "region": event.get("region") or "unknown",
            "city": event.get("city") or "unknown",
            "asn": event.get("asn") or 0,
            "os_name": event.get("os_name") or "unknown",
            "os_version": event.get("os_version") or "",
            "browser_name": event.get("browser_name") or "unknown",
            "browser_version": event.get("browser_version") or "",
            "device_type": event.get("device_type") or "unknown",
            "timezone": event.get("timezone") or "UTC",
            "timezone_offset": event.get("timezone_offset") or 0,
            "webgl_hash": webgl_hash,
            "login_timestamp": ts,
            "hour": int(dt.hour) if dt is not pd.NaT else -1,
            "day_of_week": int(dt.dayofweek) if dt is not pd.NaT else -1,
            "is_success": int(event.get("is_success", 1)),
            "is_attack": None,
            "is_account_takeover": None,
        }
