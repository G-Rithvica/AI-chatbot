from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.tabular_source import TabularSourceError
from app.db.session import get_db
from app.models.user import User
from app.schemas.database_chat import (
    DatabaseConnectRequest,
    DatabaseConnectResponse,
    DatabaseQueryRequest,
    DatabaseQueryResponse,
    SpreadsheetQueryRequest,
    SpreadsheetQueryResponse,
)
from app.services.chat_service import save_message
from app.services.database_chat_service import DatabaseConnectionError, answer_database_question, connect_to_database
from app.services.spreadsheet_chat_service import SpreadsheetSourceError, answer_spreadsheet_query, _format_spreadsheet_reply
from app.services.thread_service import get_thread

router = APIRouter(prefix='/database', tags=['database'])


def _format_database_reply(result: DatabaseQueryResponse) -> str:
    lines: list[str] = [
        '### Database Result',
        f"Status: {'Allowed' if result.allowed else 'Blocked'}",
        f'Message: {result.message}',
    ]

    if result.sql:
        lines.extend(['', 'Generated SQL:', '```sql', result.sql, '```'])

    if result.explanation:
        lines.extend(['', f'Explanation: {result.explanation}'])

    if result.columns and result.rows:
        header = f"| {' | '.join(result.columns)} |"
        divider = f"| {' | '.join('---' for _ in result.columns)} |"
        body = []
        for row in result.rows[:50]:
            cells = [str(row.get(column, '')) for column in result.columns]
            body.append(f"| {' | '.join(cells)} |")
        lines.extend(['', f'Rows returned: {result.row_count}', '', header, divider, *body])
    else:
        lines.extend(['', f'Rows returned: {result.row_count}'])

    return '\n'.join(lines)


@router.post('/connect', response_model=DatabaseConnectResponse)
async def database_connect(
    payload: DatabaseConnectRequest,
    current_user: User = Depends(get_current_user),
) -> DatabaseConnectResponse:
    del current_user
    try:
        return await connect_to_database(payload)
    except DatabaseConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TabularSourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=501, detail=f'Missing database driver: {exc.name}') from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post('/query', response_model=DatabaseQueryResponse)
async def database_query(
    payload: DatabaseQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DatabaseQueryResponse:
    try:
        if payload.thread_id:
            thread = await get_thread(db, payload.thread_id, current_user.id)
            if not thread:
                raise HTTPException(status_code=404, detail='Thread not found.')

        result = await answer_database_question(payload)

        if payload.thread_id:
            await save_message(db, current_user.id, 'user', payload.question, payload.thread_id)
            await save_message(db, current_user.id, 'assistant', _format_database_reply(result), payload.thread_id)

        return result
    except DatabaseConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TabularSourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=501, detail=f'Missing database driver: {exc.name}') from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post('/spreadsheet/query', response_model=SpreadsheetQueryResponse)
async def spreadsheet_query(
    payload: SpreadsheetQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SpreadsheetQueryResponse:
    """
    Query a spreadsheet (CSV, Excel, or Google Sheets) with a natural language question.
    
    Supports:
    - Uploaded files via attachment ID
    - Local file paths
    - Google Sheets URLs
    """
    try:
        result = await answer_spreadsheet_query(payload, db=db, user_id=current_user.id)

        if payload.thread_id:
            thread = await get_thread(db, payload.thread_id, current_user.id)
            if not thread:
                raise HTTPException(status_code=404, detail='Thread not found.')
            
            await save_message(db, current_user.id, 'user', payload.question, payload.thread_id)
            await save_message(db, current_user.id, 'assistant', _format_spreadsheet_reply(result), payload.thread_id)

        return result
    except SpreadsheetSourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
