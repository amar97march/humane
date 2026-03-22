"""Tests for VoiceProcessor — transcription, format handling, error paths, fallback."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from humane.bot.voice import VoiceProcessor, SUPPORTED_FORMATS


@dataclass
class MockVoiceConfig:
    llm_api_key: str = "test-api-key"
    voice_provider: str = "openai"
    whisper_model: str = "whisper-1"
    voice_enabled: bool = True


def _make_processor(api_key="test-api-key", provider="openai"):
    config = MockVoiceConfig(llm_api_key=api_key, voice_provider=provider)
    return VoiceProcessor(config)


class TestVoiceProcessorInit:
    def test_default_config(self):
        proc = _make_processor()
        assert proc.api_key == "test-api-key"
        assert proc.provider == "openai"
        assert proc.model == "whisper-1"
        assert proc.enabled is True

    def test_custom_provider(self):
        proc = _make_processor(provider="local")
        assert proc.provider == "local"


class TestSupportedFormats:
    def test_ogg_is_supported(self):
        assert "ogg" in SUPPORTED_FORMATS

    def test_mp3_is_supported(self):
        assert "mp3" in SUPPORTED_FORMATS

    def test_wav_is_supported(self):
        assert "wav" in SUPPORTED_FORMATS

    def test_m4a_is_supported(self):
        assert "m4a" in SUPPORTED_FORMATS

    def test_webm_is_supported(self):
        assert "webm" in SUPPORTED_FORMATS


@pytest.mark.asyncio
class TestTranscribeUnsupportedFormat:
    async def test_unsupported_format_raises_value_error(self):
        proc = _make_processor()
        with pytest.raises(ValueError, match="Unsupported audio format"):
            await proc.transcribe(b"fake audio data", format="flac")

    async def test_unsupported_format_error_lists_supported(self):
        proc = _make_processor()
        with pytest.raises(ValueError, match="Supported"):
            await proc.transcribe(b"fake audio data", format="aac")


@pytest.mark.asyncio
class TestTranscribeOpenAI:
    async def test_transcribe_calls_openai_api(self):
        proc = _make_processor()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Hello, world!"}

        with patch("humane.bot.voice.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await proc.transcribe(b"fake audio bytes", format="ogg")

        assert result == "Hello, world!"

    async def test_transcribe_sends_correct_url(self):
        proc = _make_processor()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Test"}

        with patch("humane.bot.voice.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proc.transcribe(b"fake audio bytes", format="mp3")

        call_args = mock_client.post.call_args
        assert "api.openai.com" in call_args[0][0]
        assert "transcriptions" in call_args[0][0]

    async def test_transcribe_sends_authorization_header(self):
        proc = _make_processor(api_key="sk-test-12345")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Test"}

        with patch("humane.bot.voice.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proc.transcribe(b"fake audio bytes", format="wav")

        call_args = mock_client.post.call_args
        headers = call_args.kwargs.get("headers", {})
        assert "Authorization" in headers
        assert "sk-test-12345" in headers["Authorization"]

    async def test_transcribe_handles_api_error(self):
        proc = _make_processor()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("humane.bot.voice.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(RuntimeError, match="500"):
                await proc.transcribe(b"fake audio bytes", format="ogg")

    async def test_transcribe_handles_rate_limit(self):
        proc = _make_processor()

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"

        with patch("humane.bot.voice.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(RuntimeError, match="429"):
                await proc.transcribe(b"fake audio bytes", format="ogg")

    async def test_transcribe_strips_whitespace_from_result(self):
        proc = _make_processor()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "  Hello, world!  "}

        with patch("humane.bot.voice.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await proc.transcribe(b"fake audio bytes", format="ogg")

        assert result == "Hello, world!"

    async def test_transcribe_all_supported_formats(self):
        proc = _make_processor()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "Transcribed text"}

        for fmt in SUPPORTED_FORMATS:
            with patch("humane.bot.voice.httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                result = await proc.transcribe(b"fake audio bytes", format=fmt)
                assert result == "Transcribed text"


@pytest.mark.asyncio
class TestTranscribeFallback:
    async def test_fallback_when_no_api_key(self):
        proc = _make_processor(api_key="", provider="openai")

        # Without whisper installed, should raise RuntimeError
        with pytest.raises(RuntimeError, match="Local whisper not available"):
            await proc.transcribe(b"fake audio bytes", format="ogg")

    async def test_fallback_when_provider_not_openai(self):
        proc = _make_processor(api_key="key", provider="local")

        # Without whisper installed, should raise RuntimeError
        with pytest.raises(RuntimeError, match="Local whisper not available"):
            await proc.transcribe(b"fake audio bytes", format="ogg")

    async def test_fallback_with_mock_whisper(self):
        import sys

        proc = _make_processor(api_key="", provider="local")

        mock_whisper_model = MagicMock()
        mock_whisper_model.transcribe.return_value = {"text": "Local transcription"}

        # Mock the whisper module so import succeeds
        mock_whisper_module = MagicMock()
        mock_whisper_module.load_model.return_value = mock_whisper_model

        with patch.dict(sys.modules, {"whisper": mock_whisper_module}):
            result = await proc.transcribe(b"fake audio bytes", format="ogg")
            assert result == "Local transcription"
