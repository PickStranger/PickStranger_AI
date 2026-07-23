"""Docker HEALTHCHECK용 스크립트.

gRPC 서버의 Health RPC 를 호출해 status == "ok" 이면 0(정상), 아니면 1(비정상)로 종료한다.
"""
import os
import sys

import grpc

from src.api import rba_service_pb2, rba_service_pb2_grpc

PORT = os.getenv("GRPC_PORT", "50051")


def main() -> int:
    try:
        channel = grpc.insecure_channel(f"localhost:{PORT}")
        stub = rba_service_pb2_grpc.RBAServiceStub(channel)
        resp = stub.Health(rba_service_pb2.HealthRequest(), timeout=3)
        return 0 if resp.status == "ok" else 1
    except Exception as e:  # 연결 실패 / 타임아웃 등
        print(f"[healthcheck] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
