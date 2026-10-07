from fastapi import FastAPI

from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version)

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "version": settings.app_version}

    return app


app = create_app()
