"""Independent DeepAuditCrossWalk ASGI application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from .api import router
from .catalog import (
    load_aiaf_question_bank,
    load_regulatory_pack,
    validate_regulatory_pack,
)
from .store import ConflictError, StorageUnavailable, store

MAX_REQUEST_BYTES = 32 * 1024 * 1024


class RequestLimit:
    """Bound actual request bytes, including streamed/chunked uploads."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length"}, 400)(
                scope, receive, send
            )
        if declared < 0 or declared > MAX_REQUEST_BYTES:
            return await JSONResponse(
                {"detail": "Request exceeds the 32 MiB limit"}, 413
            )(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_REQUEST_BYTES:
                return await JSONResponse(
                    {"detail": "Request exceeds the 32 MiB limit"}, 413
                )(scope, receive, send)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


@asynccontextmanager
async def lifespan(_app):
    production = os.getenv("ENV", "development").strip().lower() == "production"
    if production:
        if len(os.getenv("CROSSWALK_API_KEY", "").encode()) < 32:
            raise RuntimeError(
                "Production CROSSWALK_API_KEY must contain at least 32 bytes"
            )
        if not os.getenv("BANKING_CROSSWALK_TENANT_ID", "").strip():
            raise RuntimeError("Production BANKING_CROSSWALK_TENANT_ID is required")
    store.configure(os.getenv("DATABASE_URL"), production=production)
    try:
        yield
    finally:
        store.reset()


app = FastAPI(
    title="DeepAuditCrossWalk",
    version="0.1.0",
    description="Questionnaire coverage and enterprise policy gap analysis. MVP outputs require expert review.",
    lifespan=lifespan,
)
app.add_middleware(RequestLimit)
origins = [
    value.strip()
    for value in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if value.strip()
]
if "*" in origins:
    raise RuntimeError("ALLOWED_ORIGINS must contain explicit origins")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key", "X-Tenant-ID", "X-Actor", "X-Role"],
)
app.include_router(router)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "stateful_storage": "postgresql" if store.is_durable else "ephemeral",
    }


@app.get("/ready")
def readiness():
    store.check_ready()
    return {
        "status": "ready",
        "stateful_storage": "postgresql" if store.is_durable else "ephemeral",
    }


@app.exception_handler(StorageUnavailable)
async def storage_unavailable(_request, _exc):
    return JSONResponse(
        {"detail": "Storage unavailable. Check database readiness and migrations."}, 503
    )


@app.exception_handler(ConflictError)
async def storage_conflict(_request, exc):
    return JSONResponse({"detail": str(exc)}, 409)


@app.get("/v1/demo")
def demo_metadata():
    bank = load_aiaf_question_bank()
    return {
        "questionnaire": bank.metadata.model_dump(mode="json"),
        "regulatory_pack": validate_regulatory_pack(load_regulatory_pack()),
        "notice": "Synthetic questions and proposed regulatory mappings. No regulatory compliance conclusion is produced.",
    }
