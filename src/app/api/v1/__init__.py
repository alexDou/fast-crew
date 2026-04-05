from fastapi import APIRouter

from .health import router as health_router
from .login import router as login_router
from .logout import router as logout_router
from .poem import router as poem_router
from .poem_source import router as poem_source_router
from .users import router as users_router

router = APIRouter(prefix="/v1")
router.include_router(health_router)
router.include_router(login_router)
router.include_router(logout_router)
router.include_router(users_router)
router.include_router(poem_source_router)
router.include_router(poem_router)
