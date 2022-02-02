from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session

from empire.server.database import models
from empire.server.server import main
from empire.server.v2.api.EmpireApiRouter import APIRouter
from empire.server.v2.api.jwt_auth import get_current_active_user
from empire.server.v2.api.keyword.keyword_dto import Keyword, KeywordPostRequest, \
    KeywordUpdateRequest, Keywords
from empire.server.v2.api.shared_dependencies import get_db

keyword_service = main.keywordsv2

router = APIRouter(
    prefix="/api/v2beta/keywords",
    tags=["keywords"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(get_current_active_user)],
)


async def get_keyword(uid: int,
                      db: Session = Depends(get_db)):
    keyword = keyword_service.get_by_id(db, uid)

    if keyword:
        return keyword

    raise HTTPException(404, f'Keyword not found for id {uid}')


@router.get("/{uid}", response_model=Keyword)
async def read_keyword(uid: int,
                       db_keyword: models.Keyword = Depends(get_keyword)):
    return db_keyword


@router.get("/", response_model=Keywords)
async def read_keywords(db: Session = Depends(get_db)):
    keywords = keyword_service.get_all(db)

    return {'records': keywords}


# todo make keyword optional and randomly generate one if not provided
@router.post('/', status_code=201, response_model=Keyword)
async def create_keyword(keyword_req: KeywordPostRequest,
                         db: Session = Depends(get_db)):
    resp, err = keyword_service.create_keyword(db, keyword_req)

    if err:
        raise HTTPException(status_code=400, detail=err)

    return resp


@router.put("/{uid}", response_model=Keyword)
async def update_keyword(uid: int,
                         keyword_req: KeywordUpdateRequest,
                         db: Session = Depends(get_db),
                         db_keyword: models.Keyword = Depends(get_keyword)):
    resp, err = keyword_service.update_keyword(db, db_keyword, keyword_req)

    if err:
        raise HTTPException(status_code=400, detail=err)

    return resp


@router.delete("/{uid}", status_code=204)
async def delete_keyword(uid: str,
                         db: Session = Depends(get_db),
                         db_keyword: models.Keyword = Depends(get_keyword)):
    keyword_service.delete_keyword(db, db_keyword)
