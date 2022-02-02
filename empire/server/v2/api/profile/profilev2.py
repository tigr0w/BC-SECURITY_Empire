from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session

from empire.server.database import models
from empire.server.server import main
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.jwt_auth import get_current_active_user
from empire.server.v2.api.profile.profile_dto import Profile, ProfileUpdateRequest, \
    ProfilePostRequest, Profiles
from empire.server.v2.api.shared_dependencies import get_db

profile_service = main.profilesv2

router = APIRouter(
    prefix="/api/v2beta/malleable-profiles",
    tags=["malleable-profiles"],
    responses={404: {"description": "Not found"}},
)


async def get_profile(uid: int,
                      db: Session = Depends(get_db)):
    profile = profile_service.get_by_id(db, uid)

    if profile:
        return profile

    raise HTTPException(status_code=404, detail=f"Profile not found for id {uid}")


@router.get("/{uid}", response_model=Profile, dependencies=[Depends(get_current_active_user)])
async def read_profile(uid: int,
                       db_profile: models.Profile = Depends(get_profile)):
    return db_profile


@router.get("/", response_model=Profiles, dependencies=[Depends(get_current_active_user)])
async def read_profiles(db: Session = Depends(get_db)):
    profiles = profile_service.get_all(db)

    return {'records': profiles}


@router.post('/', status_code=201, response_model=Profile, dependencies=[Depends(get_current_active_user)])
async def create_profile(profile_req: ProfilePostRequest,
                         db: Session = Depends(get_db)):
    resp, err = profile_service.create_profile(db, profile_req)

    if err:
        raise HTTPException(status_code=400, detail=err)

    return resp


# todo should it write to the filesystem too.
@router.put("/{uid}", response_model=Profile, dependencies=[Depends(get_current_active_user)])
async def update_profile(uid: int,
                         profile_req: ProfileUpdateRequest,
                         db: Session = Depends(get_db),
                         db_profile: models.Profile = Depends(get_profile)):
    resp, err = profile_service.update_profile(db, db_profile, profile_req)

    if err:
        raise HTTPException(status_code=400, detail=err)

    return resp


@router.delete("/{uid}", status_code=204, dependencies=[Depends(get_current_active_user)])
async def delete_profile(uid: str,
                         db: Session = Depends(get_db),
                         db_profile: models.Profile = Depends(get_profile)):
    profile_service.delete_profile(db, db_profile)
