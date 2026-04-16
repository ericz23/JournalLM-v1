from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    row = result.scalar_one()
    return {
        "status": "healthy",
        "database": "connected" if row == 1 else "error",
    }


@router.get("/health/schema")
async def schema_info(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    )
    tables = [r[0] for r in result.fetchall()]
    return {"tables": tables, "count": len(tables)}
