from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from infrastructure.db import ensure_schema
from routers import router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    ensure_schema()
    yield

app = FastAPI(title="FlashSupport RAG Service", version="0.1.0", lifespan=lifespan)
app.include_router(router)
