"""
main.py — FastAPI application entry point.

Start the server:
    uvicorn server.main:app --reload                          # dev
    uvicorn server.main:app --host 0.0.0.0 --port 8000       # prod
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from server.auth import limiter
from server.score import router as score_router
from server.register import router as register_router

# ---------------------------------------------------------------------------
# Environment — load .env before anything else reads os.environ
# ---------------------------------------------------------------------------
load_dotenv()

_REQUIRED = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
for _var in _REQUIRED:
    if not os.environ.get(_var):
        raise RuntimeError(
            f"Required environment variable '{_var}' is not set. "
            f"Copy server/.env.example to server/.env and fill it in."
        )

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AgentCard Disco API",
    description=(
        "REST API for scoring and optimising A2A protocol Agent Cards.\n\n"
        "**Authentication:** pass your API key in the `X-API-Key` header.\n\n"
        "**Tier 2 deep scoring:** set `deep: true` in the request body and "
        "ensure `GEMINI_API_KEY` is set in the server environment."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}. Please slow down."},
    )


# ---------------------------------------------------------------------------
# CORS — tighten CORS_ORIGINS in production
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(score_router, prefix="/v1")
app.include_router(register_router, prefix="/v1")


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    return JSONResponse({
        "service": "agentcard-disco-api",
        "docs": "/docs",
        "health": "/v1/health",
    })
