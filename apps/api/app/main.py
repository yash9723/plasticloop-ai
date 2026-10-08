"""PlasticLoop AI — FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware

log = get_logger("app")

DESCRIPTION = """
PlasticLoop AI — intelligent rural plastic waste collection, traceability and resource recovery (SIH26259).

* All endpoints are versioned under `/api/v1`.
* Authenticate with `POST /api/v1/auth/login`, then send `Authorization: Bearer <access_token>`.
* Devices authenticate with `Authorization: Device <device_id>:<device_key>` on `POST /api/v1/devices/telemetry`.
* Errors always use `{"error": {"code", "message", "details", "request_id"}}`.
* Records carry `data_origin` (`live` | `demo_seed` | `simulated`); simulated data is never evidence of real-world outcomes.
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(settings.log_level)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    try:
        from app.iot.mqtt_auth import write_passwd_file_from_db

        write_passwd_file_from_db()
    except Exception:  # noqa: BLE001 - broker credentials are optional for the HTTP API to serve
        log.warning("mqtt_passwd_sync_failed", exc_info=True)
    log.info("startup", extra={"fields": {"environment": settings.environment, "demo_mode": settings.demo_enabled}})
    yield


app = FastAPI(
    title="PlasticLoop AI API",
    version="0.1.0",
    description=DESCRIPTION,
    lifespan=lifespan,
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)
install_error_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Requested-With", "Idempotency-Key"],
    expose_headers=["X-Request-ID", "Content-Disposition"],
)
app.add_middleware(RequestContextMiddleware)  # outermost: request id + access log for everything
app.include_router(api_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root():
    return {"name": "PlasticLoop AI API", "docs": "/docs", "openapi": "/api/v1/openapi.json", "health": "/api/v1/health"}
