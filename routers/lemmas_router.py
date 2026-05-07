from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy.orm import Session
from db import get_db
from models import UserLemma, User
from .auth_router import get_current_user
from pydantic import BaseModel
from sqlalchemy.dialects.sqlite import insert

router = APIRouter(prefix="/api")


class FavoriteRequest(BaseModel):
    key: str


class FavoriteBatchRequest(BaseModel):
    keys: list[str]


@router.post("/lemma/favorite")
def add_favorite(
    req: FavoriteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = insert(UserLemma).values(
        user_id=current_user.id,
        lemma_key=req.key
    ).on_conflict_do_nothing()

    db.execute(stmt)
    db.commit()

    return {
        "key": req.key,
        "is_favorite": True
    }


@router.delete("/lemma/favorite")
def remove_favorite(
    req: FavoriteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    row = db.query(UserLemma).filter_by(
        user_id=current_user.id,
        lemma_key=req.key
    ).first()

    if row:
        db.delete(row)
        db.commit()

    return {
        "key": req.key,
        "is_favorite": False
    }


@router.post("/lemma/favorite/check")
def check_favorites(
    req: FavoriteBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rows = db.query(UserLemma.lemma_key).filter(
        UserLemma.user_id == current_user.id,
        UserLemma.lemma_key.in_(req.keys)
    ).all()

    favorites = {r[0] for r in rows}

    return {
        "favorites": list(favorites)
    }

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