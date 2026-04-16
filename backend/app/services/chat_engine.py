"""RAG chat engine — orchestrates retrieval and grounded Gemini generation.

Takes a user message + conversation history, runs the retrieval pipeline,
and produces a streaming response grounded exclusively in retrieved context.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.chat import ChatMessage, ChatSession
from app.services.retrieval import ContextItem, RetrievalResult, retrieve

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are JournalLM, a personal intelligence assistant that helps the user \
recall and reflect on their daily life using their own journal entries.

━━━ GROUND RULES ━━━

1. ONLY use information from the RETRIEVED CONTEXT below to answer. \
Never invent, fabricate, or assume facts not present in the context.

2. If the context does not contain relevant information for the user's \
question, say so clearly: "I don't have journal data for that" or similar. \
Do NOT guess or fill in gaps.

3. When referencing facts, always mention the specific date \
(e.g., "On October 3rd, ...") so the user can verify.

4. The journal data available spans from {date_min} to {date_max}. \
If the user asks about dates outside this range, tell them you don't \
have data for that period.

5. For questions about feelings or mood, reference the sentiment scores \
and reflections from the context. Use the user's own words from journal \
snippets when possible.

6. Be conversational, warm, and concise. Use markdown formatting for \
readability (bullet points, bold for key details).

7. When listing events (restaurants, people, activities), organize them \
clearly — by date or category as appropriate.

━━━ RETRIEVED CONTEXT ━━━

{context_block}

━━━ END CONTEXT ━━━

If the context above is empty or says "No relevant data found", \
respond that you don't have information to answer the question.
"""


def _build_client() -> genai.Client:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _format_context_block(items: list[ContextItem]) -> str:
    if not items:
        return "No relevant data found."

    lines: list[str] = []
    current_date = ""
    for item in sorted(items, key=lambda x: (x.date, x.type)):
        if item.date != current_date:
            current_date = item.date
            lines.append(f"\n--- {current_date} ---")

        prefix = {
            "life_event": "EVENT",
            "reflection": "REFLECTION",
            "health_metric": "HEALTH",
            "journal_chunk": "JOURNAL",
        }.get(item.type, item.type.upper())

        meta_str = ""
        if item.metadata:
            cat = item.metadata.get("category", "")
            if cat:
                prefix = f"EVENT[{cat}]"
            sentiment = item.metadata.get("sentiment")
            if sentiment is not None:
                meta_str = f" (sentiment: {sentiment})"

        lines.append(f"  [{prefix}] {item.content}{meta_str}")

    return "\n".join(lines)


def _build_history(messages: list[ChatMessage]) -> list[types.Content]:
    """Convert stored messages to Gemini conversation format."""
    history: list[types.Content] = []
    for msg in messages:
        role = "user" if msg.role == "user" else "model"
        history.append(types.Content(
            role=role,
            parts=[types.Part(text=msg.content)],
        ))
    return history


@dataclass
class ChatResponse:
    text: str = ""
    context_items: list[dict] = field(default_factory=list)


async def generate_response(
    db: AsyncSession,
    session_id: str,
    user_message: str,
) -> ChatResponse:
    """Non-streaming: retrieve context, generate full response."""
    retrieval = await retrieve(db, user_message)
    context_block = _format_context_block(retrieval.context_items)
    system = SYSTEM_PROMPT.format(
        date_min=retrieval.date_range[0],
        date_max=retrieval.date_range[1],
        context_block=context_block,
    )

    recent_messages = (await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(8)
    )).scalars().all()
    recent_messages = list(reversed(recent_messages))
    history = _build_history(recent_messages)

    client = _build_client()
    response = await client.aio.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=history + [types.Content(
            role="user",
            parts=[types.Part(text=user_message)],
        )],
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.3,
        ),
    )

    return ChatResponse(
        text=response.text,
        context_items=[item.to_dict() for item in retrieval.context_items],
    )


async def generate_response_stream(
    db: AsyncSession,
    session_id: str,
    user_message: str,
) -> AsyncIterator[tuple[str, str]]:
    """Streaming: yields (event_type, data_json) tuples for SSE.

    Event types: "token", "context", "done"
    """
    retrieval = await retrieve(db, user_message)
    context_block = _format_context_block(retrieval.context_items)
    system = SYSTEM_PROMPT.format(
        date_min=retrieval.date_range[0],
        date_max=retrieval.date_range[1],
        context_block=context_block,
    )

    yield (
        "context",
        json.dumps({"items": [item.to_dict() for item in retrieval.context_items]}),
    )

    recent_messages = (await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(8)
    )).scalars().all()
    recent_messages = list(reversed(recent_messages))
    history = _build_history(recent_messages)

    client = _build_client()

    full_text: list[str] = []

    stream = await client.aio.models.generate_content_stream(
        model=settings.GEMINI_MODEL,
        contents=history + [types.Content(
            role="user",
            parts=[types.Part(text=user_message)],
        )],
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.3,
        ),
    )
    async for chunk in stream:
        if chunk.text:
            full_text.append(chunk.text)
            yield ("token", json.dumps({"text": chunk.text}))

    assistant_text = "".join(full_text)

    context_json = json.dumps(
        [item.to_dict() for item in retrieval.context_items]
    )
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=user_message,
    )
    assistant_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=assistant_text,
        retrieved_context=context_json,
    )
    db.add(user_msg)
    db.add(assistant_msg)

    session = (await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )).scalar_one_or_none()
    if session and not session.title:
        session.title = user_message[:80]

    await db.commit()
    await db.refresh(assistant_msg)

    yield ("done", json.dumps({"message_id": assistant_msg.id}))
