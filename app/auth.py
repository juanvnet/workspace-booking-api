"""Authentication: password hashing, JWT tokens and the current user dependencies"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from app.config import settings
from app.database import SessionDep, engine
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/token")


def hash_password(password: str) -> str:
    # bcrypt only uses the first 72 bytes of a password
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode()[:72], hashed_password.encode())


def create_access_token(user_id: int) -> str:
    """Create a JWT that identifies the user and expires after a few minutes"""
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep) -> User:
    """Return the user that owns the token, or answer 401"""
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise credentials_error from None

    user = session.get(User, user_id)
    if user is None:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_admin(user: CurrentUser) -> User:
    """Return the current user if it is an admin, or answer 403"""
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user


AdminUser = Annotated[User, Depends(get_current_admin)]


def create_first_admin() -> None:
    """Create the admin account from ADMIN_EMAIL / ADMIN_PASSWORD if it does not exist yet"""
    if not settings.admin_email or not settings.admin_password:
        return

    with Session(engine) as session:
        existing = session.exec(select(User).where(User.email == settings.admin_email))
        if existing.first() is not None:
            return
        admin = User(
            email=settings.admin_email,
            full_name="Administrator",
            hashed_password=hash_password(settings.admin_password),
            is_admin=True,
        )
        session.add(admin)
        session.commit()
