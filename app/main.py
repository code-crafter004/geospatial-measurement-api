import logging

from fastapi import FastAPI

from app.api.routes_files import router as files_router
from app.config import settings
from app.core.errors import register_error_handlers
from app.db import models  # noqa: F401  (registers tables)
from app.db.session import Base, engine


def create_app() -> FastAPI:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    Base.metadata.create_all(bind=engine)
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    register_error_handlers(app)
    app.include_router(files_router)

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "version": settings.app_version}

    return app


app = create_app()
