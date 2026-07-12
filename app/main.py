from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import init_db
from app.errors import install_exception_handlers
from app.request_context import RequestContextMiddleware, configure_request_logging
from app.routers import auth, backup, creators, importer, items, pages, search, stats, tags
from app.security import require_same_origin
from app.security_headers import SecurityHeadersMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.schema_status = init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_request_logging()
    app = FastAPI(
        title="NSFWTrack",
        version="1.0.4",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        dependencies=[Depends(require_same_origin)],
    )
    app.state.session_generation = secrets.token_hex(32)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        https_only=settings.session_cookie_secure,
    )
    app.add_middleware(RequestContextMiddleware)
    # Outer middleware so security headers apply to success, redirects, errors,
    # JSON, and media responses, including those produced by request context.
    app.add_middleware(SecurityHeadersMiddleware)
    install_exception_handlers(app)
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
