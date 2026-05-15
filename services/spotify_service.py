import base64
import json
import os
import re
import logging
from datetime import datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import SpotifyConnection

SPOTIFY_ACCOUNTS_BASE = "https://accounts.spotify.com"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"
LRCLIB_API_BASE = os.getenv("LRCLIB_API_BASE", "https://lrclib.net/api").rstrip("/")
SPOTIFY_TIMEOUT_SECONDS = float(os.getenv("SPOTIFY_TIMEOUT_SECONDS", "10"))

logger = logging.getLogger(__name__)

def utcnow() -> datetime:
    return datetime.utcnow()


def _json_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = SPOTIFY_TIMEOUT_SECONDS,
) -> tuple[int, Any]:
    req = Request(url, data=data, method=method)

    for key, value in (headers or {}).items():
        req.add_header(key, value)

    try:
        with urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            payload = response.read()
            if not payload:
                return status, None
            return status, json.loads(payload.decode("utf-8"))
    except HTTPError as exc:
        payload = exc.read()
        try:
            parsed = json.loads(payload.decode("utf-8")) if payload else None
        except Exception:
            parsed = payload.decode("utf-8", errors="ignore") if payload else None
        return exc.code, parsed
    except URLError as exc:
        raise HTTPException(status_code=502, detail=f"spotify network error: {exc.reason}") from exc


def build_authorize_url(*, client_id: str, redirect_uri: str, scope: str, state: str) -> str:
    query = urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "show_dialog": "true",
    })
    return f"{SPOTIFY_ACCOUNTS_BASE}/authorize?{query}"


def exchange_code_for_token(*, client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict[str, Any]:
    body = urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }).encode("utf-8")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")

    status, payload = _json_request(
        f"{SPOTIFY_ACCOUNTS_BASE}/api/token",
        method="POST",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=body,
    )

    if status >= 400 or not isinstance(payload, dict):
        logger.error("spotify token exchange failed: status=%s payload=%s", status, payload)
        raise HTTPException(status_code=502, detail="spotify token exchange failed")

    return payload


def refresh_access_token(connection: SpotifyConnection, *, client_id: str, client_secret: str, db: Session) -> SpotifyConnection:
    if not connection.refresh_token:
        raise HTTPException(status_code=401, detail="spotify refresh token missing")

    body = urlencode({
        "grant_type": "refresh_token",
        "refresh_token": connection.refresh_token,
    }).encode("utf-8")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")

    status, payload = _json_request(
        f"{SPOTIFY_ACCOUNTS_BASE}/api/token",
        method="POST",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=body,
    )

    if status >= 400 or not isinstance(payload, dict):
        raise HTTPException(status_code=401, detail="spotify token refresh failed")

    connection.access_token = payload["access_token"]
    connection.refresh_token = payload.get("refresh_token") or connection.refresh_token
    connection.scope = payload.get("scope") or connection.scope
    connection.expires_at = utcnow() + timedelta(seconds=int(payload.get("expires_in", 3600)))
    connection.updated_at = utcnow()

    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


