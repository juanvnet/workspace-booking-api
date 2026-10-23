"""Users: register, log in (get a token), read and update your own profile"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select

from app.auth import CurrentUser, create_access_token, hash_password, verify_password
from app.database import SessionDep
from app.models import Token, User, UserCreate, UserPublic, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, session: SessionDep) -> User:
    existing_user = session.exec(select(User).where(User.email == user_in.email)).first()
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User.model_validate(user_in, update={"hashed_password": hash_password(user_in.password)})
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.post("/token")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep) -> Token:
    """OAuth2 login: send the email as 'username' and the password, receive a JWT"""
    user = session.exec(select(User).where(User.email == form.username)).first()
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserPublic)
def read_me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserPublic)
def update_me(user_in: UserUpdate, session: SessionDep, user: CurrentUser) -> User:
    """Change your own email, name and/or password. Only the fields that are sent are updated"""
    user_data = user_in.model_dump(exclude_unset=True, exclude_none=True)
    if "email" in user_data and user_data["email"] != user.email:
        existing_user = session.exec(select(User).where(User.email == user_data["email"])).first()
        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
            )
    if "password" in user_data:
        user_data["hashed_password"] = hash_password(user_data.pop("password"))
    user.sqlmodel_update(user_data)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
