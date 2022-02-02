from datetime import timedelta

from fastapi import HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from starlette import status

from empire.server.database import models
from empire.server.server import main
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.jwt_auth import Token, authenticate_user, ACCESS_TOKEN_EXPIRE_MINUTES, \
    create_access_token, get_current_active_user, get_password_hash, get_current_active_admin_user
from empire.server.v2.api.shared_dependencies import get_db
from empire.server.v2.api.user.user_dto import domain_to_dto_user, User, UserPostRequest, UserUpdateRequest, \
    UserUpdatePasswordRequest, Users

user_service = main.usersv2

# no prefix so /token can be at root.
# Might also just move auth out of user router.
router = APIRouter(
    tags=["users"],
    responses={404: {"description": "Not found"}},
)


async def get_user(uid: int,
                   db: Session = Depends(get_db)):
    user = user_service.get_by_id(db, uid)

    if user:
        return user

    raise HTTPException(status_code=404, detail=f"User not found for id {uid}")


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(),
                                 db: Session = Depends(get_db)):
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


@router.get("/api/v2beta/users/me", response_model=User)
async def read_user_me(current_user: User = Depends(get_current_active_user)):
    return domain_to_dto_user(current_user)


@router.get("/api/v2beta/users", response_model=Users, dependencies=[Depends(get_current_active_user)])
async def read_users(db: Session = Depends(get_db)):
    users = list(map(lambda x: domain_to_dto_user(x), user_service.get_all(db)))

    return {'records': users}


@router.get("/api/v2beta/users/{uid}", response_model=User, dependencies=[Depends(get_current_active_user)])
async def read_user(uid: int,
                    db_user: models.User = Depends(get_user)):
    return domain_to_dto_user(db_user)


@router.post('/api/v2beta/users/', status_code=201, dependencies=[Depends(get_current_active_admin_user)])
async def create_user(user: UserPostRequest,
                      db: Session = Depends(get_db)):
    resp, err = user_service.create_user(db, user.username, get_password_hash(user.password), user.is_admin)

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_user(resp)


@router.put('/api/v2beta/users/{uid}', response_model=User)
async def update_user(uid: int,
                      user_req: UserUpdateRequest,
                      current_user: models.User = Depends(get_current_active_user),
                      db: Session = Depends(get_db),
                      db_user: models.User = Depends(get_user)):
    if not (current_user.admin or current_user.id == uid):
        raise HTTPException(status_code=403, detail="User does not have access to update this resource.")

    if user_req.is_admin != db_user.admin:
        if not current_user.admin:
            raise HTTPException(status_code=403, detail="User does not have access to update admin status.")

    # update
    resp, err = user_service.update_user(db, db_user, user_req)

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_user(resp)


@router.put('/api/v2beta/users/{uid}/password', response_model=User)
async def update_user_password(uid: int,
                               user_req: UserUpdatePasswordRequest,
                               current_user: models.User = Depends(get_current_active_user),
                               db: Session = Depends(get_db),
                               db_user: models.User = Depends(get_user)):
    if not current_user.id == uid:
        raise HTTPException(status_code=403, detail="User does not have access to update this resource.")

    # update
    resp, err = user_service.update_user_password(db, db_user, get_password_hash(user_req.password))

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_user(resp)
