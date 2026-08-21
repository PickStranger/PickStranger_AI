import os
from concurrent import futures

import grpc

from src.api import rba_service_pb2_grpc
from src.api.servicer import RBAServicer

PORT = os.getenv("GRPC_PORT", "50051")
MAX_WORKERS = int(os.getenv("GRPC_MAX_WORKERS", "10"))


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=MAX_WORKERS))
    rba_service_pb2_grpc.add_RBAServiceServicer_to_server(RBAServicer(), server)
    server.add_insecure_port(f"[::]:{PORT}")
    server.start()
    print(f"[server] gRPC listening on port {PORT}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
