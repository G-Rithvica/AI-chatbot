import pytest

from next_projects.project6_image_generation.models import ImageGenerationRequest
from next_projects.project6_image_generation.service import (
    ImageGenerationNotConfiguredError,
    ImageGenerationValidationError,
    generate_image,
)


class _FakeImageData:
    def __init__(self, *, b64_json: str | None = None, url: str | None = None, revised_prompt: str | None = None) -> None:
        self.b64_json = b64_json
        self.url = url
        self.revised_prompt = revised_prompt


class _FakeImagesAPI:
    def __init__(self, result_data: list[_FakeImageData]) -> None:
        self._result_data = result_data

    async def generate(self, **_: object):
        class _Resp:
            data = self._result_data

        return _Resp()


class _FakeClient:
    def __init__(self, result_data: list[_FakeImageData]) -> None:
        self.images = _FakeImagesAPI(result_data)


@pytest.mark.asyncio
async def test_generate_image_raises_when_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('PROJECT6_IMAGE_API_KEY', raising=False)
    monkeypatch.delenv('LITELLM_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)

    with pytest.raises(ImageGenerationNotConfiguredError):
        await generate_image(ImageGenerationRequest(prompt='test'))


@pytest.mark.asyncio
async def test_generate_image_returns_b64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PROJECT6_IMAGE_API_KEY', 'test-key')

    def _fake_build_client(_settings):
        return _FakeClient([_FakeImageData(b64_json='ZmFrZQ==', revised_prompt='refined prompt')])

    monkeypatch.setattr('next_projects.project6_image_generation.service._build_client', _fake_build_client)

    result = await generate_image(ImageGenerationRequest(prompt='draw a tree'))
    assert result.image_base64 == 'ZmFrZQ=='
    assert result.revised_prompt == 'refined prompt'


@pytest.mark.asyncio
async def test_generate_image_validates_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PROJECT6_IMAGE_API_KEY', 'test-key')

    with pytest.raises(ImageGenerationValidationError):
        await generate_image(ImageGenerationRequest(prompt='x', size='640x640'))
