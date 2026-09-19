import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

from app.core.database import Base, engine
from app.routers import (
    admin_projects_router,
    agents_router,
    auth_router,
    chats_router,
    client_projects_router,
    projects_router,
    storage_router,
    websocket_router,
    admin_users_router,
    generator_router,
    platforms_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables on startup (dev mode)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="CerebrumKit API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    """Attach baseline security headers to every response.

    These are safe for the JSON API and for the Swagger/ReDoc pages: none of
    them blocks the docs' own CDN assets, they only stop the API being framed,
    sniffed as a different content type, or leaking the full URL as a referrer.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    return response

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(chats_router)
app.include_router(client_projects_router)
app.include_router(admin_projects_router)
app.include_router(agents_router)
app.include_router(storage_router)
app.include_router(websocket_router)
app.include_router(admin_users_router)
app.include_router(generator_router)
app.include_router(platforms_router)


@app.get("/health")
def health():
    return {"status": "ok"}
