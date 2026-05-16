from models import Annotation, Mutual, Comment, User, Notification
from fastapi import APIRouter, Depends, HTTPException
from db import get_db
from sqlalchemy.orm import Session
from .auth_router import get_current_user
from datetime import datetime
from models import User, Comment
from typing import Optional

router = APIRouter(prefix="/api")

def can_access_annotation(db, user_id: int, annotation: Annotation):
    if annotation.user_id == user_id:
        return True

    u1, u2 = sorted([user_id, annotation.user_id])

    m = db.query(Mutual).filter(
        Mutual.user1_id == u1,
        Mutual.user2_id == u2,
        Mutual.status == "accepted"
    ).first()

    return m is not None


# ===== 댓글 생성 =====
@router.post("/annotations/{annotation_id}/comments")
def create_comment(
    annotation_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    annotation = db.query(Annotation).filter(Annotation.id == annotation_id).first()
    if not annotation:
        raise HTTPException(404, "annotation not found")

    if not can_access_annotation(db, current_user.id, annotation):
        raise HTTPException(403, "forbidden")

    parent_id = payload.get("parent_id")

    # depth 제한
    if parent_id:
        parent = db.query(Comment).filter(Comment.id == parent_id).first()
        if not parent or parent.parent_id is not None:
            raise HTTPException(400, "invalid parent")

    comment = Comment(
        annotation_id=annotation_id,
        user_id=current_user.id,
        parent_id=parent_id,
        content=payload["content"]
    )

    db.add(comment)
    db.commit()
    db.refresh(comment)

    # ===== notification =====
    if parent_id:
        # reply
        target_user = parent.user_id
        n_type = "reply"
    else:
        # comment
        target_user = annotation.user_id
        n_type = "comment"

    if target_user != current_user.id:
        notif = Notification(
            user_id=target_user,
            actor_id=current_user.id,
            type=n_type,
            comment_id=comment.id,
            annotation_id=annotation_id
        )
        db.add(notif)
        db.commit()

    return comment

# ===== 댓글 조회 =====

@router.get("/annotations/{annotation_id}/comments")
def get_comments(
    annotation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    annotation = db.query(Annotation).filter(Annotation.id == annotation_id).first()
    if not annotation:
        raise HTTPException(404, "annotation not found")

    if not can_access_annotation(db, current_user.id, annotation):
        raise HTTPException(403, "forbidden")

    rows = (
        db.query(Comment, User)
        .join(User, Comment.user_id == User.id)
        .filter(Comment.annotation_id == annotation_id)
        .order_by(Comment.created_at.asc())
        .all()
    )

    result = []
    for c, u in rows:
        result.append({
            "id": c.id,
            "parent_id": c.parent_id,
            "content": "[deleted]" if c.deleted_at else c.content,
            "deleted": c.deleted_at is not None,
            "created_at": c.created_at,

            "user": {
                "id": u.id,
                "name": u.name,
                "email": u.email,
            }
        })

    return result

# ===== 댓글 수정 =====
@router.patch("/comments/{comment_id}")
def update_comment(
    comment_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    c = db.query(Comment).filter(Comment.id == comment_id).first()

    if not c or c.deleted_at:
        raise HTTPException(404, "not found")

    if c.user_id != current_user.id:
        raise HTTPException(403, "forbidden")

    c.content = payload["content"]
    db.commit()

    return {"ok": True}

# ===== 댓글 soft delete =====
@router.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    c = db.query(Comment).filter(Comment.id == comment_id).first()

    if not c or c.deleted_at:
        raise HTTPException(404, "not found")

    if c.user_id != current_user.id:
        raise HTTPException(403, "forbidden")

    c.deleted_at = datetime.utcnow()
    db.commit()

    return {"ok": True}

# ===== 내 댓글 =====
@router.get("/me/comments")
def get_my_comments(
    cursor_created_at: Optional[datetime] = None,
    cursor_id: Optional[int] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = (
        db.query(Comment, Annotation)
        .join(Annotation, Comment.annotation_id == Annotation.id)
        .filter(
            Comment.user_id == current_user.id,
            Comment.deleted_at.is_(None)  # 핵심 추가
        )
    )

    # cursor pagination
    if cursor_created_at and cursor_id:
        query = query.filter(
            (Comment.created_at < cursor_created_at) |
            ((Comment.created_at == cursor_created_at) & (Comment.id < cursor_id))
        )

    query = query.order_by(
        Comment.created_at.desc(),
        Comment.id.desc()
    ).limit(limit + 1)

    rows = query.all()

    items = []
    for c, a in rows[:limit]:
        items.append({
            "id": c.id,
            "content": c.content,
            "created_at": c.created_at,
            "annotation_id": a.id,
            "annotation_page_id": a.page_id,
            "annotation_type": a.type,
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

# ===== 알림 =====
@router.get("/notifications")
def get_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rows = (
        db.query(Notification, User)
        .join(User, Notification.actor_id == User.id)
        .filter(Notification.user_id == current_user.id)
        .order_by(
            Notification.is_read.asc(),   # unread 먼저
            Notification.created_at.desc()
        )
        .limit(20)
        .all()
    )

    result = []
    for n, u in rows:
        result.append({
            "id": n.id,
            "type": n.type,
            "annotation_id": n.annotation_id,
            "comment_id": n.comment_id,
            "is_read": n.is_read,
            "created_at": n.created_at,

            "actor": {
                "id": u.id,
                "name": u.name
            }
        })

    return result

@router.get("/notifications/unread")
def has_unread_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    exists = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).first() is not None

    return {"has_unread": exists}

@router.post("/notifications/{id}/read")
def read_notification(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    n = db.query(Notification).filter(
        Notification.id == id,
        Notification.user_id == current_user.id
    ).first()

    if not n:
        raise HTTPException(404, "not found")

    n.is_read = True
    db.commit()

    return {"ok": True}