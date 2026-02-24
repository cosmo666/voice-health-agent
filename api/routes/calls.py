"""Call log endpoints for the Sunrise Health Clinic API.

Stores and retrieves voice call transcripts and metadata. When a new call
log is saved, background tasks are kicked off to generate an AI summary
and sentiment score via Ollama.
"""

import asyncio
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.background import process_call_post
from api.dependencies import get_db
from api.models import CallLog
from api.schemas import CallLogCreate, CallLogResponse, PaginatedCallLogs

router = APIRouter(prefix="/api/calls", tags=["calls"])


@router.post("/", response_model=CallLogResponse, status_code=201)
async def save_call_log(
    body: CallLogCreate,
    db: AsyncSession = Depends(get_db),
) -> CallLogResponse:
    """Save a new voice call log and kick off background post-processing.

    The call log is persisted immediately and returned to the caller. Summary
    generation and sentiment analysis run asynchronously in the background --
    they will update the record later without blocking this response.

    Args:
        body: Call log data including transcript, duration, tools used, etc.

    Returns:
        The created CallLogResponse (summary and sentiment may be null initially).
    """
    logger.info(
        "Saving call log: phone={}, duration={}s, escalated={}",
        body.patient_phone,
        body.duration_seconds,
        body.escalated,
    )

    call_log = CallLog(
        patient_phone=body.patient_phone,
        duration_seconds=body.duration_seconds,
        transcript=body.transcript,
        summary=body.summary,
        tools_used=body.tools_used,
        escalated=body.escalated,
        sentiment_score=body.sentiment_score,
    )

    db.add(call_log)
    await db.commit()
    await db.refresh(call_log)

    logger.info("Call log saved: id={}", call_log.id)

    # Fire background processing (summary + sentiment) without blocking
    # Only run if summary was not already provided
    if call_log.summary is None and call_log.transcript.strip():
        asyncio.create_task(process_call_post(call_log.id))
        logger.info("Background post-processing started for call_id={}", call_log.id)

    return CallLogResponse(
        id=call_log.id,
        patient_phone=call_log.patient_phone,
        duration_seconds=call_log.duration_seconds,
        transcript=call_log.transcript,
        summary=call_log.summary,
        tools_used=call_log.tools_used or [],
        escalated=call_log.escalated,
        sentiment_score=call_log.sentiment_score,
        ai_insights=call_log.ai_insights,
        created_at=call_log.created_at,
    )


@router.get("/", response_model=PaginatedCallLogs)
async def list_call_logs(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    phone: str | None = Query(None, description="Filter by patient phone number"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedCallLogs:
    """List call logs with pagination and optional phone number filter.

    Args:
        page: Page number (1-indexed).
        per_page: Number of items per page (max 100).
        phone: Optional exact phone number filter.

    Returns:
        PaginatedCallLogs with items, total count, and pagination metadata.
    """
    logger.info("Listing call logs: page={}, per_page={}, phone={}", page, per_page, phone)

    # Base query conditions
    conditions = []
    if phone:
        conditions.append(CallLog.patient_phone == phone)

    # Count total matching records
    count_stmt = select(func.count(CallLog.id))
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    count_result = await db.execute(count_stmt)
    total: int = count_result.scalar_one()

    # Calculate pagination
    total_pages = max(1, math.ceil(total / per_page))
    offset = (page - 1) * per_page

    # Fetch page of results
    items_stmt = (
        select(CallLog)
        .order_by(CallLog.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    if conditions:
        items_stmt = items_stmt.where(*conditions)

    result = await db.execute(items_stmt)
    call_logs = result.scalars().all()

    logger.info("Returning {} call logs (page {}/{})", len(call_logs), page, total_pages)

    return PaginatedCallLogs(
        items=[
            CallLogResponse(
                id=log.id,
                patient_phone=log.patient_phone,
                duration_seconds=log.duration_seconds,
                transcript=log.transcript,
                summary=log.summary,
                tools_used=log.tools_used or [],
                escalated=log.escalated,
                sentiment_score=log.sentiment_score,
                ai_insights=log.ai_insights,
                created_at=log.created_at,
            )
            for log in call_logs
        ],
        total=total,
        page=page,
        per_page=per_page,
        pages=total_pages,
    )


@router.get("/{call_id}", response_model=CallLogResponse)
async def get_call_log(
    call_id: str,
    db: AsyncSession = Depends(get_db),
) -> CallLogResponse:
    """Retrieve a single call log by its ID.

    Args:
        call_id: UUID of the call log record.

    Returns:
        The matching CallLogResponse.

    Raises:
        HTTPException 404: No call log found with the given ID.
    """
    logger.info("Fetching call log: id={}", call_id)

    result = await db.execute(
        select(CallLog).where(CallLog.id == call_id)
    )
    call_log: CallLog | None = result.scalar_one_or_none()

    if call_log is None:
        logger.warning("Call log not found: id={}", call_id)
        raise HTTPException(
            status_code=404,
            detail=f"Call log '{call_id}' not found.",
        )

    return CallLogResponse(
        id=call_log.id,
        patient_phone=call_log.patient_phone,
        duration_seconds=call_log.duration_seconds,
        transcript=call_log.transcript,
        summary=call_log.summary,
        tools_used=call_log.tools_used or [],
        escalated=call_log.escalated,
        sentiment_score=call_log.sentiment_score,
        ai_insights=call_log.ai_insights,
        created_at=call_log.created_at,
    )
