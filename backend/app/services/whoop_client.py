"""Whoop API v2 HTTP client with OAuth 2.0 token management."""

from __future__ import annotations

import datetime
import logging
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.whoop_token import WhoopToken

logger = logging.getLogger(__name__)

WHOOP_BASE = "https://api.prod.whoop.com"
WHOOP_AUTH_URL = f"{WHOOP_BASE}/oauth/oauth2/auth"
WHOOP_TOKEN_URL = f"{WHOOP_BASE}/oauth/oauth2/token"
WHOOP_API_BASE = f"{WHOOP_BASE}/developer/v1"

_TOKEN_REFRESH_BUFFER = datetime.timedelta(seconds=60)


def build_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.WHOOP_CLIENT_ID,
        "redirect_uri": settings.WHOOP_REDIRECT_URI,
        "response_type": "code",
        "scope": settings.WHOOP_SCOPES,
        "state": state,
    }
    return f"{WHOOP_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.WHOOP_CLIENT_ID,
        "client_secret": settings.WHOOP_CLIENT_SECRET,
        "redirect_uri": settings.WHOOP_REDIRECT_URI,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(WHOOP_TOKEN_URL, data=payload)
        resp.raise_for_status()
        return resp.json()


async def _refresh_access_token(refresh_token: str) -> dict:
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.WHOOP_CLIENT_ID,
        "client_secret": settings.WHOOP_CLIENT_SECRET,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(WHOOP_TOKEN_URL, data=payload)
        resp.raise_for_status()
        return resp.json()


async def save_tokens(db: AsyncSession, token_data: dict) -> WhoopToken:
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=token_data.get("expires_in", 3600)
    )
    existing = (
        await db.execute(select(WhoopToken).where(WhoopToken.id == 1))
    ).scalar_one_or_none()

    if existing is None:
        tok = WhoopToken(
            id=1,
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_at=expires_at,
            scopes=token_data.get("scope", settings.WHOOP_SCOPES),
        )
        db.add(tok)
    else:
        existing.access_token = token_data["access_token"]
        existing.refresh_token = token_data["refresh_token"]
        existing.expires_at = expires_at
        if "scope" in token_data:
            existing.scopes = token_data["scope"]
        tok = existing

    await db.commit()
    await db.refresh(tok)
    return tok


async def get_valid_token(db: AsyncSession) -> WhoopToken | None:
    """Return the stored token, refreshing if expired. Returns None if disconnected."""
    tok = (
        await db.execute(select(WhoopToken).where(WhoopToken.id == 1))
    ).scalar_one_or_none()

    if tok is None:
        return None

    now = datetime.datetime.now(datetime.timezone.utc)
    expires = tok.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=datetime.timezone.utc)

    if now + _TOKEN_REFRESH_BUFFER >= expires:
        logger.info("Whoop access token expired or expiring soon, refreshing")
        try:
            new_data = await _refresh_access_token(tok.refresh_token)
            tok = await save_tokens(db, new_data)
        except httpx.HTTPStatusError as exc:
            logger.error("Token refresh failed: %s", exc)
            return None

    return tok


async def whoop_api_get(
    db: AsyncSession,
    path: str,
    params: dict | None = None,
) -> dict:
    tok = await get_valid_token(db)
    if tok is None:
        raise RuntimeError("Whoop not connected — no valid token")

    async with httpx.AsyncClient(base_url=WHOOP_API_BASE) as client:
        resp = await client.get(
            path,
            params=params or {},
            headers={"Authorization": f"Bearer {tok.access_token}"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_collection(
    db: AsyncSession,
    path: str,
    start: str,
    end: str,
    limit: int = 25,
) -> list[dict]:
    """Fetch all pages of a paginated Whoop v2 collection endpoint."""
    all_records: list[dict] = []
    params: dict = {"start": start, "end": end, "limit": limit}

    while True:
        data = await whoop_api_get(db, path, params)
        records = data.get("records", [])
        all_records.extend(records)

        next_token = data.get("next_token")
        if not next_token or not records:
            break
        params["nextToken"] = next_token

    return all_records


async def fetch_user_profile(db: AsyncSession) -> dict:
    return await whoop_api_get(db, "/v2/user/profile/basic")
