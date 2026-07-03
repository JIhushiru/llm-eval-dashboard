"""EvalForge FastAPI application: CORS, routers, startup table creation."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import backends, cases, compare, runs, suites
from app.schemas import HealthOut


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="EvalForge", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok")


app.include_router(backends.router)
app.include_router(suites.router)
app.include_router(cases.router)
app.include_router(runs.router)
app.include_router(compare.router)
