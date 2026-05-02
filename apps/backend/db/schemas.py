from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class PasswordChangeRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class HistoryOut(BaseModel):
    id: int
    user_id: int
    mode: str
    predicted_price: float | None
    predicted_price_per_m2: float | None
    source_url: str | None
    created_at: datetime
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
