from typing import Any

import anyio
import pandas as pd

from app.core.config import get_settings
from app.services.sheets_service import load_sheet_as_dataframe
from .models import SheetsAgentQueryRequest, SheetsAgentQueryResponse


class SheetsAgentNotConfiguredError(RuntimeError):
    pass


class SheetsAgentDependencyError(RuntimeError):
    pass


class SheetsAgentValidationError(ValueError):
    pass


class SheetsAgentProviderError(RuntimeError):
    pass


def _extract_agent_output(result: Any) -> str:
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        if isinstance(result.get('output'), str):
            return result['output'].strip()
        if isinstance(result.get('result'), str):
            return result['result'].strip()
    return str(result).strip()


def _run_pandas_agent(df: pd.DataFrame, question: str) -> str:
    settings = get_settings()
    if not settings.llm_model or not settings.litellm_api_key:
        raise SheetsAgentNotConfiguredError(
            'LLM_MODEL and LITELLM_API_KEY must be configured for Project 9 query agent.'
        )

    try:
        from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent
    except ImportError as exc:
        raise SheetsAgentDependencyError(
            'langchain-experimental is required for Project 9. Install it in backend requirements.'
        ) from exc

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise SheetsAgentDependencyError(
            'langchain-openai is required for Project 9. Install it in backend requirements.'
        ) from exc

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.litellm_api_key,
        base_url=settings.litellm_proxy_url,
        temperature=0,
    )

    # Recent langchain-experimental versions require explicit opt-in for the
    # underlying Python REPL tool used by the dataframe agent.
    agent = create_pandas_dataframe_agent(
        llm=llm,
        df=df,
        verbose=False,
        allow_dangerous_code=True,
    )

    try:
        result = agent.invoke({'input': question})
    except Exception as exc:  # noqa: BLE001
        raise SheetsAgentProviderError(f'Agent query execution failed: {exc}') from exc

    output = _extract_agent_output(result)
    if not output:
        raise SheetsAgentProviderError('Agent returned an empty response.')
    return output


async def answer_sheet_query(request: SheetsAgentQueryRequest) -> SheetsAgentQueryResponse:
    dataframe = load_sheet_as_dataframe(request.source_id, sheet_name=request.sheet_name)
    limited = dataframe.head(request.max_rows)

    if limited.empty:
        raise SheetsAgentValidationError('Spreadsheet is empty. Unable to answer questions.')

    answer = await anyio.to_thread.run_sync(_run_pandas_agent, limited, request.question)

    return SheetsAgentQueryResponse(
        answer=answer,
        rows_considered=int(len(limited)),
        columns=[str(column) for column in limited.columns.tolist()],
    )
