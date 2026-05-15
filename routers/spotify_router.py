import os
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from db import get_db
from models import SpotifyConnection, User
from routers.auth_router import ALGORITHM, SECRET_KEY, WEB_APP_URL, get_current_user
from services.spotify_service import (
    build_authorize_url,
    ensure_valid_connection,
    exchange_code_for_token,
    fetch_playback_snapshot,
    get_spotify_profile,
    normalize_current_track,
    refresh_access_token,
    utcnow,
)

router = APIRouter(prefix="/api/integrations/spotify", tags=["spotify"])

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
SPOTIFY_SCOPES = os.getenv(
    "SPOTIFY_SCOPES",
    "user-read-currently-playing user-read-playback-state",
)
SPOTIFY_SUCCESS_REDIRECT = os.getenv(
    "SPOTIFY_SUCCESS_REDIRECT",
    f"{WEB_APP_URL}/settings?spotify=connected",
)
SPOTIFY_ERROR_REDIRECT = os.getenv(
    "SPOTIFY_ERROR_REDIRECT",
    f"{WEB_APP_URL}/settings?spotify=error",
)
SPOTIFY_STATE_TTL_SECONDS = int(os.getenv("SPOTIFY_STATE_TTL_SECONDS", "600"))


def require_spotify_config() -> None:
    if not SECRET_KEY:
        raise HTTPException(status_code=500, detail="SECRET_KEY is not configured")
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET or not SPOTIFY_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="spotify env is not configured")


def issue_state_token(user: User, redirect_to: str | None) -> str:
    payload = {
        "user_id": user.id,
        "redirect_to": redirect_to,
        "exp": datetime.utcnow() + timedelta(seconds=SPOTIFY_STATE_TTL_SECONDS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_state_token(state: str) -> dict:
    try:
        return jwt.decode(state, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=400, detail="invalid spotify state") from exc


def with_query_params(url: str, **params: str) -> str:
    parsed = urlparse(url)
    current = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current.update({key: value for key, value in params.items() if value is not None})
    return urlunparse(parsed._replace(query=urlencode(current)))


@router.get("/connect-url")
def get_connect_url(
    redirect_to: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
):
    require_spotify_config()
    state = issue_state_token(current_user, redirect_to)
    url = build_authorize_url(
        client_id=SPOTIFY_CLIENT_ID,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=SPOTIFY_SCOPES,
        state=state,
    )
    return {
        "url": url,
        "scopes": SPOTIFY_SCOPES.split(),
        "redirect_uri": SPOTIFY_REDIRECT_URI,
    }


@router.get("/callback")
def spotify_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    require_spotify_config()

    if error:
        return RedirectResponse(with_query_params(SPOTIFY_ERROR_REDIRECT, error=error))

    if not code or not state:
        raise HTTPException(status_code=400, detail="missing spotify callback parameters")

    state_payload = decode_state_token(state)
    user = db.query(User).filter(User.id == state_payload["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    token_payload = exchange_code_for_token(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        code=code,
        redirect_uri=SPOTIFY_REDIRECT_URI,
    )
    profile = get_spotify_profile(token_payload["access_token"])

    connection = db.query(SpotifyConnection).filter(SpotifyConnection.user_id == user.id).first()
    if not connection:
        connection = SpotifyConnection(user_id=user.id)

    connection.provider_user_id = profile.get("id")
    connection.access_token = token_payload["access_token"]
    connection.refresh_token = token_payload.get("refresh_token") or connection.refresh_token
    connection.expires_at = utcnow() + timedelta(seconds=int(token_payload.get("expires_in", 3600)))
    connection.scope = token_payload.get("scope") or SPOTIFY_SCOPES
    connection.updated_at = utcnow()
    if not connection.created_at:
        connection.created_at = utcnow()

    db.add(connection)
    db.commit()

    redirect_to = state_payload.get("redirect_to") or SPOTIFY_SUCCESS_REDIRECT
    return RedirectResponse(with_query_params(redirect_to, spotify="connected"))


@router.get("/status")
def spotify_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = db.query(SpotifyConnection).filter(SpotifyConnection.user_id == current_user.id).first()
    if not connection:
        return {
            "connected": False,
            "provider": "spotify",
        }

    return {
        "connected": True,
        "provider": "spotify",
        "provider_user_id": connection.provider_user_id,
        "scope": connection.scope.split() if connection.scope else [],
        "expires_at": connection.expires_at.isoformat(),
        "has_refresh_token": bool(connection.refresh_token),
    }


@router.post("/disconnect")
def spotify_disconnect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = db.query(SpotifyConnection).filter(SpotifyConnection.user_id == current_user.id).first()
    if connection:
        db.delete(connection)
        db.commit()

    return {"connected": False, "provider": "spotify"}


@router.get("/current-track")
def spotify_current_track(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_spotify_config()
    connection = db.query(SpotifyConnection).filter(SpotifyConnection.user_id == current_user.id).first()
    connection = ensure_valid_connection(
        connection,
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        db=db,
    )

    try:
        payload, source = fetch_playback_snapshot(connection.access_token)
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
        connection = refresh_access_token(
            connection,
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            db=db,
        )
        payload, source = fetch_playback_snapshot(connection.access_token)

    normalized = normalize_current_track(payload, source)

    return {
        "connected": True,
        **normalized,
    }
