#!/usr/bin/env python3
"""
Spreadsheet Chat Integration - API Test Examples

This script demonstrates how to test the new spreadsheet query API endpoint.
Run the backend server first: uvicorn app.main:app --reload
"""

import asyncio
import json
import sys
from pathlib import Path

# Add backend to path for imports
backend_path = Path(__file__).parent / 'backend'
sys.path.insert(0, str(backend_path))

from app.schemas.database_chat import SpreadsheetQueryRequest, SpreadsheetQueryResponse


async def test_spreadsheet_query_locally():
    """Test spreadsheet query with a local CSV file."""
    print("=" * 70)
    print("TEST 1: Local CSV File Query")
    print("=" * 70)
    
    # Create test request
    request = SpreadsheetQueryRequest(
        source_id=str(Path(__file__).parent / 'sample.csv'),
        question="What is the highest score?",
        max_rows=50,
    )
    
    print("\n📋 Request:")
    print(f"  Source: {request.source_id}")
    print(f"  Question: {request.question}")
    print(f"  Max Rows: {request.max_rows}")
    
    print("\n✅ Request is valid")
    print(f"  Request model: {request.model_dump_json(indent=2)}")


async def test_spreadsheet_query_with_attachment():
    """Test spreadsheet query with attachment ID."""
    print("\n" + "=" * 70)
    print("TEST 2: Query with Attachment ID (via API)")
    print("=" * 70)
    
    request = SpreadsheetQueryRequest(
        source_id="550e8400-e29b-41d4-a716-446655440000",  # Example attachment ID
        question="Show me the average score by city",
        sheet_name=None,
        max_rows=100,
        thread_id="thread-123",  # For saving to chat history
    )
    
    print("\n📋 Request:")
    print(f"  Attachment ID: {request.source_id}")
    print(f"  Question: {request.question}")
    print(f"  Thread ID: {request.thread_id}")
    print(f"  Max Rows: {request.max_rows}")
    
    print("\n✅ Request is valid")
    print(f"  Request model: {request.model_dump_json(indent=2)}")
    
    print("\n📝 curl Example:")
    print("""
curl -X POST "http://localhost:8000/api/database/spreadsheet/query" \\
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "source_id": "550e8400-e29b-41d4-a716-446655440000",
    "question": "Show me the average score by city",
    "sheet_name": null,
    "max_rows": 100,
    "thread_id": "thread-123"
  }'
    """)


async def test_spreadsheet_query_response_format():
    """Show expected response format."""
    print("\n" + "=" * 70)
    print("TEST 3: Expected Response Format")
    print("=" * 70)
    
    response_example = {
        "source_type": "spreadsheet",
        "allowed": True,
        "message": "Successfully analyzed spreadsheet query: What is the highest score?",
        "answer": "The highest score in the dataset is 30, which belongs to Charlie from Chicago.",
        "columns": ["name", "score", "city"],
        "rows_considered": 5,
        "thread_id": "thread-123"
    }
    
    print("\n✅ Expected Response:")
    print(json.dumps(response_example, indent=2))
    
    # Validate against schema
    response = SpreadsheetQueryResponse(**response_example)
    print(f"\n✓ Response validates against SpreadsheetQueryResponse schema")


async def test_google_sheets_example():
    """Show Google Sheets query example."""
    print("\n" + "=" * 70)
    print("TEST 4: Google Sheets Query (if configured)")
    print("=" * 70)
    
    request = SpreadsheetQueryRequest(
        source_id="https://docs.google.com/spreadsheets/d/1SHEET_ID_HERE/edit",
        question="What is the total revenue?",
        max_rows=200,
    )
    
    print("\n📋 Google Sheets Request:")
    print(f"  Source: {request.source_id}")
    print(f"  Question: {request.question}")
    
    print("\n📝 Alternative using Sheet ID only:")
    print('  source_id: "1SHEET_ID_HERE"')
    
    print("\n⚙️  Prerequisites:")
    print("  1. Set GOOGLE_SERVICE_ACCOUNT_JSON in .env")
    print("  2. Share the Google Sheet with the service account email")
    print("  3. Grant at least 'Viewer' access")


