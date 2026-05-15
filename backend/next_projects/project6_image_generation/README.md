# Project 6: Image Generation (Isolated)

This implementation is fully isolated under `backend/next_projects/project6_image_generation` and does not modify existing production routes.

## Environment Variables
- `PROJECT6_IMAGE_API_KEY` (preferred)
- fallback: `LITELLM_API_KEY` or `OPENAI_API_KEY`
- `PROJECT6_IMAGE_MODEL` (default: `gpt-image-1`)
- `PROJECT6_IMAGE_BASE_URL` (optional, for OpenAI-compatible providers)
- fallback: `LITELLM_PROXY_URL`
- `PROJECT6_IMAGE_TIMEOUT_SECONDS` (default: `60`)

## API
- `POST /project6/image-generation/generate`

Request body example:
```json
{
  "prompt": "A futuristic city at sunrise",
  "size": "1024x1024",
  "style": "vivid",
  "response_format": "b64_json"
}
```

Response body:
```json
{
  "mime_type": "image/png",
  "image_base64": "...",
  "revised_prompt": "..."
}
```

## Run Standalone
From `backend/`:
```powershell
.\.venv\Scripts\uvicorn.exe next_projects.project6_image_generation.app:app --host 127.0.0.1 --port 8016
```

## Notes
- This module supports providers returning either `b64_json` or image `url`.
- Validation guards enforce allowed sizes, styles, and response formats.
