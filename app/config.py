from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Geospatial Measurement API"
    app_version: str = "0.3.0"
    max_upload_mb: int = 25
    database_url: str = "sqlite:///./geo.db"
    upload_dir: str = "uploads"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
