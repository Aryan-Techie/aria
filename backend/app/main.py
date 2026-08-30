import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routes import admin, call, llm

# Default log level is WARNING — our own INFO-level diagnostic logging
# (e.g. pipeline.py logging the exact reply text per turn) was silently
# dropped without this, found live while trying to diagnose a real call.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

logger = logging.getLogger("aria")

app = FastAPI(title="Aria orchestrator")


@app.middleware("http")
async def catch_all_exceptions(request: Request, call_next):
    """Deliberately registered as ASGI middleware, NOT via
    @app.exception_handler(Exception) — Starlette special-cases a handler
    registered for the bare Exception class, routing it through
    ServerErrorMiddleware, which sits OUTSIDE CORSMiddleware. That silently
    drops the CORS header on every error response reaching the browser as an
    opaque "Failed to fetch" with the real cause invisible. Registering this
    *before* CORSMiddleware below places it inside CORSMiddleware in the
    stack (Starlette's add_middleware inserts each new one at the front), so
    a response built here still passes back out through CORS's header
    injection. Caught live: /api/call/start raising with no Agora
    credentials configured showed up in the browser as a bare CORS failure
    until this was traced down manually.
    """
    try:
        return await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"error": str(exc)})


_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _settings.cors_allowed_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(call.router)
app.include_router(llm.router)
app.include_router(admin.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
