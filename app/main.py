import sys
import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.routers import ui_router
from app.core.config import settings
from app.core.database import connect_db, close_db
import traceback
from fastapi import Request
from fastapi.responses import JSONResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect to MongoDB on startup
    await connect_db()
    yield
    # Disconnect on shutdown
    await close_db()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"❌ GLOBAL EXCEPTION: {exc}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error", "detail": str(exc)},
    )

# Mount static files for local image storage using absolute path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_path = os.path.join(BASE_DIR, "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/check")
async def check_health():
    return {"status": "ok", "message": "Server is responding!"}

# Include Routers
app.include_router(ui_router.router)

# Include Newspaper Router
from app.routers import newspaper_router
app.include_router(newspaper_router.router, prefix="/api")

# Include Category & Slot Routers (MongoDB-backed)
from app.routers import category_router, slot_router, history_router, auth_router, user_router
app.include_router(auth_router.router, prefix="/api")
app.include_router(user_router.router, prefix="/api")
app.include_router(category_router.router, prefix="/api")
app.include_router(slot_router.router, prefix="/api")
app.include_router(history_router.router, prefix="/api")

# Include Image Router (search + generate)
from app.routers import image_router
app.include_router(image_router.router, prefix="/api")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host="127.0.0.1", port=8000, reload=True, loop="asyncio"
    )
