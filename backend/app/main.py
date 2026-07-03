"""EvalForge FastAPI application: CORS, routers, startup table creation."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db, run_migrations
from app.ratelimit import RateLimitMiddleware
from app.routers import backends, cases, compare, runs, suites
from app.schemas import HealthOut
from app.security import require_token


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if get_settings().evalforge_use_migrations:
        run_migrations()
    else:
        init_db()
    yield


app = FastAPI(title="EvalForge", version="0.1.0", lifespan=lifespan)

# Rate limiter is added first so CORS (added last) stays the OUTERMOST layer and
# still decorates 429 responses with the CORS headers the browser needs to read.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)


# Liveness probe: intentionally open (no token, not rate limited).
@app.get("/api/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok")


# The rest of the surface sits behind the shared-token gate (a no-op when the
# token is unset). backends is included so the UI can't enumerate providers
# without the token either.
_gated = [Depends(require_token)]
app.include_router(backends.router, dependencies=_gated)
app.include_router(suites.router, dependencies=_gated)
app.include_router(cases.router, dependencies=_gated)
app.include_router(runs.router, dependencies=_gated)
app.include_router(compare.router, dependencies=_gated)
