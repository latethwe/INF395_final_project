import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./krisha_app.db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change_me")
    jwt_alg: str = os.getenv("JWT_ALG", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")
    ml_enabled: bool = _env_bool("ML_ENABLED", True)
    external_ml_api_base: str = os.getenv("EXTERNAL_ML_API_BASE", "").strip()


settings = Settings()
