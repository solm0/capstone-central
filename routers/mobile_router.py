import json
import logging
import time
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from language_config import get_nlp
from language_config.sr import cyr_to_lat
from models import User, UserLemma
from routers.auth_router import get_current_user_optional
from services.ipa_service import attach_token_ipa, describe_token_articulation
from services import lemma_service
from services.nlp_service import align_tokens
from services.prediction_service import predict_next, search_prefix, tokenize

router = APIRouter(prefix="/api/mobile", tags=["mobile"])
logger = logging.getLogger(__name__)


class Block(BaseModel):
    text: str


class AnalyzeRequest(BaseModel):
    blocks: list[Block]
    language: str


class LookupRequest(BaseModel):
    lemma: str
    pos: str
    language: str


class BatchLookupRequest(BaseModel):
    items: list[dict]
    language: str


class IpaRequest(BaseModel):
    blocks: list[dict]
    language: str


class ArticulationRequest(BaseModel):
    tokens: list[dict]
    language: str


def normalize_sr(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return cyr_to_lat(text)


def to_local_key(lemma: str, pos: str) -> str:
    return f"{lemma}_{pos}"


def to_global_key(lemma: str, pos: str, lang: str) -> str:
    return f"{lemma}/{pos}/{lang}"


def fetch_favorites(
    db: Session,
    user: User | None,
    lemma_keys: list[str],
) -> set[str]:
    if not user or not lemma_keys:
        return set()

    rows = db.query(UserLemma.lemma_key).filter(
        UserLemma.user_id == user.id,
        UserLemma.lemma_key.in_(lemma_keys),
    ).all()

    return {row[0] for row in rows}


@router.get("/predict")
def predict(
    language: str,
    text: str | None = None,
    context: str | None = Query(default=None),
):
    tokens = None

    if context is not None:
        try:
            parsed = json.loads(context)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid context") from exc

        if not isinstance(parsed, list) or not all(isinstance(token, str) for token in parsed):
            raise HTTPException(status_code=400, detail="invalid context")

        tokens = parsed
    elif text is not None:
        tokens = tokenize(text, language)
    else:
        raise HTTPException(status_code=422, detail="text or context is required")

    return {
        "input": text,
        "context": tokens,
        "tokens": tokens,
        "predictions": predict_next(tokens, language),
    }


@router.get("/search")
def search(q: str, language: str):
    return {
        "query": q,
        "predictions": search_prefix(q, language),
    }


@router.post("/analyze")
def analyze(req: AnalyzeRequest):
    started_at = time.perf_counter()
    logger.info(
        "[mobile.analyze] start language=%s blocks=%s",
        req.language,
        len(req.blocks),
    )

    try:
        print("[mobile.analyze] entered", flush=True)
        nlp = get_nlp(req.language)
        logger.info(
            "[mobile.analyze] pipeline ready language=%s elapsed=%.2fs",
            req.language,
            time.perf_counter() - started_at,
        )
    except Exception:
        logger.exception(
            "[mobile.analyze] pipeline init failed language=%s",
            req.language,
        )
        raise

    out_blocks = []

    for index, block in enumerate(req.blocks):
        text = block.text.strip()

        if not text:
            out_blocks.append({
                "text": block.text,
                "tokens": [],
            })
            continue

        if req.language == "sr":
            text = normalize_sr(text)

        block_started_at = time.perf_counter()

        try:
            logger.info(
                "[mobile.analyze] block=%s chars=%s running_nlp",
                index,
                len(text),
            )
            print("[mobile.analyze] pipeline ready", flush=True)
            doc = nlp(text)
            logger.info(
                "[mobile.analyze] block=%s nlp_done elapsed=%.2fs",
                index,
                time.perf_counter() - block_started_at,
            )
            print("[mobile.analyze] nlp(text) done", flush=True)
        except Exception:
            logger.exception(
                "[mobile.analyze] block=%s nlp failed chars=%s",
                index,
                len(text),
            )
            raise

        tokens_all = []
        for sent in doc.sentences:
            tokens_all.extend(align_tokens(sent))

        out_blocks.append({
            "text": block.text,
            "tokens": tokens_all or [],
        })

    logger.info(
        "[mobile.analyze] done language=%s blocks=%s elapsed=%.2fs",
        req.language,
        len(out_blocks),
        time.perf_counter() - started_at,
    )
    return {"blocks": out_blocks}


@router.post("/lookup")
def lookup(
    req: LookupRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    global_key = to_global_key(req.lemma, req.pos, req.language)
    local_key = to_local_key(req.lemma, req.pos)

    liked_set = fetch_favorites(db, user, [global_key])
    is_favorite = global_key in liked_set

    if not lemma_service.has_key(local_key, req.language):
        return {
            "key": local_key,
            "global_key": global_key,
            "related": [],
            "kwic": [],
            "is_favorite": is_favorite,
        }

    related = lemma_service.get_related(local_key, req.language)
    line_ids = lemma_service.get_line_ids(local_key, req.language)

    kwic = lemma_service.sample_kwic(
        line_ids,
        req.lemma,
        req.pos,
        req.language,
        max_k=20,
    )

    return {
        "key": local_key,
        "global_key": global_key,
        "related": related,
        "kwic": kwic,
        "is_favorite": is_favorite,
    }


@router.post("/lookup_batch")
def lookup_batch(
    req: BatchLookupRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    lang = req.language
    result = {}

    global_keys = [
        to_global_key(item["lemma"], item["pos"], lang)
        for item in req.items
    ]
    liked_set = fetch_favorites(db, user, global_keys)

    for item in req.items:
        lemma = item["lemma"]
        pos = item["pos"]

        local_key = to_local_key(lemma, pos)
        global_key = to_global_key(lemma, pos, lang)

        if not lemma_service.has_key(local_key, lang):
            continue

        result[local_key] = {
            "key": local_key,
            "global_key": global_key,
            "related": lemma_service.get_related(local_key, lang),
            "kwic": lemma_service.sample_kwic(
                lemma_service.get_line_ids(local_key, lang),
                lemma,
                pos,
                lang,
                max_k=10,
            ),
            "is_favorite": global_key in liked_set,
        }

    return result


@router.post("/ipa")
def enrich_ipa(req: IpaRequest):
    return {
        "blocks": attach_token_ipa(req.blocks, req.language),
    }


@router.post("/articulation")
def articulation(req: ArticulationRequest):
    items: list[dict] = []

    for token_index, token in enumerate(req.tokens):
        token_surface = token.get("surface", "")
        token_ipa = token.get("ipa")

        for segment_index, detail in enumerate(
            describe_token_articulation(token_surface, token_ipa)
        ):
            items.append({
                **detail,
                "token_index": token_index,
                "segment_index": segment_index,
            })

    return {
        "items": items,
    }


@router.post("/ocr")
def ocr_not_supported():
    raise HTTPException(status_code=501, detail="OCR is not supported on mobile")
