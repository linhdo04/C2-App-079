from .admin_routes import router as admin_router
from .agent_routes import router as agent_router
from .auth_routes import router as auth_router
from .dashboard_routes import router as dashboard_router
from .drone_routes import router as drone_router

__all__ = [
    "admin_router",
    "agent_router",
    "auth_router",
    "dashboard_router",
    "drone_router",
]
