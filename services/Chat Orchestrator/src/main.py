from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from infrastructure.config import get_settings
from routes import router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_settings()
    yield


app = FastAPI(title="FlashSupport Chat Orchestrator", version="0.1.0", lifespan=lifespan)
app.include_router(router)