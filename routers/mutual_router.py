from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import json
from sqlalchemy import func

from db import get_db
from models import Mutual, User, Annotation, Page, Comment
from .auth_router import get_current_user

router = APIRouter(prefix="/api/mutuals", tags=["mutuals"])


def normalize_pair(a: int, b: int):
    return (a, b) if a < b else (b, a)


# ===== 요청 보내기 =====
@router.post("/request")
def request_mutual(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    email = payload.get("email")
    if not email:
        raise HTTPException(400, "email required")

    target = db.query(User).filter(User.email == email).first()
    if not target:
        raise HTTPException(404, "user not found")

    if target.id == current_user.id:
        raise HTTPException(400, "cannot self connect")

    u1, u2 = normalize_pair(current_user.id, target.id)

    existing = db.query(Mutual).filter(
        Mutual.user1_id == u1,
        Mutual.user2_id == u2
    ).first()

    if existing:
        return {"ok": True, "status": existing.status}

    m = Mutual(
        user1_id=u1,
        user2_id=u2,
        requester_id=current_user.id,
        status="pending",
        created_at=datetime.utcnow()
    )

    db.add(m)
    db.commit()

    return {"ok": True}


# ===== 받은 요청 =====
@router.get("/requests")
def get_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rows = db.query(Mutual).filter(
        Mutual.status == "pending",
        (
            (Mutual.user1_id == current_user.id) |
            (Mutual.user2_id == current_user.id)
        ),
        Mutual.requester_id != current_user.id
    ).all()

    other_ids = [
        r.user2_id if r.user1_id == current_user.id else r.user1_id
        for r in rows
    ]

    users = db.query(User).filter(User.id.in_(other_ids)).all()
    user_map = {u.id: u for u in users}

    return [
        {
            "id": r.id,
            "user": {
                "id": other_id,
                "name": user_map[other_id].name,
                "email": user_map[other_id].email
            },
        }
        for r in rows
        for other_id in [
            r.user2_id if r.user1_id == current_user.id else r.user1_id
        ]
    ]


# ===== pending 보낸 요청 =====
@router.get("/sent")
def get_sent_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rows = db.query(Mutual).filter(
        Mutual.status == "pending",
        Mutual.requester_id == current_user.id
    ).all()

    other_ids = [
        r.user2_id if r.user1_id == current_user.id else r.user1_id
        for r in rows
    ]

    users = db.query(User).filter(User.id.in_(other_ids)).all()
    user_map = {u.id: u for u in users}

    return {
        "items": [
            {
                "id": other_id,
                "name": user_map[other_id].name,
                "email": user_map[other_id].email
            }
            for r in rows
            for other_id in [
                r.user2_id if r.user1_id == current_user.id else r.user1_id
            ]
        ]
    }

# ===== 수락 =====
@router.post("/{mutual_id}/accept")
def accept_mutual(
    mutual_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    m = db.query(Mutual).filter(Mutual.id == mutual_id).first()

    if not m:
        raise HTTPException(404, "not found")

    if m.status != "pending":
        raise HTTPException(400, "already handled")

    if m.requester_id == current_user.id:
        raise HTTPException(403, "forbidden")

    if current_user.id not in (m.user1_id, m.user2_id):
        raise HTTPException(403, "forbidden")

    m.status = "accepted"
    db.commit()

    return {"ok": True}


# ===== 내 mutual 리스트 =====
@router.get("")
def get_mutuals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rows = db.query(Mutual).filter(
        Mutual.status == "accepted",
        (Mutual.user1_id == current_user.id) |
        (Mutual.user2_id == current_user.id)
    ).all()

    ids = [
        r.user2_id if r.user1_id == current_user.id else r.user1_id
        for r in rows
    ]

    users = db.query(User).filter(User.id.in_(ids)).all()

    return {
        "items": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email
            }
            for u in users
        ]
    }


# ===== 타임라인 =====
@router.get("/timeline")
def get_timeline(
    cursor_created_at: Optional[datetime] = None,
    cursor_id: Optional[int] = None,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rows = db.query(Mutual).filter(
        Mutual.status == "accepted",
        (Mutual.user1_id == current_user.id) |
        (Mutual.user2_id == current_user.id)
    ).all()

    mutual_ids = [
        r.user2_id if r.user1_id == current_user.id else r.user1_id
        for r in rows
    ]

    if not mutual_ids:
        return {"items": [], "next_cursor": None}
    
    comment_counts = (
        db.query(
            Comment.annotation_id,
            func.count(Comment.id).label("count")
        )
        .filter(Comment.deleted_at == None)
        .group_by(Comment.annotation_id)
        .subquery()
    )
    query = (
        db.query(Annotation, User, Page, comment_counts.c.count)
        .join(User, Annotation.user_id == User.id)
        .join(Page, Annotation.page_id == Page.id)
        .outerjoin(
            comment_counts,
            Annotation.id == comment_counts.c.annotation_id
        )
        .filter(Annotation.user_id.in_(mutual_ids))
    )

    if cursor_created_at and cursor_id:
        query = query.filter(
            (Annotation.created_at < cursor_created_at) |
            ((Annotation.created_at == cursor_created_at) & (Annotation.id < cursor_id))
        )

    query = query.order_by(
        Annotation.created_at.desc(),
        Annotation.id.desc()
    ).limit(limit + 1)

    rows = query.all()

    items = []
    for ann, user, page, count in rows[:limit]:
        result = json.loads(page.result_json)
        text = result["text"]

        tokens = text.split()
        source = " ".join(tokens[ann.start_index:ann.end_index + 1])

        items.append({
            "id": ann.id,
            "type": ann.type,
            "content": ann.content,
            "created_at": ann.created_at,
            "comment_count": count or 0,
            "user": {
                "id": user.id,
                "name": user.name
            },
            "page_id": page.id,
            "page_name": page.name,
            "source": source
        })

    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1][0]
        next_cursor = {
            "created_at": last.created_at.isoformat(),
            "id": last.id
        }

    return {
        "items": items,
        "next_cursor": next_cursor
    }