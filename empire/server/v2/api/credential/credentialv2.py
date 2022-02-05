from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from empire.server.database import models
from empire.server.server import main
from empire.server.v2.api.credential.credential_dto import (
    Credential,
    CredentialPostRequest,
    Credentials,
    CredentialUpdateRequest,
    domain_to_dto_credential,
)
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.jwt_auth import get_current_active_user
from empire.server.v2.api.shared_dependencies import get_db

credential_service = main.credentialsv2

router = APIRouter(
    prefix="/api/v2beta/credentials",
    tags=["credentials"],
    responses={404: {"description": "Not found"}},
)


async def get_credential(uid: int, db: Session = Depends(get_db)):
    credential = credential_service.get_by_id(db, uid)

    if credential:
        return credential

    raise HTTPException(404, f"Credential not found for id {uid}")


@router.get(
    "/{uid}", response_model=Credential, dependencies=[Depends(get_current_active_user)]
)
async def read_credential(
    uid: int, db_credential: models.Credential = Depends(get_credential)
):
    return domain_to_dto_credential(db_credential)


@router.get(
    "/", response_model=Credentials, dependencies=[Depends(get_current_active_user)]
)
async def read_credentials(db: Session = Depends(get_db)):
    credentials = list(
        map(lambda x: domain_to_dto_credential(x), credential_service.get_all(db))
    )

    return {"records": credentials}


@router.post(
    "/",
    status_code=201,
    response_model=Credential,
    dependencies=[Depends(get_current_active_user)],
)
async def create_credential(
    credential_req: CredentialPostRequest, db: Session = Depends(get_db)
):
    resp, err = credential_service.create_credential(db, credential_req)

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_credential(resp)


@router.put(
    "/{uid}", response_model=Credential, dependencies=[Depends(get_current_active_user)]
)
async def update_credential(
    uid: int,
    credential_req: CredentialUpdateRequest,
    db: Session = Depends(get_db),
    db_credential: models.Credential = Depends(get_credential),
):
    resp, err = credential_service.update_credential(db, db_credential, credential_req)

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_credential(resp)


@router.delete(
    "/{uid}", status_code=204, dependencies=[Depends(get_current_active_user)]
)
async def delete_credential(
    uid: str,
    db: Session = Depends(get_db),
    db_credential: models.Credential = Depends(get_credential),
):
    credential_service.delete_credential(db, db_credential)