def get_spotify_profile(access_token: str) -> dict[str, Any]:
    status, payload = _json_request(
        f"{SPOTIFY_API_BASE}/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    if status >= 400 or not isinstance(payload, dict):
        logger.error("spotify profile fetch failed: status=%s payload=%s", status, payload)
        raise HTTPException(status_code=502, detail="spotify profile fetch failed")

    return payload


def ensure_valid_connection(
    connection: SpotifyConnection | None,
    *,
    client_id: str,
    client_secret: str,
    db: Session,
) -> SpotifyConnection:
    if not connection:
        raise HTTPException(status_code=404, detail="spotify not connected")

    if connection.expires_at <= utcnow() + timedelta(seconds=30):
        return refresh_access_token(connection, client_id=client_id, client_secret=client_secret, db=db)

    return connection


def spotify_get(url: str, access_token: str) -> tuple[int, Any]:
    return _json_request(url, headers={"Authorization": f"Bearer {access_token}"})


def fetch_playback_snapshot(access_token: str) -> tuple[dict[str, Any] | None, str]:
    endpoints = [
        (f"{SPOTIFY_API_BASE}/me/player?additional_types=track", "playback-state"),
        (f"{SPOTIFY_API_BASE}/me/player/currently-playing?additional_types=track", "currently-playing"),
    ]

    for url, source in endpoints:
        status, payload = spotify_get(url, access_token)

        if status == 204:
            continue

        if status in (401, 403):
            raise HTTPException(status_code=status, detail="spotify access denied")

        if status >= 400:
            continue

        if isinstance(payload, dict):
            return payload, source

    return None, "none"


def _pick_image(track: dict[str, Any]) -> str | None:
    album = track.get("album") or {}
    images = album.get("images") or []
    if not images:
        return None
    return images[0].get("url")


def _clean_title(title: str) -> str:
    cleaned = re.sub(r"\s*[\(\[][^)\]]*(remaster|live|mono|stereo|version|edit|feat\.?|featuring)[^)\]]*[\)\]]", "", title, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*-\s*(remaster(ed)?|live|mono|stereo|radio edit|edit|version)\b.*$", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def build_lyrics_queries(track_name: str, artists: list[str], album_name: str | None) -> dict[str, Any]:
    primary_artist = artists[0] if artists else ""
    cleaned_title = _clean_title(track_name)
    primary = f"{primary_artist} - {cleaned_title}".strip(" -")

    fallbacks: list[str] = []
    if track_name and primary_artist:
        fallbacks.append(f"{primary_artist} - {track_name}")
    if cleaned_title and len(artists) > 1:
        fallbacks.append(f"{', '.join(artists[:2])} - {cleaned_title}")
    if cleaned_title and album_name:
        fallbacks.append(f"{primary_artist} - {cleaned_title} ({album_name})")
    if cleaned_title:
        fallbacks.append(cleaned_title)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in [primary, *fallbacks]:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(key)

    return {
        "primary": deduped[0] if deduped else None,
        "fallbacks": deduped[1:],
    }


def _lyrics_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    plain = payload.get("plainLyrics") or payload.get("plain_lyrics")
    synced = payload.get("syncedLyrics") or payload.get("synced_lyrics")
    if not plain and not synced:
        return None

    return {
        "provider": "lrclib",
        "is_synced": bool(synced),
        "plain": plain,
        "synced": synced,
        "language": payload.get("lang"),
    }


def fetch_lyrics(track_name: str, artists: list[str], album_name: str | None, duration_ms: int | None) -> dict[str, Any] | None:
    if not track_name or not artists:
        return None

    primary_artist = artists[0]
    candidate_params = [
        {
            "track_name": _clean_title(track_name),
            "artist_name": primary_artist,
            "album_name": album_name or "",
            "duration": duration_ms or "",
        },
        {
            "track_name": track_name,
            "artist_name": primary_artist,
        },
        {
            "track_name": _clean_title(track_name),
            "artist_name": primary_artist,
        },
    ]

    for params in candidate_params:
        encoded = urlencode({k: v for k, v in params.items() if v not in (None, "")})
        status, payload = _json_request(f"{LRCLIB_API_BASE}/get?{encoded}")
        if status < 400 and isinstance(payload, dict):
            lyrics = _lyrics_from_payload(payload)
            if lyrics:
                return lyrics

    search_query = f"{primary_artist} {_clean_title(track_name)}".strip()
    status, payload = _json_request(f"{LRCLIB_API_BASE}/search?{urlencode({'query': search_query})}")
    if status < 400 and isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            lyrics = _lyrics_from_payload(item)
            if lyrics:
                return lyrics

    return None


def normalize_current_track(payload: dict[str, Any] | None, source: str) -> dict[str, Any]:
    item = (payload or {}).get("item") if payload else None
    device = (payload or {}).get("device") if payload else None

    if not isinstance(item, dict):
        return {
            "source": source,
            "is_playing": bool((payload or {}).get("is_playing")),
            "progress_ms": (payload or {}).get("progress_ms"),
            "duration_ms": None,
            "timestamp": (payload or {}).get("timestamp"),
            "track": None,
            "device": {
                "name": device.get("name"),
                "type": device.get("type"),
            } if isinstance(device, dict) else None,
            "source_query": {
                "primary": None,
                "fallbacks": [],
            },
            "lyrics": None,
        }

    artists = [artist.get("name") for artist in item.get("artists", []) if artist.get("name")]
    album = item.get("album") or {}
    duration_ms = item.get("duration_ms")
    lyrics_queries = build_lyrics_queries(item.get("name") or "", artists, album.get("name"))

    return {
        "source": source,
        "is_playing": bool((payload or {}).get("is_playing")),
        "progress_ms": (payload or {}).get("progress_ms"),
        "duration_ms": duration_ms,
        "timestamp": (payload or {}).get("timestamp"),
        "track": {
            "id": item.get("id"),
            "uri": item.get("uri"),
            "name": item.get("name"),
            "artists": artists,
            "album": album.get("name"),
            "image_url": _pick_image(item),
            "external_url": (item.get("external_urls") or {}).get("spotify"),
            "isrc": (item.get("external_ids") or {}).get("isrc"),
        },
        "device": {
            "name": device.get("name"),
            "type": device.get("type"),
        } if isinstance(device, dict) else None,
        "source_query": lyrics_queries,
        "lyrics": fetch_lyrics(
            track_name=item.get("name") or "",
            artists=artists,
            album_name=album.get("name"),
            duration_ms=duration_ms,
        ),
    }

