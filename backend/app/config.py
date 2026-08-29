from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CloudMind"
    database_url: str = "sqlite:///./cloudmind.db"
    jwt_secret: str = "replace-me-with-a-32-byte-minimum-secret"
    jwt_algorithm: str = "HS256"
    max_upload_bytes: int = 10 * 1024 * 1024
    embedding_dimensions: int = 256

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CLOUDMIND_")


settings = Settings()
