"""Application settings loaded from environment variables."""
import os
from dataclasses import dataclass


def normalize_database_url(value: str) -> str:
    """Support standard managed PostgreSQL URLs with the psycopg v3 driver."""
    if value.startswith('postgres://'):
        return 'postgresql+psycopg://' + value[len('postgres://'):]
    if value.startswith('postgresql://'):
        return 'postgresql+psycopg://' + value[len('postgresql://'):]
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str = normalize_database_url(os.getenv('DATABASE_URL', 'sqlite:///./shopsense.db'))
    jwt_secret: str = os.getenv('JWT_SECRET', 'dev-only-change-me-use-longer-key-here')
    jwt_expires_minutes: int = int(os.getenv('JWT_EXPIRES_MINUTES', '120'))
    environment: str = os.getenv('ENVIRONMENT', 'development')
    cors_origins: tuple[str, ...] = tuple(x.strip() for x in os.getenv('CORS_ORIGINS', 'http://localhost:8501').split(',') if x.strip())


settings = Settings()
if settings.environment == 'production' and (settings.jwt_secret == 'dev-only-change-me-use-longer-key-here' or len(settings.jwt_secret) < 32):
    raise RuntimeError('Set a strong JWT_SECRET (32+ characters) for production')
