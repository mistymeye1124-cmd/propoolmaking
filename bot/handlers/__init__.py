from aiogram import Dispatcher
from .start import router as start_router
from .poll_create import router as poll_create_router
from .voting import router as voting_router
from .poll_manage import router as poll_manage_router
from .admin import router as admin_router

def register_all_handlers(dp: Dispatcher):
    dp.include_router(admin_router)
    dp.include_router(start_router)
    dp.include_router(poll_manage_router)
    dp.include_router(poll_create_router)
    dp.include_router(voting_router)
