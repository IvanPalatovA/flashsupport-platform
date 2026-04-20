from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from infrastructure.config import get_settings
from infrastructure.db import ensure_schema, get_session_factory
from infrastructure.repositories import AuthRepository
from infrastructure.security import TokenManager
from routers import router
from services import AuthService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "Auth token TTLs: user_access=%s minutes, user_refresh=%s days, service_access=%s minutes",
        settings.user_access_token_ttl_minutes,
        settings.user_refresh_token_ttl_days,
        settings.service_access_token_ttl_minutes,
    )

    if settings.skip_schema_init:
        logger.warning("Schema initialization is skipped because SKIP_SCHEMA_INIT=true")
        yield
        return

    ensure_schema()

    session = get_session_factory()()
    try:
        repository = AuthRepository(session=session)
        service = AuthService(repository=repository, token_manager=TokenManager(settings), settings=settings)
        loaded = service.sync_service_public_keys()
        logger.info("Loaded %s service public keys into trust registry", loaded)
    finally:
        session.close()

    yield


app = FastAPI(title="FlashSupport Auth Service", version="0.1.0", lifespan=lifespan)
app.include_router(router)
