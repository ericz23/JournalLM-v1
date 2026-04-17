"""Chat API routes — session management, SSE message streaming, embeddings."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.chat import ChatMessage, ChatSession
from app.services.chat_engine import generate_response_stream
from app.services.embeddings import embed_journals

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Schemas ──────────────────────────────────────────────────────────


class SessionCreate(BaseModel):
    title: str | None = None
    is_temporary: bool = False


class SessionSummary(BaseModel):
    id: str
    title: str | None
    is_temporary: bool
    message_count: int
    created_at: str
    updated_at: str


class MessageSchema(BaseModel):
    id: int
    role: str
    content: str
    retrieved_context: list | None = None
    created_at: str


class SessionDetail(BaseModel):
    id: str
    title: str | None
    messages: list[MessageSchema]


class SendMessage(BaseModel):
    content: str
    mode: str = "default"


class EmbedResponse(BaseModel):
    entries_processed: int
    chunks_created: int
    skipped: int


# ── Session endpoints ────────────────────────────────────────────────


@router.post("/sessions", response_model=SessionSummary)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    session = ChatSession(title=body.title, is_temporary=body.is_temporary)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionSummary(
        id=session.id,
        title=session.title,
        is_temporary=session.is_temporary,
        message_count=0,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    q = (
        select(
            ChatSession,
            func.count(ChatMessage.id).label("msg_count"),
        )
        .where(ChatSession.is_temporary == False)  # noqa: E712
        .outerjoin(ChatMessage)
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
    )
    rows = (await db.execute(q)).all()
    return [
        SessionSummary(
            id=row[0].id,
            title=row[0].title,
            is_temporary=row[0].is_temporary,
            message_count=row[1],
            created_at=row[0].created_at.isoformat(),
            updated_at=row[0].updated_at.isoformat(),
        )
        for row in rows
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = (await db.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.messages))
    )).scalar_one_or_none()

    if session is None:
        raise HTTPException(404, "Session not found")

    return SessionDetail(
        id=session.id,
        title=session.title,
        messages=[
            MessageSchema(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                retrieved_context=(
                    json.loads(msg.retrieved_context)
                    if msg.retrieved_context else None
                ),
                created_at=msg.created_at.isoformat(),
            )
            for msg in session.messages
        ],
    )


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = (await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )).scalar_one_or_none()

    if session is None:
        raise HTTPException(404, "Session not found")

    await db.delete(session)
    await db.commit()
    return {"status": "deleted"}


@router.patch("/sessions/{session_id}/save", response_model=SessionSummary)
async def save_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Convert a temporary session into a permanent one."""
    session = (await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )).scalar_one_or_none()

    if session is None:
        raise HTTPException(404, "Session not found")

    session.is_temporary = False
    await db.commit()
    await db.refresh(session)

    msg_count = (await db.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
    )).scalar() or 0

    return SessionSummary(
        id=session.id,
        title=session.title,
        is_temporary=session.is_temporary,
        message_count=msg_count,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


# ── Message endpoint (SSE streaming) ─────────────────────────────────


@router.post("/sessions/{session_id}/message")
async def send_message(
    session_id: str,
    body: SendMessage,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    session = (await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )).scalar_one_or_none()

    if session is None:
        raise HTTPException(404, "Session not found")

    async def event_stream():
        async for event_type, data in generate_response_stream(
            db, session_id, body.content, mode=body.mode,
        ):
            if await request.is_disconnected():
                break
            yield f"event: {event_type}\ndata: {data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Embedding trigger ────────────────────────────────────────────────


@router.post("/embed", response_model=EmbedResponse)
async def trigger_embed(db: AsyncSession = Depends(get_db)):
    result = await embed_journals(db)
    return EmbedResponse(
        entries_processed=result.entries_processed,
        chunks_created=result.chunks_created,
        skipped=result.skipped,
    )
