from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from packs import PACKS

from db import get_db
from models import UserLemma

router = APIRouter(prefix="/api")


# -----------------------------
# FAVORITE BATCH CHECK
# -----------------------------

class BatchFavoriteCheckRequest(BaseModel):
    user_id: int
    lemma_keys: List[str]


class BatchFavoriteCheckResponse(BaseModel):
    favorites: List[str]


@router.post("/user-lemmas/batch-check", response_model=BatchFavoriteCheckResponse)
def batch_check_favorites(
    req: BatchFavoriteCheckRequest,
    db: Session = Depends(get_db)
):
    if not req.lemma_keys:
        return {"favorites": []}

    rows = db.query(UserLemma.lemma_key).filter(
        UserLemma.user_id == req.user_id,
        UserLemma.lemma_key.in_(req.lemma_keys)
    ).all()

    return {
        "favorites": [r[0] for r in rows]
    }

@router.get("/lang/packs")
def get_packs():
    return PACKS