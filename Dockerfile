FROM python:3.12-slim AS builder
WORKDIR /app

COPY requirements-serve.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements-serve.txt

RUN pip install --no-cache-dir "grpcio-tools>=1.64.0"

COPY src/ src/
RUN python -m grpc_tools.protoc -I . \
      --python_out=. --grpc_python_out=. \
      src/api/rba_service.proto

FROM python:3.12-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GRPC_PORT=50051 \
    GRPC_MAX_WORKERS=10 \
    MODEL_PATH=models/xgboost_v1.json \
    PREPROCESSOR_PATH=models/preprocessor_v1.pkl

COPY --from=builder /install /usr/local

COPY --from=builder /app/src/ src/
COPY serve.py healthcheck.py ./
COPY models/ models/

EXPOSE 50051

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python healthcheck.py || exit 1

CMD ["python", "serve.py"]
