from pydantic import BaseModel, Field


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    size: str = Field(default='1024x1024')
    style: str | None = None
    response_format: str = Field(default='b64_json')


class ImageGenerationResult(BaseModel):
    mime_type: str = 'image/png'
    image_base64: str
    revised_prompt: str | None = None
