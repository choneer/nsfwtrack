from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import init_db
from app.routers import auth, backup, creators, importer, items, pages, search, stats, tags


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.schema_status = init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="NSFWTrack",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        https_only=False,
    )
    app.include_router(auth.router)
    app.include_router(items.router)
    app.include_router(tags.router)
    app.include_router(creators.router)
    app.include_router(search.router)
    app.include_router(stats.router)
    app.include_router(importer.router)
    app.include_router(backup.router)
    app.include_router(pages.router)
    return app


app = create_app()
