from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
import json
from typing import Optional
from datetime import datetime

from db import get_db
from models import Page, Notebook, User, Annotation, Comment
from .auth_router import get_current_user
from .comment_router import can_access_annotation

router = APIRouter(prefix="/api", tags=["pages"])

# ===== Page 생성 =====
@router.post("/pages")
def save_page(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if "result" not in payload:
        raise HTTPException(status_code=400, detail="result is required")

    language = payload.get("language")
    if not language:
        raise HTTPException(status_code=400, detail="language is required")

    name = payload.get("name") or f"My page {int(datetime.utcnow().timestamp())}"
    notebook_id = payload.get("notebook_id")

    page = Page(
        user_id=current_user.id,
        name=name,
        result_json=json.dumps(payload["result"]),
        notebook_id=notebook_id,
        language=language,
        created_at=datetime.utcnow()
    )

    db.add(page)
    db.commit()
    db.refresh(page)

    return {"id": page.id}


# ===== 내 페이지 리스트 =====
@router.get("/pages")
def get_my_pages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    pages = (
        db.query(Page)
        .filter(Page.user_id == current_user.id)
        .order_by(Page.created_at.desc())
        .all()
    )

    return [
        {
            "id": p.id,
            "name": p.name,
            "created_at": p.created_at,
            "notebook_id": p.notebook_id,
            "language": p.language,
        }
        for p in pages
    ]

# ===== Page 삭제 =====
@router.delete("/pages/{page_id}")
def delete_page(
    page_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    page = db.query(Page).filter(Page.id == page_id).first()

    if not page:
        raise HTTPException(status_code=404, detail="page not found")

    if page.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="forbidden")

    db.delete(page)
    db.commit()

    return {"ok": True}

# ===== page 이름 수정 =====
@router.patch("/pages/{page_id}")
def update_page_name(
    page_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    page = db.query(Page).filter(Page.id == page_id).first()

    if not page:
        raise HTTPException(404, "page not found")
    if page.user_id != current_user.id:
        raise HTTPException(403, "forbidden")

    name = payload.get("name")
    if not name:
        raise HTTPException(400, "name required")

    page.name = name
    db.commit()

    return {"ok": True}


# ===== page 이동 =====
@router.post("/pages/move")
def move_pages(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    page_ids = payload.get("page_ids")
    notebook_id = payload.get("notebook_id")

    if not page_ids:
        raise HTTPException(400, "invalid payload")

    # notebook_id가 있을 때만 검증
    if notebook_id is not None:
        notebook = (
            db.query(Notebook)
            .filter(Notebook.id == notebook_id)
            .first()
        )

        if not notebook or notebook.user_id != current_user.id:
            raise HTTPException(403, "invalid notebook")

    pages = db.query(Page).filter(Page.id.in_(page_ids)).all()

    for p in pages:
        if p.user_id != current_user.id:
            raise HTTPException(403, "forbidden")

        # 핵심: None이면 notebook에서 제거
        p.notebook_id = notebook_id if notebook_id is not None else None

    db.commit()

    return {"ok": True}


# ===== 단일 페이지 조회 =====
@router.get("/pages/{page_id}")
def get_page(
    page_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    page = db.query(Page).filter(Page.id == page_id).first()

    if not page:
        raise HTTPException(status_code=404, detail="page not found")

    if page.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="forbidden")

    return {
        "id": page.id,
        "result": json.loads(page.result_json),
        "created_at": page.created_at,
        "notebook_id": page.notebook_id,
        "language": page.language,
    }


# ===== Notebook 생성 =====
@router.post("/notebooks")
def create_notebook(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    name = payload.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    notebook = Notebook(
        user_id=current_user.id,
        name=name,
        created_at=datetime.utcnow()
    )

    db.add(notebook)
    db.commit()
    db.refresh(notebook)

    return {"id": notebook.id, "name": notebook.name}


# ===== 내 Notebook 목록 =====
@router.get("/notebooks")
def get_notebooks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notebooks = (
        db.query(Notebook)
        .filter(Notebook.user_id == current_user.id)
        .order_by(Notebook.created_at.desc())
        .all()
    )

    return [
        {
            "id": n.id,
            "name": n.name,
            "created_at": n.created_at
        }
        for n in notebooks
    ]

# ===== notebook 삭제 -> 내부 page까지 같이 삭제 =====
@router.delete("/notebooks/{notebook_id}")
def delete_notebook(
    notebook_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notebook = db.query(Notebook).filter(Notebook.id == notebook_id).first()
    if not notebook:
        raise HTTPException(404, "notebook not found")

    if notebook.user_id != current_user.id:
        raise HTTPException(403, "forbidden")

    # 내부 페이지 전부 삭제
    db.query(Page).filter(Page.notebook_id == notebook_id).delete()
    db.delete(notebook)
    db.commit()

    return {"ok": True}

# ===== notebook 이름 수정 =====
@router.patch("/notebooks/{notebook_id}")
def update_notebook(
    notebook_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notebook = db.query(Notebook).filter(Notebook.id == notebook_id).first()

    if not notebook:
        raise HTTPException(404, "notebook not found")
    if notebook.user_id != current_user.id:
        raise HTTPException(403, "forbidden")

    name = payload.get("name")
    if not name:
        raise HTTPException(400, "name required")

    notebook.name = name
    db.commit()

    return {"ok": True}


# ===== notebook 내부 페이지 리스트 =====
@router.get("/notebooks/{notebook_id}/pages")
def get_pages_in_notebook(
    notebook_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notebook = db.query(Notebook).filter(Notebook.id == notebook_id).first()

    if not notebook:
        raise HTTPException(404, "notebook not found")
    if notebook.user_id != current_user.id:
        raise HTTPException(403, "forbidden")

    pages = (
        db.query(Page)
        .filter(
            Page.user_id == current_user.id,
            Page.notebook_id == notebook_id
        )
        .order_by(Page.created_at.desc())
        .all()
    )

    return {
        "notebook": {
            "id": notebook.id,
            "name": notebook.name
        },
        "pages": [
            {
                "id": p.id,
                "name": p.name,
                "created_at": p.created_at,
                "language": p.language,
            }
            for p in pages
        ]
    }


# ====== annotation 생성 ======
@router.post("/annotations")
def create_annotation(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ann = Annotation(
        user_id=current_user.id,
        page_id=payload["page_id"],
        type=payload["type"],
        content=payload["content"],
        start_index=payload["start_index"],
        end_index=payload["end_index"],
        created_at=datetime.utcnow()
    )

    db.add(ann)
    db.commit()
    db.refresh(ann)

    return ann


# ====== 단일 페이지 내 주석 리스트 ======
@router.get("/pages/{page_id}/annotations")
def get_annotations(
    page_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    anns = (
        db.query(Annotation)
        .filter(
            Annotation.page_id == page_id,
            Annotation.user_id == current_user.id
        )
        .all()
    )

    return anns


# ====== 주석 삭제 ======
@router.delete("/annotations/{annotation_id}")
def delete_annotation(
    annotation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ann = db.query(Annotation).filter(
        Annotation.id == annotation_id,
        Annotation.user_id == current_user.id
    ).first()

    if not ann:
        raise HTTPException(status_code=404, detail="Annotation not found")

    db.delete(ann)
    db.commit()

    return {"ok": True}


# ====== 주석 수정 ======
@router.patch("/annotations/{annotation_id}")
def update_annotation(
    annotation_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ann = db.query(Annotation).filter(
        Annotation.id == annotation_id,
        Annotation.user_id == current_user.id
    ).first()

    if not ann:
        raise HTTPException(status_code=404, detail="Annotation not found")

    ann.content = payload["content"]

    db.commit()
    db.refresh(ann)

    return ann


# ====== 유저 주석 리스트 ======
@router.get("/annotations")
def get_annotations_all(
    cursor_created_at: Optional[datetime] = None,
    cursor_id: Optional[int] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
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
        db.query(Annotation, Page, comment_counts.c.count)
        .join(Page, Annotation.page_id == Page.id)
        .outerjoin(
            comment_counts,
            Annotation.id == comment_counts.c.annotation_id
        )
        .filter(Annotation.user_id == current_user.id)
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
    for ann, page, count in rows[:limit]:
        result = json.loads(page.result_json)
        text = result["text"]

        tokens = text.split()
        source = " ".join(tokens[ann.start_index:ann.end_index+1])

        items.append({
            "id": ann.id,
            "type": ann.type,
            "content": ann.content,
            "page_id": page.id,
            "page_name": page.name,
            "source": source,
            "created_at": ann.created_at,
            "comment_count": count or 0,
            "user": {
                "id": current_user.id,
                "name": current_user.name,
                "email": current_user.email,
            }
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


# ====== 단일 주석 조회 ======
from models import Annotation, Comment, User

@router.get("/annotations/{annotation_id}")
def get_annotation(
    annotation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    row = (
        db.query(Annotation, User, Page)
        .join(User, Annotation.user_id == User.id)
        .join(Page, Annotation.page_id == Page.id)
        .filter(Annotation.id == annotation_id)
        .first()
    )

    if not row:
        raise HTTPException(404, "not found")

    a, u, p = row

    if not can_access_annotation(db, current_user.id, a):
        raise HTTPException(403, "forbidden")

    count = db.query(Comment).filter(
        Comment.annotation_id == annotation_id,
        Comment.deleted_at.is_(None)
    ).count()

    result = json.loads(p.result_json)
    text = result["text"]
    tokens = text.split()

    source = " ".join(tokens[a.start_index:a.end_index + 1])

    return {
        "id": a.id,
        "type": a.type,
        "content": a.content,
        "page_id": a.page_id,
        "page_name": p.name,
        "source": source,
        "created_at": a.created_at,
        "comment_count": count,
        "user": {
            "id": u.id,
            "name": u.name,
            "email": u.email,
        },
    }