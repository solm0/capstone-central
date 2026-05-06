from fastapi import Depends, APIRouter
from sqlalchemy.orm import Session
from db import get_db
from models import UserLemma, User
from .auth_router import get_current_user, get_current_user_optional
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api")

def to_local_key(lemma: str, pos: str) -> str:
    return f"{lemma}_{pos}"

def to_global_key(lemma: str, pos: str, lang: str) -> str:
    return f"{lemma}/{pos}/{lang}"

def parse_global_key(key: str):
    lemma, pos, lang = key.split("/")
    return lemma, pos, lang

class FavoriteToggleRequest(BaseModel):
    key: str

class LookupRequest(BaseModel):
    lemma: str
    pos: str
    language: str

class BatchRequest(BaseModel):
    items: list[dict]
    language: str

@router.post("/lemma/favorite/toggle")
def toggle_favorite(req: FavoriteToggleRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from sqlalchemy.dialects.sqlite import insert

    try:
        lemma, pos, lang = parse_global_key(req.key)
    except:
        raise ValueError("invalid key format")

    stmt = insert(UserLemma).values(
        user_id=current_user.id,
        lemma_key=req.key
    ).on_conflict_do_nothing()

    result = db.execute(stmt)
    db.commit()

    if result.rowcount > 0:
        return {"key": req.key, "is_favorite": True}

    # 이미 존재 → 삭제
    row = db.query(UserLemma).filter_by(
        user_id=current_user.id,
        lemma_key=req.key
    ).first()

    if row:
        db.delete(row)
        db.commit()

    return {"key": req.key, "is_favorite": False}


@router.get("/lemma/favorites")
def get_favorites(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rows = db.query(UserLemma.lemma_key).filter(
        UserLemma.user_id == current_user.id
    ).all()

    return {
        "items": [r[0] for r in rows]
    }