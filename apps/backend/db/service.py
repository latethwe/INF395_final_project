import json
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.security import hash_password, verify_password
from .models import PredictionHistory, User
from .schemas import UserOut
from .session import Base, engine, get_db


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def ensure_admin_exists(db: Session) -> None:
    stmt = select(User).where(User.email == settings.admin_email)
    admin = db.execute(stmt).scalar_one_or_none()
    if admin:
        return
    admin = User(
        email=settings.admin_email,
        password_hash=hash_password(settings.admin_password),
        role="admin",
        is_active=True,
    )
    db.add(admin)
    db.commit()


def to_user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, role=user.role, created_at=user.created_at)


def create_user(db: Session, email: str, password: str, role: str = "user") -> User:
    user = User(email=email.lower().strip(), password_hash=hash_password(password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    stmt = select(User).where(User.email == email.lower().strip())
    user = db.execute(stmt).scalar_one_or_none()
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
        sub = payload.get("sub")
        if not sub:
            raise credentials_exc
        user_id = int(sub)
    except (JWTError, ValueError):
        raise credentials_exc

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise credentials_exc
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def save_history(
    db: Session,
    *,
    user_id: int,
    mode: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    predicted_price: float | None,
    predicted_price_per_m2: float | None,
    source_url: str | None = None,
) -> PredictionHistory:
    item = PredictionHistory(
        user_id=user_id,
        mode=mode,
        request_payload=json.dumps(request_payload, ensure_ascii=False),
        response_payload=json.dumps(response_payload, ensure_ascii=False),
        predicted_price=predicted_price,
        predicted_price_per_m2=predicted_price_per_m2,
        source_url=source_url,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def parse_history_payload(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"value": data}
    except Exception:
        return {"raw": raw}


def serialize_history(item: PredictionHistory) -> dict[str, Any]:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "mode": item.mode,
        "predicted_price": item.predicted_price,
        "predicted_price_per_m2": item.predicted_price_per_m2,
        "source_url": item.source_url,
        "created_at": item.created_at,
        "request_payload": parse_history_payload(item.request_payload),
        "response_payload": parse_history_payload(item.response_payload),
    }
