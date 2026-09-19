from app.routers.auth import router as auth_router
from app.routers.projects import admin_router as admin_projects_router, client_router as client_projects_router, router as projects_router
from app.routers.chats import router as chats_router
from app.routers.agents import router as agents_router
from app.routers.storage import router as storage_router
from app.routers.websocket import router as websocket_router
from app.routers.users import router as admin_users_router
from app.routers.generator import router as generator_router
from app.routers.platforms import router as platforms_router

__all__ = ["admin_projects_router", "agents_router", "auth_router", "chats_router", "client_projects_router", "projects_router", "storage_router", "websocket_router", "admin_users_router", "generator_router", "platforms_router"]
