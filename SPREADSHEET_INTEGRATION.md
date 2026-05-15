# Spreadsheet Chat Integration Guide

## Overview

The chatbot now supports querying spreadsheet files (CSV, Excel, Google Sheets) using natural language. Users can upload files and ask questions about the data, and the chatbot will analyze the data and provide answers.

## Supported File Formats

- **CSV** (.csv, .tsv) - Comma or tab-separated values
- **Excel** (.xlsx, .xls, .ods) - Excel workbooks and OpenDocument Spreadsheets
- **Google Sheets** - Direct URL or sheet ID with proper authentication

## API Endpoints

### 1. Spreadsheet Query (Main Endpoint)

**Endpoint:** `POST /database/spreadsheet/query`

**Authentication:** Required (Bearer token)

**Request Body:**
```json
{
  "source_id": "attachment-id-or-file-path-or-sheet-url",
  "question": "What is the total of all scores?",
  "sheet_name": "Sheet1",  // Optional: for multi-sheet documents
  "max_rows": 50,          // Optional: max rows to analyze (default: 50, max: 200)
  "thread_id": "thread-id" // Optional: save to chat thread
}
```

**Response:**
```json
{
  "source_type": "spreadsheet",
  "allowed": true,
  "message": "Successfully analyzed spreadsheet query: What is the total of all scores?",
  "answer": "The total of all scores is 60 (10 + 20 + 30).",
  "columns": ["name", "score"],
  "rows_considered": 3,
  "thread_id": "thread-id"
}
```

## How It Works

### Data Flow

1. **File Upload**
   - User uploads a CSV/Excel file through the attachments endpoint
   - File is stored in `./uploads/{user_id}/{attachment_id}/`
   - Attachment metadata is saved to database

2. **Query Processing**
   - User sends a natural language question with the attachment ID
   - System loads the spreadsheet data (first N rows, default 50)
   - LLM analyzes the data structure and question
   - Returns answer based on the data

3. **Thread Integration**
   - If `thread_id` is provided, the query and answer are saved to the thread
   - Allows conversation history tracking

### Data Processing

- **Sample Size**: Only the first N rows are sent to the LLM (controlled by `max_rows`)
- **Data Preservation**: Original files are never modified
- **Privacy**: User data is kept isolated per user ID
- **Performance**: Large files are safely handled by sampling

## Usage Examples

### Example 1: Query Uploaded CSV File

```bash
# Step 1: Upload file
curl -X POST "http://localhost:8000/api/attachments/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@sales_data.csv"

# Response:
{
  "id": "attachment-123",
  "file_name": "sales_data.csv",
  ...
}

# Step 2: Query the file
curl -X POST "http://localhost:8000/api/database/spreadsheet/query" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "attachment-123",
    "question": "What is the total sales by region?",
    "max_rows": 100
  }'
```

### Example 2: Query with Thread Integration

```bash
curl -X POST "http://localhost:8000/api/database/spreadsheet/query" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "attachment-123",
    "question": "Show me the top 5 products by revenue",
    "thread_id": "thread-456",
    "max_rows": 100
  }'
```

### Example 3: Query Google Sheets

```bash
# Using Google Sheets URL
curl -X POST "http://localhost:8000/api/database/spreadsheet/query" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "https://docs.google.com/spreadsheets/d/SHEET_ID/edit",
    "question": "What is the average score?"
  }'

# Or using just the Sheet ID
curl -X POST "http://localhost:8000/api/database/spreadsheet/query" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "SHEET_ID",
    "question": "What is the average score?"
  }'
```

## Configuration

### Google Sheets Support

To enable Google Sheets integration:

1. **Set up Google Service Account**
   - Create a service account in Google Cloud Console
   - Download the JSON credentials file

2. **Configure Environment**
   - Set `GOOGLE_SERVICE_ACCOUNT_JSON` to the JSON file path or JSON content:
   ```env
   # Option 1: File path
   GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json
   
   # Option 2: JSON string
   GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
   ```

3. **Share the Sheet**
   - Share your Google Sheet with the service account email
   - Grant at least "Viewer" access

## Error Handling

### Common Errors

| Status | Error | Solution |
|--------|-------|----------|
| 400 | Invalid spreadsheet source | Check attachment ID or file path exists |
| 404 | Spreadsheet not found | Verify file is uploaded or sheet is accessible |
| 502 | Error processing spreadsheet | Check file format is valid and not corrupted |

## Limitations & Notes

- **Max Rows**: LLM only analyzes first N rows (default 50, max 200) for performance
- **File Size**: System handles large files by sampling
- **Sheet Names**: For multi-sheet files, specify the exact sheet name
- **Data Types**: All data is treated as text; numeric analysis depends on LLM understanding
- **Privacy**: All data processing happens on the server; no data is cached

## Integration with Main Chat

The spreadsheet query feature integrates seamlessly with the main chat:

1. Users can upload files
2. Reference attachments in chat messages
3. Ask questions about uploaded files
4. Questions and answers are automatically saved to conversation history
5. Context is maintained across multiple queries in the same thread

## Architecture

### Service Layer
- **`spreadsheet_chat_service.py`**: Main service for processing spreadsheet queries
- **`database_chat_service.py`**: Existing database service (unchanged)
- **`project8_data_qa/spreadsheet_adapter.py`**: Core spreadsheet processing logic

### API Layer
- **`/database/spreadsheet/query`**: Main endpoint for spreadsheet queries
- **`/database/connect`**: Connect to databases (unchanged)
- **`/database/query`**: Query databases (unchanged)

### Database Models
- **Message**: Stores queries and answers (existing)
- **Attachment**: Stores uploaded file metadata (existing)

## Performance Considerations

1. **Sampling Strategy**: Only first N rows sent to LLM to reduce token usage
2. **File Handling**: Large files handled efficiently by pandas
3. **Caching**: Results not cached; each query is processed fresh
4. **Concurrency**: Async processing supports multiple concurrent queries

## Testing

### Local Testing

1. **Upload a test file:**
```bash
curl -X POST "http://localhost:8000/api/attachments/upload" \
  -H "Authorization: Bearer test-token" \
  -F "file=@sample.csv"
```

2. **Query the file:**
```bash
curl -X POST "http://localhost:8000/api/database/spreadsheet/query" \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "your-attachment-id",
    "question": "What is the highest score?"
  }'
```

## Future Enhancements

- [ ] Support for multi-file queries (join/combine data)
- [ ] Custom aggregation functions
- [ ] Data visualization (charts)
- [ ] Advanced filtering and sorting
- [ ] Query caching for performance
- [ ] Integration with database queries (SQL + Spreadsheet joins)

## Troubleshooting

### Issue: "Google Sheets integration not configured"
- **Solution**: Set `GOOGLE_SERVICE_ACCOUNT_JSON` in `.env`

### Issue: "Spreadsheet source not found"
- **Solution**: Verify attachment ID is correct and file is still in uploads directory

### Issue: "Unsupported spreadsheet format"
- **Solution**: Use CSV, XLSX, XLS, ODS, or TSV format

### Issue: "Permission denied for Google Sheet"
- **Solution**: Share the sheet with the service account email address

## Support

For issues or questions, check:
1. The error message and status code
2. Environment variables are set correctly
3. File format is supported
4. Google Service Account has required permissions (if using Google Sheets)
