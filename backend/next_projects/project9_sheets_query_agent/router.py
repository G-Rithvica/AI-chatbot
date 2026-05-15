from fastapi import APIRouter, HTTPException

from app.services.sheets_service import SheetsServiceConfigurationError
from .models import SheetsAgentQueryRequest, SheetsAgentQueryResponse
from .service import (
    SheetsAgentDependencyError,
    SheetsAgentNotConfiguredError,
    SheetsAgentProviderError,
    SheetsAgentValidationError,
    answer_sheet_query,
)

router = APIRouter(prefix='/project9/sheets-agent', tags=['project9'])


@router.post('/query', response_model=SheetsAgentQueryResponse)
async def query_sheet(payload: SheetsAgentQueryRequest) -> SheetsAgentQueryResponse:
    try:
        return await answer_sheet_query(payload)
    except SheetsAgentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SheetsServiceConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SheetsAgentDependencyError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except SheetsAgentNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except SheetsAgentProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
