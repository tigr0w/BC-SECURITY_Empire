from datetime import timedelta

from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from starlette import status

from empire.server.api.api_router import APIRouter
from empire.server.api.jwt_auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    Token,
    authenticate_user,
    create_access_token,
    get_current_active_admin_user,
    get_current_active_user,
    get_password_hash,
)
from empire.server.api.v2.shared_dependencies import get_db
from empire.server.api.v2.shared_dto import BadRequestResponse, NotFoundResponse
from empire.server.api.v2.user.user_dto import (
    User,
    UserPostRequest,
    Users,
    UserUpdatePasswordRequest,
    UserUpdateRequest,
    domain_to_dto_user,
)
from empire.server.core.db import models
from empire.server.server import main

user_service = main.usersv2

# no prefix so /token can be at root.
# Might also just move auth out of user router.
router = APIRouter(
    tags=["users"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
)


async def get_user(uid: int, db: Session = Depends(get_db)):
    user = user_service.get_by_id(db, uid)

    if user:
        return user

    raise HTTPException(status_code=404, detail=f"User not found for id {uid}")


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/api/v2/users/me", response_model=User)
async def read_user_me(current_user: User = Depends(get_current_active_user)):
    return domain_to_dto_user(current_user)


@router.get(
    "/api/v2/users",
    response_model=Users,
    dependencies=[Depends(get_current_active_user)],
)
async def read_users(db: Session = Depends(get_db)):
    users = list(map(lambda x: domain_to_dto_user(x), user_service.get_all(db)))

    return {"records": users}


@router.get(
    "/api/v2/users/{uid}",
    response_model=User,
    dependencies=[Depends(get_current_active_user)],
)
async def read_user(uid: int, db_user: models.User = Depends(get_user)):
    return domain_to_dto_user(db_user)


@router.post(
    "/api/v2/users/",
    status_code=201,
    dependencies=[Depends(get_current_active_admin_user)],
)
async def create_user(user: UserPostRequest, db: Session = Depends(get_db)):
    resp, err = user_service.create_user(
        db, user.username, get_password_hash(user.password), user.is_admin
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_user(resp)


@router.put("/api/v2/users/{uid}", response_model=User)
async def update_user(
    uid: int,
    user_req: UserUpdateRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    db_user: models.User = Depends(get_user),
):
    if not (current_user.admin or current_user.id == uid):
        raise HTTPException(
            status_code=403, detail="User does not have access to update this resource."
        )

    if user_req.is_admin != db_user.admin:
        if not current_user.admin:
            raise HTTPException(
                status_code=403,
                detail="User does not have access to update admin status.",
            )

    # update
    resp, err = user_service.update_user(db, db_user, user_req)

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_user(resp)


@router.put("/api/v2/users/{uid}/password", response_model=User)
async def update_user_password(
    uid: int,
    user_req: UserUpdatePasswordRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    db_user: models.User = Depends(get_user),
):
    if not current_user.id == uid:
        raise HTTPException(
            status_code=403, detail="User does not have access to update this resource."
        )

    # update
    resp, err = user_service.update_user_password(
        db, db_user, get_password_hash(user_req.password)
    )

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_user(resp)


@router.post("/api/v2/users/{uid}/avatar", status_code=201)
async def create_avatar(
    uid: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_active_user),
    file: UploadFile = File(...),
):
    if not user.id == uid:
        raise HTTPException(
            status_code=403, detail="User does not have access to update this resource."
        )

    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")

    user_service.update_user_avatar(db, user, file)
