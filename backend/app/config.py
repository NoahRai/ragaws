from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CloudMind"
    database_url: str = "sqlite:///./cloudmind.db"
    jwt_secret: str = "replace-me-with-a-32-byte-minimum-secret"
    jwt_algorithm: str = "HS256"
    max_upload_bytes: int = 10 * 1024 * 1024
    embedding_dimensions: int = 256
    embedding_provider: str = "semantic"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    semantic_embedding_dimensions: int = 384
    storage_backend: str = "local"
    s3_bucket: str | None = None
    aws_region: str = "us-east-1"
    presigned_url_expiry_seconds: int = 300
    queue_backend: str = "local"
    sqs_queue_url: str | None = None
    worker_wait_seconds: int = 20
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CLOUDMIND_")


settings = Settings()
