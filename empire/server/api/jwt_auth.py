from datetime import datetime, timedelta
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette import status

from empire.server.api.v2.shared_dependencies import CurrentSession
from empire.server.core.db import models
from empire.server.core.db.base import SessionLocal

# This all comes from the amazing fastapi docs: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
SECRET_KEY = SessionLocal().query(models.Config).first().jwt_secret_key
ALGORITHM = "HS256"

# Long token expiration until refresh token is implemented
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


# Support both Authorization header and custom header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
api_key_header = APIKeyHeader(name="X-Empire-Token", auto_error=False)


def verify_password(plain_password, hashed_password):
    password_byte_enc = plain_password.encode("utf-8")
    return bcrypt.checkpw(password_byte_enc, hashed_password.encode("utf-8"))


def get_password_hash(plain_password: str) -> str:
    pwd_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def get_user(db, username: str) -> models.User:
    return db.query(models.User).filter(models.User.username == username).first()


def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user:
        return False
    if not user.enabled:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_token_from_headers(request: Request) -> str:
    """Check both Authorization and X-Empire-Token headers for JWT token"""
    token = request.headers.get("X-Empire-Token")
    if token:
        # Remove 'Bearer ' prefix if present
        return token.removeprefix("Bearer ")

    auth_header = request.headers.get("Authorization")
    if auth_header:
        return auth_header.removeprefix("Bearer ")

    # No valid token found in either header
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials - token required in either 'Authorization' or 'X-Empire-Token' header",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user_from_token(
    db: CurrentSession,
    token: str,
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError as e:
        raise credentials_exception from e
    except HTTPException:
        # Re-raise HTTPExceptions from get_token_from_headers
        raise
    user = get_user(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_user(
    db: CurrentSession,
    request: Request,
):
    token = get_token_from_headers(request)
    return await get_current_user_from_token(db, token)


CurrentUser = Annotated[models.User, Depends(get_current_user)]


async def get_current_active_user(
    current_user: CurrentUser,
):
    if not current_user.enabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


CurrentActiveUser = Annotated[models.User, Depends(get_current_active_user)]


async def get_current_active_admin_user(
    current_user: CurrentUser,
):
    if not current_user.enabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    if not current_user.admin:
        raise HTTPException(status_code=403, detail="Not an admin user")
    return current_user


CurrentActiveAdminUser = Annotated[models.User, Depends(get_current_active_admin_user)]
