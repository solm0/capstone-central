from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from models import DailyReadingRecommendation, ReadingPreference, User
from routers.auth_router import get_current_user
from services.reading_recommendation_service import (
    category_payload,
    dumps_json_list,
    generate_recommendation,
    loads_json_list,
    normalize_preference_categories,
    normalize_preference_languages,
    supported_language_payload,
)


router = APIRouter(prefix="/api/reading", tags=["reading"])


class ReadingPreferencePayload(BaseModel):
    enabled: bool = True
    languages: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)


class ReadingRecommendationRequest(BaseModel):
    available_languages: list[str] = Field(default_factory=list)
    refresh: bool = False
    preferred_languages: list[str] = Field(default_factory=list)
    preferred_categories: list[str] = Field(default_factory=list)


def serialize_preference(preference: ReadingPreference | None):
    return {
        "enabled": preference.enabled if preference else False,
        "languages": normalize_preference_languages(
            loads_json_list(preference.languages_json) if preference else []
        ),
        "categories": normalize_preference_categories(
            loads_json_list(preference.categories_json) if preference else []
        ),
        "supported_languages": supported_language_payload(),
        "available_categories": category_payload(),
        "updated_at": preference.updated_at.isoformat() if preference and preference.updated_at else None,
    }


def serialize_recommendation(recommendation: DailyReadingRecommendation):
    return {
        "id": recommendation.id,
        "language": recommendation.language,
        "category_key": recommendation.category_key,
        "title": recommendation.title,
        "author": recommendation.author,
        "summary": recommendation.summary,
        "excerpt": recommendation.excerpt,
        "source_url": recommendation.source_url,
        "gutenberg_id": recommendation.gutenberg_id,
        "recommendation_date": recommendation.recommendation_date.isoformat(),
    }


def recommendation_matches_context(
    recommendation: DailyReadingRecommendation,
    preferred_languages: list[str],
    selected_categories: list[str],
    available_languages: list[str],
) -> bool:
    if recommendation.language not in available_languages:
        return False

    if recommendation.language not in preferred_languages:
        return False

    if selected_categories and recommendation.category_key:
        return recommendation.category_key in selected_categories

    return True


def build_or_update_recommendation(
    db: Session,
    user: User,
    available_languages: list[str],
    refresh: bool,
    preferred_languages_override: list[str] | None = None,
    preferred_categories_override: list[str] | None = None,
) -> DailyReadingRecommendation:
    preference = (
        db.query(ReadingPreference)
        .filter(ReadingPreference.user_id == user.id)
        .first()
    )

    preferred_languages = normalize_preference_languages(
        preferred_languages_override
        if preferred_languages_override
        else loads_json_list(preference.languages_json) if preference else []
    )
    selected_categories = normalize_preference_categories(
        preferred_categories_override
        if preferred_categories_override
        else loads_json_list(preference.categories_json) if preference else []
    )
    normalized_available = normalize_preference_languages(available_languages)

    if preference and not preference.enabled and not preferred_languages_override and not preferred_categories_override:
        raise HTTPException(status_code=404, detail="reading preferences not configured")

    if not preferred_languages:
        raise HTTPException(status_code=400, detail="reading preference languages are empty")

    if not selected_categories:
        raise HTTPException(status_code=400, detail="reading preference categories are empty")

    today = date.today()
    recommendation = (
        db.query(DailyReadingRecommendation)
        .filter(
            DailyReadingRecommendation.user_id == user.id,
            DailyReadingRecommendation.recommendation_date == today,
        )
        .first()
    )

    if (
        recommendation
        and not refresh
        and recommendation_matches_context(
            recommendation,
            preferred_languages,
            selected_categories,
            normalized_available,
        )
    ):
        return recommendation

    recent_cutoff = today - timedelta(days=14)
    recent_book_ids = {
        row.gutenberg_id
        for row in db.query(DailyReadingRecommendation)
        .filter(
            DailyReadingRecommendation.user_id == user.id,
            DailyReadingRecommendation.recommendation_date >= recent_cutoff,
        )
        .all()
    }

    if recommendation:
        recent_book_ids.add(recommendation.gutenberg_id)

    try:
        candidate = generate_recommendation(
            preferred_languages=preferred_languages,
            selected_categories=selected_categories,
            available_languages=normalized_available,
            excluded_book_ids=recent_book_ids,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=504,
            detail="Recommendation lookup timed out. Please try again.",
        ) from error

    if not recommendation:
        recommendation = DailyReadingRecommendation(
            user_id=user.id,
            recommendation_date=today,
        )
        db.add(recommendation)

    recommendation.language = candidate.language
    recommendation.category_key = candidate.category_key
    recommendation.gutenberg_id = candidate.gutenberg_id
    recommendation.title = candidate.title
    recommendation.author = candidate.author
    recommendation.summary = candidate.summary
    recommendation.excerpt = candidate.excerpt
    recommendation.source_url = candidate.source_url
    recommendation.created_at = datetime.utcnow()

    db.commit()
    db.refresh(recommendation)

    return recommendation


@router.get("/preferences")
def get_reading_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    preference = (
        db.query(ReadingPreference)
        .filter(ReadingPreference.user_id == current_user.id)
        .first()
    )

    return serialize_preference(preference)


@router.put("/preferences")
def save_reading_preferences(
    payload: ReadingPreferencePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    languages = normalize_preference_languages(payload.languages)
    categories = normalize_preference_categories(payload.categories)

    if payload.enabled and (not languages or not categories):
        raise HTTPException(
            status_code=400,
            detail="enabled reading preferences require at least one language and one category",
        )

    preference = (
        db.query(ReadingPreference)
        .filter(ReadingPreference.user_id == current_user.id)
        .first()
    )

    if not preference:
        preference = ReadingPreference(user_id=current_user.id)
        db.add(preference)

    preference.enabled = payload.enabled
    preference.languages_json = dumps_json_list(languages)
    preference.categories_json = dumps_json_list(categories)
    preference.updated_at = datetime.utcnow()

    if preference.created_at is None:
        preference.created_at = datetime.utcnow()

    db.commit()
    db.refresh(preference)

    return serialize_preference(preference)


@router.post("/recommendation")
def get_daily_recommendation(
    payload: ReadingRecommendationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    recommendation = build_or_update_recommendation(
        db=db,
        user=current_user,
        available_languages=payload.available_languages,
        refresh=payload.refresh,
        preferred_languages_override=payload.preferred_languages,
        preferred_categories_override=payload.preferred_categories,
    )
    return serialize_recommendation(recommendation)
