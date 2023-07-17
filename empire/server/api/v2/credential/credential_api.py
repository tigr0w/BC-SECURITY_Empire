from typing import Optional

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.responses import Response
from starlette.status import HTTP_204_NO_CONTENT

from empire.server.api.api_router import APIRouter
from empire.server.api.jwt_auth import get_current_active_user
from empire.server.api.v2.credential.credential_dto import (
    Credential,
    CredentialPostRequest,
    Credentials,
    CredentialUpdateRequest,
    domain_to_dto_credential,
)
from empire.server.api.v2.shared_dependencies import get_db
from empire.server.api.v2.shared_dto import BadRequestResponse, NotFoundResponse
from empire.server.api.v2.tag import tag_api
from empire.server.core.db import models
from empire.server.server import main

credential_service = main.credentialsv2

router = APIRouter(
    prefix="/api/v2/credentials",
    tags=["credentials"],
    responses={
        404: {"description": "Not found", "model": NotFoundResponse},
        400: {"description": "Bad request", "model": BadRequestResponse},
    },
    dependencies=[Depends(get_current_active_user)],
)


async def get_credential(uid: int, db: Session = Depends(get_db)):
    credential = credential_service.get_by_id(db, uid)

    if credential:
        return credential

    raise HTTPException(404, f"Credential not found for id {uid}")


tag_api.add_endpoints_to_taggable(router, "/{uid}/tags", get_credential)


@router.get("/{uid}", response_model=Credential)
async def read_credential(
    uid: int, db_credential: models.Credential = Depends(get_credential)
):
    return domain_to_dto_credential(db_credential)


@router.get("/", response_model=Credentials)
async def read_credentials(
    db: Session = Depends(get_db),
    search: Optional[str] = None,
    credtype: Optional[str] = None,
):
    credentials = list(
        map(
            lambda x: domain_to_dto_credential(x),
            credential_service.get_all(db, search, credtype),
        )
    )

    return {"records": credentials}


@router.post(
    "/",
    status_code=201,
    response_model=Credential,
)
async def create_credential(
    credential_req: CredentialPostRequest, db: Session = Depends(get_db)
):
    resp, err = credential_service.create_credential(db, credential_req)

    if err:
        raise HTTPException(status_code=400, detail=err)

    return domain_to_dto_credential(resp)


@router.put("/{uid}", response_model=Credential)
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
    "/{uid}",
    status_code=HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_credential(
    uid: str,
    db: Session = Depends(get_db),
    db_credential: models.Credential = Depends(get_credential),
):
    credential_service.delete_credential(db, db_credential)
