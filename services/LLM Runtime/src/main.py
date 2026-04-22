from fastapi import FastAPI

from routers import router

app = FastAPI(title="FlashSupport LLM Runtime", version="0.1.0")
app.include_router(router)
