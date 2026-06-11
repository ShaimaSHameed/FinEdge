from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.analysis_history import AnalysisHistory
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/user", tags=["user"])

DEFAULT_USER_ID = "anonymous"


@router.get("/history")
async def get_history(
    user_id: str = DEFAULT_USER_ID,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    stmt = (
        select(AnalysisHistory)
        .where(AnalysisHistory.user_id == user_id)
        .order_by(AnalysisHistory.created_at.desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "ticker": row.ticker,
            "market": row.market,
            "analysis_types": row.analysis_types,
            "results": row.results,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.delete("/history/{history_id}")
async def delete_history_item(
    history_id: str,
    user_id: str = DEFAULT_USER_ID,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    stmt = (
        select(AnalysisHistory)
        .where(AnalysisHistory.id == history_id)
        .where(AnalysisHistory.user_id == user_id)
        .limit(1)
    )

    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        raise HTTPException(status_code=404, detail="History item not found")

    await db.delete(record)
    await db.commit()

    return {"status": "deleted"}
