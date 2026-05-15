from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.chat_service import save_message
from app.services.thread_service import get_thread
from .image_validation import (
    ImageValidationBatchRequest,
    ImageValidationBatchResult,
    ImageValidationRequest,
    ImageValidationResult,
    validate_image,
    validate_images_batch,
)
from .image_rules import ImageRuleReport, ImageRuleRequest, run_rules
from .spreadsheet_adapter import SpreadsheetAnswer, SpreadsheetQuestionRequest, answer_spreadsheet_question
from .sql_guard import (
    SqlGuardResult,
    SqlQueryRequest,
    SqlQueryResult,
    SqlQuestionRequest,
    evaluate_generated_sql,
    execute_read_only_sql,
    generate_sql_from_question,
)

router = APIRouter(prefix='/project8/data-qa', tags=['project8'])


@router.post('/sql/guard', response_model=SqlGuardResult)
async def sql_guard(payload: dict[str, str]) -> SqlGuardResult:
    return evaluate_generated_sql(payload.get('sql', ''))


@router.post('/sql/query', response_model=SqlQueryResult)
async def sql_query(
    payload: SqlQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SqlQueryResult:
    del current_user
    return await execute_read_only_sql(db, payload.sql, max_rows=payload.max_rows)


@router.post('/sql/ask', response_model=SqlQueryResult)
async def sql_ask(
    payload: SqlQuestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SqlQueryResult:
    if payload.source_id:
        try:
            spreadsheet_result = await answer_spreadsheet_question(
                SpreadsheetQuestionRequest(
                    source_id=payload.source_id,
                    question=payload.question,
                    sheet_name=payload.sheet_name,
                    max_rows=payload.max_rows,
                ),
                db=db,
                user_id=current_user.id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return SqlQueryResult(
            allowed=True,
            reason='Spreadsheet question answered successfully.',
            sql=f'SPREADSHEET::{payload.source_id}',
            answer=spreadsheet_result.answer,
            columns=spreadsheet_result.columns,
            rows=[],
            row_count=spreadsheet_result.rows_considered,
        )

    try:
        sql = await generate_sql_from_question(db, payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await execute_read_only_sql(db, sql, max_rows=payload.max_rows)


@router.post('/spreadsheet/query', response_model=SpreadsheetAnswer)
async def spreadsheet_query(payload: SpreadsheetQuestionRequest) -> SpreadsheetAnswer:
    try:
        return await answer_spreadsheet_question(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post('/spreadsheet/query-authenticated', response_model=SpreadsheetAnswer)
async def spreadsheet_query_authenticated(
    payload: SpreadsheetQuestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SpreadsheetAnswer:
    try:
        return await answer_spreadsheet_question(payload, db=db, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post('/image-rules/check', response_model=ImageRuleReport)
async def image_rule_check(
    payload: ImageRuleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImageRuleReport:
    try:
        return await run_rules(payload, db=db, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post('/image-validation/validate', response_model=ImageValidationResult)
async def image_validation_validate(
    payload: ImageValidationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImageValidationResult:
    if payload.thread_id:
        thread = await get_thread(db, payload.thread_id, current_user.id)
        if not thread:
            raise HTTPException(status_code=404, detail='Thread not found.')

    try:
        result = await validate_image(payload, db=db, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if payload.thread_id and result.source_thread_id and payload.thread_id != result.source_thread_id:
        raise HTTPException(status_code=400, detail='Image does not belong to the requested thread.')

    if payload.thread_id:
        user_note = payload.note.strip() if payload.note else ''
        user_message = user_note or f'Validate image: {result.source_name}'
        await save_message(db, current_user.id, 'user', user_message, payload.thread_id)
        await save_message(db, current_user.id, 'assistant', result.chat_summary, payload.thread_id)

    return result


@router.post('/image-validation/validate-batch', response_model=ImageValidationBatchResult)
async def image_validation_validate_batch(
    payload: ImageValidationBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImageValidationBatchResult:
    return await validate_images_batch(payload, db=db, user_id=current_user.id)
