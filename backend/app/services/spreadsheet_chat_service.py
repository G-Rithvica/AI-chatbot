import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BASE_DIR, get_settings
from app.schemas.database_chat import SpreadsheetQueryRequest, SpreadsheetQueryResponse
from next_projects.project8_data_qa.spreadsheet_adapter import (
    SpreadsheetQuestionRequest,
    answer_spreadsheet_question,
)

logger = logging.getLogger(__name__)


class SpreadsheetSourceError(Exception):
    """Raised when there are issues with spreadsheet sources."""

    pass


async def answer_spreadsheet_query(
    payload: SpreadsheetQueryRequest,
    db: AsyncSession | None = None,
    user_id: str | None = None,
) -> SpreadsheetQueryResponse:
    """
    Answer a question based on a spreadsheet (CSV, Excel, or Google Sheets).

    Args:
        payload: The spreadsheet query request
        db: Database session for attachment lookup
        user_id: User ID for attachment verification

    Returns:
        SpreadsheetQueryResponse with the answer
    """
    try:
        # Convert to internal spreadsheet question format
        question_request = SpreadsheetQuestionRequest(
            source_id=payload.source_id,
            question=payload.question,
            sheet_name=payload.sheet_name,
            max_rows=payload.max_rows,
        )

        logger.info(
            'Spreadsheet query requested source_id=%s max_rows=%d',
            payload.source_id,
            payload.max_rows,
        )

        # Answer the spreadsheet question
        spreadsheet_answer = await answer_spreadsheet_question(
            question_request,
            db=db,
            user_id=user_id,
        )

        return SpreadsheetQueryResponse(
            source_type='spreadsheet',
            allowed=True,
            message=f'Successfully analyzed spreadsheet query: {payload.question}',
            answer=spreadsheet_answer.answer,
            columns=spreadsheet_answer.columns,
            rows_considered=spreadsheet_answer.rows_considered,
            thread_id=payload.thread_id,
        )

    except ValueError as exc:
        logger.error('Spreadsheet validation error: %s', str(exc))
        raise SpreadsheetSourceError(f'Invalid spreadsheet source: {str(exc)}') from exc
    except FileNotFoundError as exc:
        logger.error('Spreadsheet file not found: %s', str(exc))
        raise SpreadsheetSourceError(f'Spreadsheet not found: {str(exc)}') from exc
    except Exception as exc:
        logger.error('Error processing spreadsheet query: %s', str(exc))
        raise SpreadsheetSourceError(f'Error processing spreadsheet: {str(exc)}') from exc


def _format_spreadsheet_reply(result: SpreadsheetQueryResponse) -> str:
    """Format spreadsheet response for display in chat."""
    lines: list[str] = [
        '### Spreadsheet Analysis Result',
        f'Message: {result.message}',
        f'Rows Analyzed: {result.rows_considered}',
        '',
        '**Answer:**',
        result.answer,
    ]

    if result.columns:
        lines.extend(['', 'Columns Available:', ', '.join(result.columns)])

    return '\n'.join(lines)
