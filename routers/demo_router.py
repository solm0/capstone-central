import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/demo", tags=["demo"])

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"


@lru_cache(maxsize=8)
def load_demo(name: str):
    demo_path = DEMO_DIR / f"{name}.json"

    if not demo_path.exists():
        raise FileNotFoundError(name)

    with demo_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@router.get("/landing/{name}")
def get_landing_demo(name: str):
    try:
        return load_demo(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="demo not found") from exc
