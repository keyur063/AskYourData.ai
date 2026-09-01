"""
AskYourData.ai — FastAPI application entrypoint.

Mounts all API routers and registers middleware.  The /health endpoint is
the only route implemented at scaffold time; all others are stubs that will
be filled in session by session per docs/Lean-Backlog.md.
"""
import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.logging import get_logger, request_id_ctx
from app.core.security import CurrentUser, require_user

logger = get_logger(__name__)

app = FastAPI(
    title="AskYourData.ai",
    version="0.1.0-lean",
    description="Natural-language queries over your CSV data.",
)

# ---------------------------------------------------------------------------
# CORS — allow the Next.js dev server in local development.
# Tighten this list when deploying to a real environment.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request-ID middleware — attaches a UUID to every request so every log
# line for that request is traceable. The ID is also returned as a response
# header so the frontend / curl caller can correlate with server logs.
# ---------------------------------------------------------------------------
@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    token = request_id_ctx.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_ctx.reset(token)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "method=%s path=%s status=%s",
        request.method,
        request.url.path,
        response.status_code,
    )
    return response


# ---------------------------------------------------------------------------
# Routers — uncomment each as its ticket is implemented:
# ---------------------------------------------------------------------------
from app.api import workspaces  # L1.3
app.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])

from app.api import files  # L2.1
app.include_router(files.router, tags=["files"])

from app.api import catalog  # L3.1
app.include_router(catalog.router, tags=["catalog"])

# from app.api import query    # L5.4
from app.api import me       # L5.0
# app.include_router(query.router, tags=["query"])
app.include_router(me.router, tags=["me"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health", tags=["meta"])
async def health(request: Request):
    """Liveness check — returns 200 when the server is up."""
    return JSONResponse(
        {
            "status": "ok",
            "version": "0.1.0-lean",
            "request_id": request.state.request_id,
        }
    )


@app.get("/auth-test", tags=["meta"])
async def auth_test(current_user: Annotated[CurrentUser, Depends(require_user)]):
    """
    L1.2 verification route — protected by JWT.

    Returns 200 + resolved user_id with a valid Supabase-issued token.
    Returns 401 with an invalid/expired/missing token.
    """
    return {"authenticated": True, "user_id": current_user.user_id}