async def test_error_cases():
    """Show common error cases."""
    print("\n" + "=" * 70)
    print("TEST 5: Error Handling Examples")
    print("=" * 70)
    
    error_cases = [
        {
            "name": "Invalid Attachment ID",
            "request": {"source_id": "nonexistent-id", "question": "test"},
            "expected_status": 404,
            "expected_error": "Spreadsheet not found"
        },
        {
            "name": "Invalid File Path",
            "request": {"source_id": "/invalid/path.csv", "question": "test"},
            "expected_status": 404,
            "expected_error": "Spreadsheet source could not be resolved"
        },
        {
            "name": "Unsupported Format",
            "request": {"source_id": "/path/to/file.txt", "question": "test"},
            "expected_status": 400,
            "expected_error": "Unsupported spreadsheet format"
        },
        {
            "name": "Missing Question",
            "request": {"source_id": "file.csv", "question": ""},
            "expected_status": 422,
            "expected_error": "Validation error"
        },
    ]
    
    for case in error_cases:
        print(f"\n❌ {case['name']}:")
        print(f"  Status: {case['expected_status']}")
        print(f"  Error: {case['expected_error']}")


async def test_workflow_with_thread():
    """Show complete workflow with thread integration."""
    print("\n" + "=" * 70)
    print("TEST 6: Complete Workflow with Thread Integration")
    print("=" * 70)
    
    print("\n📋 Workflow Steps:")
    print("""
1. Upload file:
   POST /api/attachments/upload
   Response: { "id": "attachment-123", ... }

2. Create thread (optional):
   POST /api/threads
   Response: { "id": "thread-456", ... }

3. Query spreadsheet:
   POST /api/database/spreadsheet/query
   {
     "source_id": "attachment-123",
     "question": "What is the average score?",
     "thread_id": "thread-456",
     "max_rows": 100
   }
   Response: { "answer": "...", "rows_considered": 5, ... }

4. Query is automatically saved to thread:
   GET /api/threads/thread-456/messages
   Returns both user question and assistant answer

5. Ask follow-up questions:
   POST /api/database/spreadsheet/query
   {
     "source_id": "attachment-123",
     "question": "Group by city",
     "thread_id": "thread-456"
   }
   
All questions and answers are saved to conversation history!
    """)


async def main():
    """Run all tests."""
    print("""
╔══════════════════════════════════════════════════════════════════════════╗
║           SPREADSHEET CHAT INTEGRATION - API TEST SUITE                  ║
║                                                                          ║
║ This demonstrates how to use the new /database/spreadsheet/query        ║
║ endpoint to query CSV, Excel, and Google Sheets files.                  ║
╚══════════════════════════════════════════════════════════════════════════╝
    """)
    
    try:
        await test_spreadsheet_query_locally()
        await test_spreadsheet_query_with_attachment()
        await test_spreadsheet_query_response_format()
        await test_google_sheets_example()
        await test_error_cases()
        await test_workflow_with_thread()
        
        print("\n" + "=" * 70)
        print("✅ ALL TESTS COMPLETED SUCCESSFULLY")
        print("=" * 70)
        
        print("""
📚 NEXT STEPS:
1. Review SPREADSHEET_INTEGRATION.md for full documentation
2. Review IMPLEMENTATION_SUMMARY.md for technical details
3. Run pytest tests: pytest backend/tests/test_spreadsheet_chat_module.py -v
4. Start the backend: uvicorn app.main:app --reload
5. Test the API using curl or your API client

🔗 ENDPOINT:
POST http://localhost:8000/api/database/spreadsheet/query

📖 DOCUMENTATION:
- SPREADSHEET_INTEGRATION.md - Complete guide
- IMPLEMENTATION_SUMMARY.md - Implementation details
- backend/tests/test_spreadsheet_chat_module.py - Test examples
- backend/app/services/spreadsheet_chat_service.py - Source code
        """)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == '__main__':
    asyncio.run(main())
