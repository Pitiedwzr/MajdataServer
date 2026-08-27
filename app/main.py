import contextlib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db, AsyncSessionLocal
from app.services.chart_scanner import scan_and_sync_charts
from app.routers import (
    account_router,
    maichart_router,
    score_router,
    collection_router,
    interaction_router,
    machine_persist_router,
    stats_router,
    utils_router,
)

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB and scan charts
    print("Starting MajdataServer...")
    await init_db()
    print("Database tables initialized.")
    
    async with AsyncSessionLocal() as session:
        count = await scan_and_sync_charts(session)
        print(f"Chart scan completed: {count} charts loaded.")
        
    yield
    # Shutdown
    print("Shutting down MajdataServer...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for Web Frontend compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, configure specific allowed frontend domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers under /api
api_routers = [
    account_router,
    maichart_router,
    score_router,
    collection_router,
    interaction_router,
    machine_persist_router,
    stats_router,
    utils_router,
]

for r in api_routers:
    app.include_router(r, prefix=settings.API_PREFIX)
    # Also include under /api3/api for direct frontend proxy compatibility
    app.include_router(r, prefix=settings.API3_PREFIX)

@app.get("/")
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
