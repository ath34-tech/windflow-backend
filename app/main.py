import asyncio
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import settings
from .services.data_loader import data_loader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("windscope.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle manager."""
    logger.info("Starting WindScope FastAPI Backend...")
    logger.info("Allowed CORS origins: %s", settings.cors_origin_list)

    if settings.PRELOAD_ON_STARTUP:
        # Initialize data in the background so health checks stay fast and responsive
        asyncio.create_task(data_loader.initialize())

    yield
    logger.info("Shutting down WindScope Backend.")

app = FastAPI(
    title="WindScope API",
    version="1.0.0",
    description="UK National Wind Generation Forecasting & Accuracy Backend for Day-Ahead Electricity Trading.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS to allow all origins for seamless frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/", tags=["root"])
async def root():
    return {
        "service": "WindScope API",
        "status": "operational",
        "docs": "/docs",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
