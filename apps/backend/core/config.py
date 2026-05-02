import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")


@dataclass
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./krisha_app.db")
    jwt_secret: str = os.getenv("JWT_SECRET", "change_me")
    jwt_alg: str = os.getenv("JWT_ALG", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    admin_email: str = os.getenv("ADMIN_EMAIL", "admin@pricepal.local")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "admin12345")


settings = Settings()
