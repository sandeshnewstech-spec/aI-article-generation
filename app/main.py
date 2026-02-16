import sys
import asyncio


from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.routers import api_router, ui_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# Mount static files (if any in future)
# app.mount("/static", StaticFiles(directory="static"), name="static")

# Include Routers
app.include_router(api_router.router, prefix="/api")
app.include_router(ui_router.router)

# Include Newspaper Router
from app.routers import newspaper_router

app.include_router(newspaper_router.router, prefix="/api")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host="127.0.0.1", port=8000, reload=True, loop="asyncio"
    )
