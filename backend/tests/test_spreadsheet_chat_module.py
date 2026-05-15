import csv
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import Attachment
from app.schemas.database_chat import SpreadsheetQueryRequest
from app.services.spreadsheet_chat_service import SpreadsheetSourceError, answer_spreadsheet_query


def _create_sample_csv(path: Path) -> None:
    """Create a sample CSV file for testing."""
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['name', 'score', 'city'])
        writer.writerow(['Alice', 10, 'New York'])
        writer.writerow(['Bob', 20, 'Los Angeles'])
        writer.writerow(['Charlie', 30, 'Chicago'])
        writer.writerow(['David', 15, 'New York'])
        writer.writerow(['Eve', 25, 'Boston'])


def _create_sample_excel(path: Path) -> None:
    """Create a sample Excel file for testing."""
    df = pd.DataFrame({
        'name': ['Alice', 'Bob', 'Charlie', 'David', 'Eve'],
        'score': [10, 20, 30, 15, 25],
        'city': ['New York', 'Los Angeles', 'Chicago', 'New York', 'Boston'],
    })
    df.to_excel(path, index=False, engine='openpyxl')


@pytest.mark.asyncio
async def test_spreadsheet_query_with_local_csv_file() -> None:
    """Test querying a local CSV file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / 'sample.csv'
        _create_sample_csv(csv_path)

        result = await answer_spreadsheet_query(
            SpreadsheetQueryRequest(
                source_id=str(csv_path),
                question='What is the highest score?',
                max_rows=50,
            )
        )

        assert result.allowed is True
        assert result.source_type == 'spreadsheet'
        assert 'answer' in result.answer.lower() or '30' in result.answer
        assert result.rows_considered == 5
        assert set(result.columns) == {'name', 'score', 'city'}


@pytest.mark.asyncio
async def test_spreadsheet_query_with_local_excel_file() -> None:
    """Test querying a local Excel file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        excel_path = Path(tmpdir) / 'sample.xlsx'
        _create_sample_excel(excel_path)

        result = await answer_spreadsheet_query(
            SpreadsheetQueryRequest(
                source_id=str(excel_path),
                question='How many people are from New York?',
                max_rows=50,
            )
        )

        assert result.allowed is True
        assert result.source_type == 'spreadsheet'
        assert '2' in result.answer or 'two' in result.answer.lower()
        assert result.rows_considered == 5


@pytest.mark.asyncio
async def test_spreadsheet_query_with_max_rows_limit() -> None:
    """Test that max_rows parameter is respected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / 'sample.csv'
        _create_sample_csv(csv_path)

        result = await answer_spreadsheet_query(
            SpreadsheetQueryRequest(
                source_id=str(csv_path),
                question='What is the highest score?',
                max_rows=2,  # Only analyze first 2 rows + header
            )
        )

        assert result.allowed is True
        assert result.rows_considered == 2  # Only header and first data row


@pytest.mark.asyncio
async def test_spreadsheet_query_invalid_source_raises_error() -> None:
    """Test that querying non-existent file raises error."""
    with pytest.raises(SpreadsheetSourceError):
        await answer_spreadsheet_query(
            SpreadsheetQueryRequest(
                source_id='/nonexistent/file.csv',
                question='What is the data?',
            )
        )


@pytest.mark.asyncio
async def test_spreadsheet_query_returns_proper_columns() -> None:
    """Test that response includes correct column information."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / 'sample.csv'
        _create_sample_csv(csv_path)

        result = await answer_spreadsheet_query(
            SpreadsheetQueryRequest(
                source_id=str(csv_path),
                question='What are the columns?',
                max_rows=50,
            )
        )

        assert 'name' in result.columns
        assert 'score' in result.columns
        assert 'city' in result.columns


@pytest.mark.asyncio
async def test_spreadsheet_query_with_sheet_name() -> None:
    """Test querying Excel file with specific sheet name."""
    with tempfile.TemporaryDirectory() as tmpdir:
        excel_path = Path(tmpdir) / 'sample.xlsx'
        _create_sample_excel(excel_path)

        result = await answer_spreadsheet_query(
            SpreadsheetQueryRequest(
                source_id=str(excel_path),
                question='How many records are there?',
                sheet_name='Sheet1',  # Default sheet name from to_excel
                max_rows=50,
            )
        )

        assert result.allowed is True
        assert result.rows_considered > 0


@pytest.mark.asyncio
async def test_spreadsheet_query_response_format() -> None:
    """Test that response has all required fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / 'sample.csv'
        _create_sample_csv(csv_path)

        result = await answer_spreadsheet_query(
            SpreadsheetQueryRequest(
                source_id=str(csv_path),
                question='Test question',
                max_rows=50,
            )
        )

        # Check all required fields are present
        assert hasattr(result, 'source_type')
        assert hasattr(result, 'allowed')
        assert hasattr(result, 'message')
        assert hasattr(result, 'answer')
        assert hasattr(result, 'columns')
        assert hasattr(result, 'rows_considered')
        
        # Check values
        assert result.source_type == 'spreadsheet'
        assert result.allowed is True
        assert isinstance(result.message, str)
        assert isinstance(result.answer, str)
        assert isinstance(result.columns, list)
        assert isinstance(result.rows_considered, int)
        assert result.rows_considered > 0
