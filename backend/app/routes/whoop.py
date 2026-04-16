"""Whoop OAuth 2.0 and data-sync API routes."""

from __future__ import annotations

import logging
import secrets
import time

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.whoop_token import WhoopToken
from app.services.whoop_client import (
    build_authorize_url,
    exchange_code_for_tokens,
    save_tokens,
)
from app.services.whoop_sync import sync_whoop_data

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whoop", tags=["whoop"])

# In-memory state store for CSRF protection (TTL = 10 minutes)
_pending_states: dict[str, float] = {}
_STATE_TTL = 600


def _prune_expired_states() -> None:
    now = time.time()
    expired = [k for k, v in _pending_states.items() if now - v > _STATE_TTL]
    for k in expired:
        del _pending_states[k]


@router.get("/authorize")
async def authorize():
    """Redirect the user to the Whoop OAuth consent screen."""
    _prune_expired_states()
    state = secrets.token_hex(16)
    _pending_states[state] = time.time()
    url = build_authorize_url(state)
    return RedirectResponse(url, status_code=302)


@router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Exchange the authorization code for tokens and persist them."""
    _prune_expired_states()

    if state not in _pending_states:
        return JSONResponse(
            {"error": "Invalid or expired state parameter"},
            status_code=400,
        )
    del _pending_states[state]

    try:
        token_data = await exchange_code_for_tokens(code)
    except Exception as exc:
        logger.error("Token exchange failed: %s", exc)
        return JSONResponse(
            {"error": f"Token exchange failed: {exc}"},
            status_code=502,
        )

    await save_tokens(db, token_data)
    return {
        "status": "connected",
        "message": "Whoop account linked successfully. You can now sync data.",
    }


@router.post("/sync")
async def sync(
    days_back: int = Query(14, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Pull Whoop data for the given range and upsert into health_metrics."""
    tok = (
        await db.execute(select(WhoopToken).where(WhoopToken.id == 1))
    ).scalar_one_or_none()

    if tok is None:
        return JSONResponse(
            {"error": "Whoop not connected. Call /api/whoop/authorize first."},
            status_code=400,
        )

    result = await sync_whoop_data(db, days_back=days_back)
    response = {
        "status": "ok",
        "days_fetched": result.days_fetched,
        "inserted": result.inserted,
        "updated": result.updated,
    }
    if result.errors:
        response["errors"] = result.errors
        response["status"] = "partial"
    return response


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db)):
    """Report whether Whoop is connected, and token/scope details."""
    tok = (
        await db.execute(select(WhoopToken).where(WhoopToken.id == 1))
    ).scalar_one_or_none()

    if tok is None:
        return {
            "connected": False,
            "message": "No Whoop account linked.",
        }

    return {
        "connected": True,
        "whoop_user_id": tok.whoop_user_id,
        "scopes": tok.scopes,
        "expires_at": tok.expires_at.isoformat() if tok.expires_at else None,
        "updated_at": tok.updated_at.isoformat() if tok.updated_at else None,
    }


@router.post("/disconnect")
async def disconnect(db: AsyncSession = Depends(get_db)):
    """Remove stored Whoop tokens, effectively disconnecting."""
    tok = (
        await db.execute(select(WhoopToken).where(WhoopToken.id == 1))
    ).scalar_one_or_none()

    if tok is None:
        return {"status": "already_disconnected"}

    await db.delete(tok)
    await db.commit()
    return {"status": "disconnected", "message": "Whoop tokens removed."}
